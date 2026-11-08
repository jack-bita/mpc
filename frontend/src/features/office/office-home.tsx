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
  const me = useWhoIsHere();

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
  if (refused || !me.data) return <ApiErrorAlert error={me.error} />;

  const open = screens(me.data);
  return (
    <div className="grid max-w-md gap-6">
      <h1 className="text-2xl font-semibold">
        {t("welcome", { name: me.data.staff.display_name })}
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
    </div>
  );
}
