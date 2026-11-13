// needs-attention.tsx — the records the server refused, as the counter shows them (SYNC-11, SYNC-8, 03 §6.3).
// It owns how a refused record is named and how each of the server's reasons reads at the counter.
//
// The push sets a refused record aside on the laptop (`invalid`, push.ts): it stays in the outbox, marked,
// and is never sent again, as a resend gets the same no. Nothing on the server holds it: a refused clock-in
// never reached the attendance book. So someone must see it, and the manager decide: the counter lists each,
// read live (useNeedsAttention, outbox.ts), with what it was, why, and "tell the manager".
//
// The reasons get the counter's own words, not the office's (errors.*): those end with "try again" or
// "update the app", which can't mend a record already refused. A code the laptop has no words for, as a
// newer server may send, is named by the code itself, so the manager can still look it up.
//
// Here, beside the counter's frame, for every counter screen: the clock-in screen shows it first (SYNC-11),
// and the sale and payment screens can show it the same way. A record is named by its kind when the counter
// knows it (a clock-in: who, which tap, when), else by its number on this laptop.
//
// "use client": it asks use-intl for words, and reads the laptop's database, in the browser only.
"use client";

import { useId } from "react";
import { useTranslations } from "use-intl";

import { Alert, AlertDescription, AlertTitle } from "@/components/design/alert";
import { useThisDevice } from "@/features/devices/this-device";
import { formatTime } from "@/lib/format";
import { CLOCK } from "@/offline/clock-today";
import { type SetAside, useNeedsAttention } from "@/offline/outbox";
import { useStaff } from "@/offline/reference";

/** The server's reasons the counter has words for (PushedAnswer's codes, apps/sync/push.py), by the key
 * of their words: a key of the word book can't hold the code's dot. */
const REASONS = {
  "document.type_unknown": "typeUnknown",
  "document.version_unknown": "versionUnknown",
  "document.maker_unknown": "makerUnknown",
  "id.taken": "idTaken",
} as const;

function knownReason(code: string): code is keyof typeof REASONS {
  return Object.hasOwn(REASONS, code);
}

export function NeedsAttention() {
  const t = useTranslations("needsAttention");
  const attendance = useTranslations("attendance");
  const title = useId();
  const refused = useNeedsAttention();
  const staff = useStaff();
  const timezone = useThisDevice()?.shop.timezone;

  // Nothing until the reads are in, and nothing while nothing was refused: most days, nothing at all.
  if (
    refused === undefined ||
    refused.length === 0 ||
    staff === undefined ||
    timezone === undefined
  )
    return null;

  const nameOf = (staffId: string) =>
    staff.find((row) => row.id === staffId)?.display_name ?? t("unknownPerson");

  /** What the record was: a clock-in by who, which tap and when; any other kind by its number. */
  function whatItWas({ document, device_seq }: SetAside): string {
    const kind = (document.payload as { kind?: unknown } | null)?.kind;
    if (document.type === CLOCK && (kind === "in" || kind === "out"))
      return t("clock", {
        name: nameOf(document.created_by),
        action: attendance(kind === "in" ? "clockIn" : "clockOut"),
        time: formatTime(document.client_time, timezone ?? ""),
      });
    return t("other", { number: device_seq });
  }

  function why(code: string): string {
    return knownReason(code)
      ? t(`reasons.${REASONS[code]}`)
      : t("reasons.other", { code });
  }

  return (
    // role="alert", from the danger kind: a screen reader says it as it comes. Named by its title, so a list of
    // the page's warnings reads "Kumbukumbu zilizokataliwa na seva".
    <Alert kind="danger" aria-labelledby={title}>
      <AlertTitle id={title}>{t("title")}</AlertTitle>
      <AlertDescription>
        <ul className="grid gap-2">
          {refused.map((each) => (
            <li key={each.document.id}>
              <p className="font-semibold">{whatItWas(each)}</p>
              <p>{why(each.reason)}</p>
            </li>
          ))}
        </ul>
        <p className="mt-3">{t("notAgain")}</p>
      </AlertDescription>
    </Alert>
  );
}
