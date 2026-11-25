// advance-page.tsx — one advance's own page, opened from its line on Advansi (WAGE-8, 03 §5.10), as Jack pictured it
// (25 Nov 2026):
//
//   ←  Advansi ya Juma
//   TSh 20,000
//   Jumatano 25/11/2026
//   Ada ya shule
//   Imeandikwa na Meneja · 25/11/2026 10:42 asubuhi
//   [ Batilisha ]
//
// At /advances/view/?id=…, as the app has no [id] pages (ADR-0016): the page around it reads the id from the address. One
// crossed out stays, struck through, with who, when and why (A2); Batilisha opens its sheet (void-advance.tsx), never on
// the person's own, where a line says who may (Jack: A). Opened from outside the app, the arrow leads to the list of the
// advance's own month.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Card, CardContent } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import { monthOf, type Weekday } from "@/features/attendance/attendance-month";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { Decimal } from "@/lib/decimal";
import {
  dayPart,
  formatDate,
  formatDay,
  formatMoney,
  formatTime,
  weekdayOf,
} from "@/lib/format";

import { type AdvancePage, advancesPage, useAdvance } from "./advances";
import { VoidAdvance } from "./void-advance";

export function AdvanceScreen({ id }: { id: string | null }) {
  const t = useTranslations("advances");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  const answer = useAdvance(id);
  const waiting = who.isPending || (id !== null && answer.isPending);
  const advance = answer.data?.advance;

  return (
    <div className="grid max-w-2xl gap-6">
      {/* Whose, as the title once the server says it; until then, what the page is. */}
      <PageHeader
        title={
          advance === undefined
            ? t("title")
            : t("page.title", { name: advance.display_name })
        }
        fallback={advancesPage(
          advance === undefined ? null : monthOf(advance.date),
        )}
      />
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {/* An address with no id names none: the page says so, and asks nothing. */}
      {id === null ? <p>{t("page.none")}</p> : null}
      {/* Not logged in, no network, the server's own problem; or refused: no key, or one the shop doesn't have, "not
          found". A refresh that fails keeps what was last read, with the reason above it. */}
      <ApiErrorAlert error={who.error} />
      <ApiErrorAlert error={answer.error} />
      {who.data && answer.data && !answer.isPending ? (
        <TheAdvance
          // An advance of its own: on another's page, as the browser's back and forward move the address, an open sheet
          // closes, its reason with it, so Juma's never goes to Asha's (worker-page.tsx).
          key={answer.data.advance.id}
          answer={answer.data}
          timezone={who.data.shop.timezone}
        />
      ) : null}
    </div>
  );
}

function TheAdvance({
  answer,
  timezone,
}: {
  answer: AdvancePage;
  timezone: string;
}) {
  const t = useTranslations("advances");
  const monthWords = useTranslations("attendanceMonth");
  const attendance = useTranslations("attendance");
  const [crossing, setCrossing] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const line = useRef<HTMLParagraphElement>(null);
  // Whether the last close was a crossing out, when the button is gone: the keyboard then goes to the amount itself. Read
  // as the sheet goes, after the draw that took it away, so a ref, not the state (worker-pay.tsx).
  const afterVoid = useRef(false);
  const { advance, own, closed } = answer;
  const amount = formatMoney(new Decimal(advance.amount));
  const ready = answer.ready_void_reasons.find(
    (code) => code === advance.voided?.reason,
  );
  return (
    <Card>
      <CardContent>
        <section aria-label={t("title")} className="grid gap-2">
          {/* Struck through once crossed out (<s>, what is no longer right), with who, when and why under it, which a
              screen reader says too, as it says no strike. */}
          <p
            ref={line}
            tabIndex={-1}
            className={
              advance.voided === null
                ? "text-xl font-semibold tabular-nums outline-none"
                : "text-xl text-muted-foreground tabular-nums outline-none"
            }
          >
            {advance.voided === null ? amount : <s>{amount}</s>}
          </p>
          <p>
            {t("day", {
              weekday: monthWords(
                `weekdays.${String(weekdayOf(advance.date)) as Weekday}`,
              ),
              date: formatDay(advance.date),
            })}
          </p>
          {advance.note === "" ? null : <p>{advance.note}</p>}
          <p className="text-muted-foreground">
            {t("page.typedBy", {
              by: advance.by,
              date: formatDate(advance.at, timezone),
              time: attendance("timeOfDay", {
                time: formatTime(advance.at, timezone),
                part: dayPart(advance.at, timezone),
              }),
            })}
          </p>
          {advance.voided !== null ? (
            <>
              <p>
                {t("page.voidedBy", {
                  by: advance.voided.by,
                  date: formatDate(advance.voided.at, timezone),
                })}
              </p>
              {/* On the demo a ready reason's code, said in words; elsewhere the words typed. */}
              <p>
                {t("page.reason", {
                  reason:
                    ready === undefined
                      ? advance.voided.reason
                      : t(`readyReason.${ready}`),
                })}
              </p>
            </>
          ) : closed ? (
            // The pay it came off is approved, the month's or theirs alone (WAGE-3): final, so there is no button.
            <p>{t("page.closed")}</p>
          ) : own ? (
            // Never one's own (Jack: A), and why there is no button: someone else crosses it out.
            <p>{t("page.own")}</p>
          ) : (
            <Button
              ref={button}
              kind="second"
              size="normal"
              className="mt-2 justify-self-start"
              onClick={() => {
                afterVoid.current = false;
                setCrossing(true);
              }}
            >
              {t("void.action")}
            </Button>
          )}
        </section>
        {/* Mounted only while open, so a sheet closed with Ghairi forgets what was typed. */}
        {crossing ? (
          <VoidAdvance
            advance={advance}
            readyReasons={answer.ready_void_reasons}
            onDone={() => {
              afterVoid.current = true;
              setCrossing(false);
            }}
            onClose={() => setCrossing(false)}
            // Or the amount itself, when its button went while the sheet was open: crossed out, its answer lost.
            finalFocus={() =>
              afterVoid.current
                ? line.current
                : (button.current ?? line.current)
            }
          />
        ) : null}
      </CardContent>
    </Card>
  );
}
