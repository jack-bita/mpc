// worker-pay.tsx — Malipo kwa siku on a worker's page (WAGE-1): their daily pay rate today, its history, and the button
// that gives them a new one.
//
// As Jack pictured it (19 Nov 2026), a card under the roles:
//
//    Malipo kwa siku
//    Sasa: TSh 10,000 kwa siku · anachangia chakula
//    Historia
//    Kuanzia 01/12/2026 · TSh 12,000 · anachangia chakula · Ameongezewa
//    Kuanzia 10/11/2026 · TSh 10,000 · anachangia chakula
//
// with its button on the heading's row since UI-10 (card-heading.tsx), Malipo kwa siku [ Badilisha malipo ], as it
// changes what the whole card shows; its form opens in a sheet over the page, and the button stays in its place.
//
// A worker with no rate today says so (Bado hana malipo kwa siku.), and their button reads Weka malipo; one with a rate
// still to come shows it in the history, as it counts from its own day. Which rate is in force is the server's answer,
// on the shop's own date. Only for whoever holds settings.manage and staff.manage on the whole shop (maySeePay,
// pay-rates.ts): the page asks the rates for them alone, and hands the read down (worker-page.tsx).
//
// The button shows as the roles card's do (worker-roles.tsx): for a worker working or suspended, as a suspended one
// still has days to pay; none for one who left, whose pay up to their last day is worked out with the rates they had;
// none on one's own page, as nobody sets their own pay (staff.own). Who else may is the server's (the PIN's rule), and
// a refusal shows inside the sheet. One change is made at a time: while another card's form is open in the page
// (Badilisha, Ongeza kazi, until UI-11), it hides; its own form is a sheet (UI-10), which shuts the page off behind it,
// the button staying in its place. After a save, one line says what was saved, and the keyboard goes to it (the
// sheet's finalFocus, as the button stays); Ghairi gives the keyboard back to the button, and asks the rates again, as
// a save whose answer was lost may have been made.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { Card, CardContent } from "@/components/design/card";
import type { WhoIsHere } from "@/features/people/who-is-here";
import { Decimal } from "@/lib/decimal";
import { formatDay, formatMoney } from "@/lib/format";

import { CardHeading } from "./card-heading";
import { PayRateForm } from "./pay-rate-form";
import { PAY_RATES, type PayRate, type PayRatesRead } from "./pay-rates";
import type { Worker } from "./workers";

