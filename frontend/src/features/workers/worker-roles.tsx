// worker-roles.tsx — a worker's roles and extra keys on their own page (PPL-8): Cheo, each role with its side,
// "Muuzaji (Dawa)"; then Ruhusa za ziada, each key given apart from a role, by its name and side, "Kuhesabu mzigo
// (Vyakula)", where PPL-6 only counted them.
//
// A card of its own under Taarifa zake and Kuingia (Jack, PPL-8 and PPL-12: the page order), not inside the details:
// Badilisha leaves the details out while its form is open (worker-actions.tsx), and the roles stay on the page all the
// same, as Badilisha changes none of them.
//
// What a worker holds is a role's codes plus their extra keys, on each side (02 §5). The page shows them as given,
// one line each, so a manager sees exactly what was given and where.
//
// Cheo is the card's heading, and Ruhusa za ziada a heading a level under it, as the keys are part of what the worker
// may do (UI-10). On Cheo's row sits Ongeza kazi (card-heading.tsx), as it adds to the whole card, roles and keys
// alike; its form opens under the lists (give-form.tsx), and the button leaves the row meanwhile. It shows as PPL-6's do
// (the card's default): for a worker working or suspended, as a suspended one may be given a role, which counts once
// they are back (PPL-7); none for one who left, whose roles stay as history; none on one's own page, where the status
// buttons' line already says why (staff.own, worker-actions.tsx), as nobody changes their own job.
//
// Beside each role and each key, Ondoa opens its sheet over the page (end-form.tsx, UI-10), its title naming what goes;
// never beside Mmiliki, which only the superuser takes away (PPL-7, PPL-13). Shown for the same workers as Ongeza kazi.
// One change is made at a time: while Ongeza kazi's form is open in the page, no other button shows, on this card or
// the others (worker-page.tsx); while Ondoa's sheet is open, the page behind it is shut off.
//
// After a change, one line says what it did, and that the shop's laptops learn it at their next sync, as a worker's
// keys travel on their staff row (SYNC-15); the keyboard goes to it, as after the status buttons. Ghairi gives the
// keyboard back to the button that opened the form, and reads the worker again: a change whose answer was lost may
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

import { CardHeading } from "./card-heading";
import { EndForm, type Ending } from "./end-form";
import { GiveForm } from "./give-form";
import { isOwnerRole } from "./giving";
import { EVERY_KEY, type GivenKey, isPermission, useKeyWords } from "./keys";
import { type RolesRead, useRoleWords, type Worker, WORKERS } from "./workers";

/** The form open, if any: Ongeza kazi, or Ondoa of one role or key. */
type Open = { form: "give" } | { form: "end"; ending: Ending };

/** Ongeza kazi's place among the buttons the keyboard goes back to; each Ondoa's is its row's id. */
const ADD = "add";

