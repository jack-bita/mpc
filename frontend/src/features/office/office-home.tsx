// office-home.tsx — the office's home page, /office/: "Karibu, Asha", and a big button for each office
// screen the person may open (UI-5, 03 §7.1).
//
// Where a manager lands after logging in on their own phone (Jack, 7 Nov 2026): big buttons are easy to
// tap, and the page grows a button as each office screen comes (products, prices, reports…). Today there
// is one, Vifaa, for whoever holds device.manage on some side, as its Sajili kifaa is theirs (UI-3).
// A button for a screen someone may not use stays off the page; the server still checks every change
// itself (PPL-5), so this only keeps a door nobody may use out of sight.
//
// "use client": it asks use-intl for words, and the server who is here.
"use client";

import { useEffect, useRef } from "react";
import { useTranslations } from "use-intl";

import { ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { ButtonLink } from "@/components/design/button";
import {
  sidesWhere,
  useWhoIsHere,
  type WhoIsHere,
} from "@/features/people/who-is-here";

export function OfficeHome() {
  const t = useTranslations("office");
  const devices = useTranslations("device.office");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const me = useWhoIsHere();
  // Focus on the welcome as each person arrives: after a login, or Chagua nenosiri lako's Hifadhi, the
  // button that had it is gone. A screen reader then says where the person is, and Tab goes on to the
  // screens (UI-4's review moved focus to each step's heading the same way).
  const welcome = useRef<HTMLHeadingElement>(null);
  const arrived = me.data?.staff.id;
  useEffect(() => welcome.current?.focus(), [arrived]);

  // The office's screens, each with who may open it. A new office screen adds its line here.
  const screens = (here: WhoIsHere) =>
    [
      {
        href: "/devices/",
        label: devices("title"),
        open: sidesWhere(here, "device.manage").length > 0,
      },
    ].filter((screen) => screen.open);

  // Refused, or no answer yet: why. A refusal is read before the answer: TanStack keeps the last answer
  // beside it, which would greet someone the server has just refused, as a suspended person. A 5xx or a
  // dropped network leaves the answer as it was. Nobody logged in, the office's frame sends them to the
  // way in (office-frame.tsx), so "Ingia kwanza" shows only for that moment.
  const refused = me.error instanceof ApiRefusal && me.error.status < 500;
  // Until `me` first answers: "Subiri kidogo…", never a blank page (CI's every-page-in-English test found
  // one, UI-5's PR). The line is on the page from the start and only its words change, as one that comes
  // with its words in it often goes unsaid (offline-banner.tsx).
  const waiting = me.isPending && me.failureCount === 0;

  return (
    <div className="grid max-w-md gap-6">
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {refused || !me.data ? (
        <ApiErrorAlert error={me.error} />
      ) : (
        theWelcome(me.data)
      )}
    </div>
  );

  // The welcome and the screen's buttons. Called, not drawn as a component of its own, so the heading
  // keeps its place, and its focus, across redraws.
  function theWelcome(here: WhoIsHere) {
    const open = screens(here);
    return (
      <>
        <h1
          ref={welcome}
          tabIndex={-1}
          className="text-2xl font-semibold outline-none"
        >
          {t("welcome", { name: here.staff.display_name })}
        </h1>
        {open.length > 0 ? (
          // One under the other, as wide as the column: a finger finds each at once on a phone.
          <ul className="grid gap-3">
            {open.map((screen) => (
              <li key={screen.href}>
                <ButtonLink href={screen.href} className="w-full">
                  {screen.label}
                </ButtonLink>
              </li>
            ))}
          </ul>
        ) : (
          <p>{t("nothingYet")}</p>
        )}
      </>
    );
  }
}