export function WorkerPay({
  worker,
  me,
  rates,
  buttonsHidden = false,
}: {
  worker: Worker;
  me: WhoIsHere;
  /** The worker's rates, asked by the page and handed down (worker-page.tsx). */
  rates: PayRatesRead;
  /** Another card's form is open in the page: this card's button stays off the page meanwhile. */
  buttonsHidden?: boolean;
}) {
  const t = useTranslations("workers.pay");
  const loginWords = useTranslations("login");
  const store = useQueryClient();
  const titleId = useId();
  const historyId = useId();
  // The sheet is open. The page isn't told: a sheet hides no other card's buttons, as it shuts the page off.
  const [open, setOpen] = useState(false);
  // The line that says what the last save did.
  const [news, setNews] = useState<string | null>(null);

  // Where the keyboard goes as the sheet closes, which the sheet alone moves (its finalFocus, worker-actions.tsx):
  // Ghairi, back to the button; a save, to the line that says what was saved.
  const button = useRef<HTMLButtonElement>(null);
  const newsLine = useRef<HTMLDivElement>(null);

  // Who may see the button (see the top); none before the rates came, as the form starts from them. It stays under
  // the open sheet, so Ghairi gives the keyboard back to it.
  const mayChange = worker.status !== "left" && worker.id !== me.staff.id;
  const answer = rates.data;
  const inForce = answer?.rates.find((rate) => rate.id === answer.in_force);
  const showButton = mayChange && !buttonsHidden && answer;
  // Whether the last close was a save, for the sheet to give the keyboard to the done line: read as the sheet goes,
  // after the draw that took it away, so a ref, not the state (worker-actions.tsx).
  const afterSave = useRef(false);

  return (
    <Card>
      {/* One region for the whole card, its button and form included, so a screen reader names the button by the card
          it belongs to, "Malipo kwa siku". */}
      <CardContent>
        <section aria-labelledby={titleId} className="grid gap-6">
          <div className="grid gap-3">
            <CardHeading id={titleId} title={t("title")}>
              {showButton ? (
                <Button
                  ref={button}
                  kind="second"
                  // Normal, on the heading's row, which a big one would crowd (worker-actions.tsx).
                  size="normal"
                  onClick={() => {
                    afterSave.current = false;
                    setNews(null);
                    setOpen(true);
                  }}
                >
                  {inForce ? t("change") : t("set")}
                </Button>
              ) : null}
            </CardHeading>
            {/* Until the first answer, through the store's own tries too (worker-page.tsx). */}
            {rates.isPending ? (
              <p role="status">{loginWords("waiting")}</p>
            ) : null}
            {/* A failed read keeps the rates last read, with the reason above them. */}
            <ApiErrorAlert error={rates.error} />
            {answer ? (
              <>
                <p className="font-semibold">
                  {inForce
                    ? t("now", {
                        amount: amountOf(inForce),
                        meals: t(mealsOf(inForce)),
                      })
                    : t("none")}
                </p>
                {answer.rates.length > 0 ? (
                  <section aria-labelledby={historyId} className="grid gap-2">
                    <h3 id={historyId} className="font-semibold">
                      {t("history")}
                    </h3>
                    {/* Newest first, as the server sends them. role="list" written out, as Safari with VoiceOver stops
                      calling a styled <ul> a list. */}
                    <ul role="list" className="grid gap-2">
                      {answer.rates.map((rate) => {
                        // The line whole, from the books, its " · " too, as Sasa's is: each book orders its parts.
                        const parts = {
                          day: formatDay(rate.effective_from),
                          amount: amountOf(rate),
                          meals: t(mealsOf(rate)),
                        };
                        return (
                          <li key={rate.id}>
                            {rate.note === ""
                              ? t("line", parts)
                              : t("lineWithNote", {
                                  ...parts,
                                  note: rate.note,
                                })}
                          </li>
                        );
                      })}
                    </ul>
                  </section>
                ) : null}
              </>
            ) : null}
          </div>
          {/* Always on the page, empty and hidden until something happens: a role="status" box is read when its words
            change, and one that appears with its words already in it may not be read at all (worker-roles.tsx). */}
          <div
            ref={newsLine}
            tabIndex={-1}
            className={news ? "outline-none" : "sr-only"}
          >
            <Alert kind="info">
              {news ? <AlertDescription>{news}</AlertDescription> : null}
            </Alert>
          </div>
          {open && answer && mayChange ? (
            <PayRateForm
              worker={worker}
              rates={answer}
              onDone={(sentence) => {
                afterSave.current = true;
                setOpen(false);
                setNews(sentence);
              }}
              onCancel={() => {
                setOpen(false);
                // Asked again: a save whose answer was lost may have been made (worker-roles.tsx).
                void store.invalidateQueries({ queryKey: PAY_RATES });
              }}
              // After a save, the done line; after Ghairi, the button itself, named (worker-actions.tsx).
              finalFocus={() =>
                afterSave.current ? newsLine.current : button.current
              }
            />
          ) : null}
        </section>
      </CardContent>
    </Card>
  );
}

/** A rate's amount as the shop writes money: "TSh 10,000". */
function amountOf(rate: PayRate): string {
  return formatMoney(new Decimal(rate.daily_rate));
}

/** Whether the worker shares the meals, as the words' key under workers.pay. */
function mealsOf(rate: PayRate): "meals.yes" | "meals.no" {
  return rate.shares_meals ? "meals.yes" : "meals.no";
}