export function WorkerRoles({
  worker,
  me,
  roles,
  onGiving,
  onForm,
  buttonsHidden = false,
}: {
  worker: Worker;
  me: WhoIsHere;
  /** The shop's roles, asked by the page once Ongeza kazi opens (onGiving) and handed down (worker-page.tsx). */
  roles: RolesRead;
  /** Ongeza kazi's form opened (true): the page asks the shop's roles from then on. */
  onGiving?: (giving: boolean) => void;
  /** A form opened (true) or closed (false): the page keeps one form open at a time (worker-page.tsx). */
  onForm?: (open: boolean) => void;
  /** Another card's form is open: this card's buttons stay off the page meanwhile (PPL-8's review). */
  buttonsHidden?: boolean;
}) {
  const t = useTranslations("workers");
  const store = useQueryClient();
  const { roleOnSide } = useRoleWords(me);
  const { keyOnSide } = useKeyWords(me);
  const rolesId = useId();
  const keysId = useId();
  const [open, setOpenHere] = useState<Open | null>(null);
  /** A form opens, or (null) closes: the page learns whether Ongeza kazi's is open in the page, for the other cards'
   * buttons. Ondoa's sheet isn't told: it shuts the whole page off behind it (UI-10). */
  function setOpen(form: Open | null) {
    setOpenHere(form);
    onForm?.(form?.form === "give");
  }
  // Gone from the page with a form open: the page lets the other card's buttons show again.
  useEffect(() => () => onForm?.(false), [onForm]);
  // The line that says what the last change did, or that someone else changed the worker first.
  const [news, setNews] = useState<string | null>(null);

  // Where the keyboard goes when a form closes (worker-actions.tsx): Ghairi, back to the button that opened it; a
  // change, to the line that says what happened, as an Ondoa's row is gone. A new object each time, so each close
  // moves it.
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const newsLine = useRef<HTMLDivElement>(null);
  const [backTo, setBackTo] = useState<{ to: string } | null>(null);
  useEffect(() => {
    if (backTo === null) return;
    if (backTo.to === "news") newsLine.current?.focus();
    else buttons.current.get(backTo.to)?.focus();
  }, [backTo]);

  // Who may see the buttons (see the top); none while Ongeza kazi's form is open in the page. They stay under Ondoa's
  // sheet, so Ghairi gives the keyboard back to the very row's Ondoa.
  const mayChange = worker.status !== "left" && worker.id !== me.staff.id;
  const showButtons = mayChange && open?.form !== "give" && !buttonsHidden;

  // Whether the last close was a change, for Ondoa's sheet to give the keyboard to the done line: read as the sheet
  // goes, after the draw that took it away, so a ref, not the state (worker-actions.tsx).
  const afterChange = useRef(false);

  function said(sentence: string) {
    afterChange.current = true;
    setOpen(null);
    setNews(sentence);
    setBackTo({ to: "news" });
  }

  function cancelled(button: string) {
    setOpen(null);
    setBackTo({ to: button });
    // Asked again: a change whose answer was lost may have been made (worker-actions.tsx).
    void store.invalidateQueries({ queryKey: WORKERS });
  }

  /** Ondoa beside a role or a key: its name for a screen reader says what goes, "Ondoa Muuzaji (Dawa)", as every row's
   * button reads "Ondoa"; the words seen are inside it, so a person who says "Ondoa" to their computer finds it. */
  function removeButton(ending: Ending) {
    return (
      <Button
        ref={(button) => {
          // Its place among the buttons, for the keyboard to come back to (worker-actions.tsx).
          if (button) buttons.current.set(ending.id, button);
          else buttons.current.delete(ending.id);
        }}
        kind="second"
        size="normal"
        aria-label={t("ending.removeWhat", { what: ending.words })}
        onClick={() => {
          afterChange.current = false;
          setNews(null);
          setOpen({ form: "end", ending });
        }}
      >
        {t("ending.remove")}
      </Button>
    );
  }

  return (
    <Card>
      <CardContent className="grid gap-6">
        <section aria-labelledby={rolesId} className="grid gap-2">
          <CardHeading id={rolesId} title={t("view.roles")}>
            {showButtons ? (
              <Button
                ref={(button) => {
                  // Its place among the buttons, for the keyboard to come back to (worker-actions.tsx).
                  if (button) buttons.current.set(ADD, button);
                  else buttons.current.delete(ADD);
                }}
                kind="second"
                // Normal, on the heading's row, which a big one would crowd (worker-actions.tsx).
                size="normal"
                onClick={() => {
                  setNews(null);
                  setOpen({ form: "give" });
                  onGiving?.(true);
                }}
              >
                {t("giving.add")}
              </Button>
            ) : null}
          </CardHeading>
          {worker.roles.length === 0 ? (
            <p>{t("noRole")}</p>
          ) : (
            // One a line: a manager on both sides reads each at a glance. role="list" written out, as Safari with
            // VoiceOver stops calling a styled <ul> a list.
            <ul role="list" className="grid gap-2">
              {worker.roles.map((given) => (
                <li key={given.id} className={ROW}>
                  <span>{roleOnSide(given)}</span>
                  {/* Never beside Mmiliki: the superuser's alone to take away (PPL-7). */}
                  {showButtons && !isOwnerRole(given)
                    ? removeButton({
                        kind: "role",
                        id: given.id,
                        words: roleOnSide(given),
                      })
                    : null}
                </li>
              ))}
            </ul>
          )}
        </section>
        {/* A section of its own, beside the roles', not inside it: each list reads alone, Cheo's without the keys. */}
        <section aria-labelledby={keysId} className="grid gap-2">
          <h3 id={keysId} className="font-semibold">
            {t("view.extraKeys")}
          </h3>
          {worker.keys.length === 0 ? (
            <p>{t("view.noExtraKeys")}</p>
          ) : (
            <ul role="list" className="grid gap-2">
              {inTheServersOrder(worker.keys).map((given) => (
                <li key={given.id} className={ROW}>
                  <span>{keyOnSide(given)}</span>
                  {showButtons
                    ? removeButton({
                        kind: "key",
                        id: given.id,
                        words: keyOnSide(given),
                      })
                    : null}
                </li>
              ))}
            </ul>
          )}
        </section>
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
        {!mayChange ? null : open?.form === "give" ? (
          <GiveForm
            worker={worker}
            me={me}
            roles={roles}
            onDone={said}
            onChangedMeanwhile={said}
            onCancel={() => cancelled(ADD)}
          />
        ) : open?.form === "end" ? (
          // A sheet, mounted only while open, so Ghairi forgets what was typed (UI-10).
          <EndForm
            worker={worker}
            ending={open.ending}
            onDone={said}
            onChangedMeanwhile={said}
            onCancel={() => cancelled(open.ending.id)}
            // After a change, the done line, as the row and its Ondoa are gone; after Ghairi, the row's Ondoa.
            finalFocus={() => (afterChange.current ? newsLine.current : null)}
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

/** A role's or a key's line: its words, and Ondoa at the far end, which wraps under them on a narrow phone. */
const ROW = "flex flex-wrap items-center justify-between gap-x-3 gap-y-1";

/** The keys in the order permissions.py lists their codes, so selling's come first and the page reads the same each
 * time; one code on two sides keeps the server's order between them. A code this app doesn't know yet comes last. */
function inTheServersOrder(keys: GivenKey[]): GivenKey[] {
  const place = (code: string) =>
    isPermission(code) ? EVERY_KEY.indexOf(code) : EVERY_KEY.length;
  // A copy: sort() changes the array it is given, and this one is the store's.
  return [...keys].sort((a, b) => place(a.permission) - place(b.permission));
}
