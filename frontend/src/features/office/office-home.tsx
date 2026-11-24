// office-home.tsx — the office's home page, /office/: "Karibu, Asha", and a big button for each office
// screen the person may open (UI-5, 03 §7.1).
//
// Where a manager lands after logging in on their own phone (Jack, 7 Nov 2026): big buttons are easy to
// tap, and the page grows a button as each office screen comes (products, prices, reports…). Today there
// are seven. Two are for whoever holds device.manage on some side: Vifaa, as its Sajili kifaa is theirs
// (UI-3), and Hali ya vifaa, as keeping the devices working is theirs too (SYNC-14). Mipangilio ya duka is
// for anyone who works on a side: reading the shop's rules needs no key, and changing one is the owner's,
// which the page itself asks for (SHOP-5). Wafanyakazi is for whoever holds staff.manage on the whole shop,
// as even reading the workers is behind it (PPL-6). Mahudhurio ya mwezi is for whoever holds attendance.manage on
// the whole shop, the owner and the managers, as its route asks (ATT-5). Hela ya chakula is for whoever the owner gave
// meals.record on the whole shop (WAGE-7). Tofauti is for whoever holds flag.review on some side, as a flag shows only
// to whoever may close it (CTRL-4).
// A button for a screen someone may not use stays off the page; the server still checks every change
// itself (PPL-5), so this only keeps a door nobody may use out of sight. Under them, for everyone,
// Mipangilio yangu: a person's own language and font need no key (UI-9).
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
import { mayManageAttendance } from "@/features/attendance/attendance-month";
import { FLAGS_PAGE, mayReviewFlags } from "@/features/flags/flags";
import { MEAL_MONEY_PAGE, mayRecordMeals } from "@/features/meals/meal-money";
import { mayManageStaff } from "@/features/workers/workers";

export function OfficeHome() {
  const t = useTranslations("office");
  const devices = useTranslations("device.office");
  const health = useTranslations("device.health");
  const shopSettings = useTranslations("shopSettings");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const settings = useTranslations("mySettings");
  const workers = useTranslations("workers");
  const attendanceMonth = useTranslations("attendanceMonth");
  const mealMoney = useTranslations("mealMoney");
  const flags = useTranslations("flags");
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
      {
        href: "/device-health/",
        label: health("title"),
        open: sidesWhere(here, "device.manage").length > 0,
      },
      {
        // Every rule already travels to every laptop of the shop (SYNC-2): whoever works on a side may read
        // them, as the server lets them (SHOP-3).
        href: "/settings/",
        label: shopSettings("title"),
        open: here.permissions.sides.length > 0,
      },
      {
        // The workers' page shows each worker's roles, and later their pay (WAGE-2): its routes ask
        // staff.manage on the whole shop, not on a side, as a worker belongs to the shop (PPL-4).
        href: "/workers/",
        label: workers("title"),
        open: mayManageStaff(here),
      },
      {
        // The month's attendance is the whole shop's, Asha of Dawa beside Baraka of Vyakula: its route asks
        // attendance.manage on the whole shop, not on a side (ATT-5).
        href: "/attendance-month/",
        label: attendanceMonth("title"),
        open: mayManageAttendance(here),
      },
      {
        // What the shop spends on the workers' meals, which they pay for: for whoever the owner gave its key to, on
        // the whole shop, as both sides eat together (WAGE-7).
        href: MEAL_MONEY_PAGE,
        label: mealMoney("title"),
        open: mayRecordMeals(here),
      },
      {
        // What the system found and a person must look into: for whoever may close a flag on some side, as the
        // server shows a flag to nobody else (CTRL-4).
        href: FLAGS_PAGE,
        label: flags("title"),
        open: mayReviewFlags(here),
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
        {/* Apart from the office's work, and the second kind: it is the person's own, not a job. */}
        <div>
          <ButtonLink href="/my-settings/" kind="second" size="normal">
            {settings("title")}
          </ButtonLink>
        </div>
      </>
    );
  }
}
