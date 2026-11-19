// worker-logins.tsx — Kuingia, a worker's ways in, on their own page (PPL-12): whether they have a PIN, Imewekwa or
// Haijawekwa, so the owner sees who has no tile on the shop's laptops yet; Weka PIN, for a laptop's tile
// (pin-form.tsx); and Nenosiri la muda, for one who works from their own phone (password-form.tsx). Each opens its
// form in the buttons' place.
//
// A card of its own between the status buttons and the roles (Jack, PPL-12: A): a way to log in is neither the job's
// status nor a role. The PIN's line shows for every worker; the buttons as PPL-8's do: for a worker working or
// suspended, as a suspended one may be given a PIN for when they are back; none for one who left; none on one's own
// page, where the status buttons' line already says why (staff.own), as nobody sets their own PIN here (pin.own).
// While a form is open, no other button shows, on this card or the others (worker-page.tsx), so one change is made at
// a time.
//
// On the demo (Jack, PPL-12: A), PINs and passwords stay as the seed made them, so every visitor can log in: the
// buttons are off, with demo.logins_fixed's own sentence under them, as a visitor's worker given a PIN would show his
// tile on every visitor's laptop until the night's reset (PPL-4's review). The page asks the server whether this is
// the demo and hands the answer down; unknown, or not answered, the buttons are on, and the server refuses all the
// same.
//
// After a change, one line says what it did, and the keyboard goes to it, as after the status buttons. Ghairi gives
// the keyboard back to the button that opened the form, and reads the worker again: a change whose answer was lost may
// have been made.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { Alert, AlertDescription } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { Card, CardContent } from "@/components/design/card";
import type { WhoIsHere } from "@/features/people/who-is-here";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { formatPhone } from "@/lib/format";

import { PasswordForm } from "./password-form";
import { PinForm } from "./pin-form";
import { type Worker, WORKERS } from "./workers";

/** The form open, if any. */
type Form = "pin" | "password";

/** The buttons, in their order on the card: the PIN first, as every worker at a laptop needs one. */
const FORMS: Form[] = ["pin", "password"];

export function WorkerLogins({
  worker,
  me,
  demo = false,
  onForm,
  buttonsHidden = false,
}: {
  worker: Worker;
  me: WhoIsHere;
  /** This is the demo, where nobody's PIN or password changes. */
  demo?: boolean;
  /** A form opened (true) or closed (false): the page keeps one form open at a time (worker-page.tsx). */
  onForm?: (open: boolean) => void;
  /** Another card's form is open: this card's buttons stay off the page meanwhile (PPL-8's review). */
  buttonsHidden?: boolean;
}) {
  const t = useTranslations("workers.logins");
  const codes = useCodeWords();
  const store = useQueryClient();
  const titleId = useId();
  const [open, setOpenHere] = useState<Form | null>(null);
  /** A form opens, or (null) closes: the page learns, for the other cards' buttons. */
  function setOpen(form: Form | null) {
    setOpenHere(form);
    onForm?.(form !== null);
  }
  // Gone from the page with a form open: the page lets the other cards' buttons show again.
  useEffect(() => () => onForm?.(false), [onForm]);
  // The line that says what the last change did.
  const [news, setNews] = useState<string | null>(null);

  // Where the keyboard goes when a form closes (worker-actions.tsx): Ghairi, back to the button that opened it; a
  // change, to the line that says what happened. A new object each time, so each close moves it.
  const buttons = useRef(new Map<Form, HTMLButtonElement>());
  const newsLine = useRef<HTMLDivElement>(null);
  const [backTo, setBackTo] = useState<{ to: Form | "news" } | null>(null);
  useEffect(() => {
    if (backTo === null) return;
    if (backTo.to === "news") newsLine.current?.focus();
    else buttons.current.get(backTo.to)?.focus();
  }, [backTo]);

  // Who may see the buttons (see the top); none while a form is open.
  const mayChange = worker.status !== "left" && worker.id !== me.staff.id;
  const showButtons = mayChange && open === null && !buttonsHidden;

  function said(sentence: string) {
    setOpen(null);
    setNews(sentence);
    setBackTo({ to: "news" });
  }

  function cancelled(form: Form) {
    setOpen(null);
    setBackTo({ to: form });
    // Asked again: a change whose answer was lost may have been made (worker-actions.tsx).
    void store.invalidateQueries({ queryKey: WORKERS });
  }

  return (
    <Card>
      <CardContent>
        <section aria-labelledby={titleId} className="grid gap-4">
          <h2 id={titleId} className="text-lg font-semibold">
            {t("title")}
          </h2>
          {/* A label and its value, as the worker's details are: a screen reader reads them as a pair. */}
          <dl className="grid gap-1">
            <dt className="text-muted-foreground">{t("pin")}</dt>
            <dd className="font-semibold">
              {worker.has_pin ? t("pinSet") : t("pinNotSet")}
            </dd>
          </dl>
          {/* Always on the page, empty and hidden until something happens: a role="status" box is read when its words
              change, and one that appears with its words already in it may not be read at all (offline-banner.tsx). */}
          <div
            ref={newsLine}
            tabIndex={-1}
            className={news ? "outline-none" : "sr-only"}
          >
            <Alert kind="info">
              {news ? <AlertDescription>{news}</AlertDescription> : null}
            </Alert>
          </div>
          {open === "pin" ? (
            <PinForm
              worker={worker}
              onDone={(changed) =>
                said(t("pinDone", { name: changed.display_name }))
              }
              onCancel={() => cancelled("pin")}
            />
          ) : open === "password" ? (
            <PasswordForm
              worker={worker}
              // With her phone as the shop writes it, 0712 345 678; with none, her email, which the page never sees.
              onDone={() =>
                said(
                  worker.phone === null
                    ? t("passwordDoneNoPhone", { name: worker.display_name })
                    : t("passwordDone", {
                        name: worker.display_name,
                        phone: formatPhone(worker.phone),
                      }),
                )
              }
              onCancel={() => cancelled("password")}
            />
          ) : null}
          {showButtons ? (
            <div className="grid gap-3">
              <div className="flex flex-wrap gap-3">
                {FORMS.map((form) => (
                  <Button
                    key={form}
                    ref={(button) => {
                      if (button) buttons.current.set(form, button);
                      else buttons.current.delete(form);
                    }}
                    kind="second"
                    // Off on the demo, with the line under them saying why (see the top).
                    disabled={demo}
                    onClick={() => {
                      setNews(null);
                      setOpen(form);
                    }}
                  >
                    {form === "pin" ? t("setPin") : t("temporaryPassword")}
                  </Button>
                ))}
              </div>
              {/* One line for both buttons: the server's own sentence for the demo's logins. */}
              {demo ? <p>{codeMessage(codes, "demo.logins_fixed")}</p> : null}
            </div>
          ) : null}
        </section>
      </CardContent>
    </Card>
  );
}
