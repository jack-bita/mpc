// worker-roles.tsx — a worker's roles and extra keys on their own page (PPL-8): Cheo, each role with its side,
// "Muuzaji (Dawa)"; then Ruhusa za ziada, each key given apart from a role, by its name and side, "Kuhesabu mzigo
// (Vyakula)", where PPL-6 only counted them.
//
// A card of its own under the status buttons (Jack, PPL-8: the page order), not inside the details: Badilisha hides
// the details while its form is open (worker-page.tsx), and the roles stay on the page all the same, as Badilisha
// changes none of them.
//
// What a worker holds is a role's codes plus their extra keys, on each side (02 §5). The page shows them as given,
// one line each, so a manager sees exactly what was given and where.
//
// Under the lists, Ongeza kazi opens its form in the button's place (give-form.tsx). The button shows as PPL-6's do
// (the card's default): for a worker working or suspended, as a suspended one may be given a role, which counts once
// they are back (PPL-7); none for one who left, whose roles stay as history; none on one's own page, where the status
// buttons' line already says why (staff.own, worker-actions.tsx), as nobody changes their own job.
//
// After a give, one line says what it did, and that the shop's laptops learn it at their next sync, as a worker's keys
// travel on their staff row (SYNC-15); the keyboard goes to it, as after the status buttons. Ghairi gives the keyboard
// back to the button, and reads the worker again: a give whose answer was lost may have been made.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { type UseQueryResult, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { Alert, AlertDescription } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { Card, CardContent } from "@/components/design/card";
import type { WhoIsHere } from "@/features/people/who-is-here";

import { GiveForm } from "./give-form";
import { EVERY_KEY, type GivenKey, isPermission, useKeyWords } from "./keys";
import { type Role, useRoleWords, type Worker, WORKERS } from "./workers";

/** The form open, if any. */
type Open = { form: "give" };

export function WorkerRoles({
  worker,
  me,
  roles,
  onGiving,
}: {
  worker: Worker;
  me: WhoIsHere;
  /** The shop's roles, asked by the page once Ongeza kazi opens (onGiving) and handed down (worker-page.tsx). */
  roles: UseQueryResult<Role[]>;
  /** Ongeza kazi's form opened (true): the page asks the shop's roles from then on. */
  onGiving?: (giving: boolean) => void;
}) {
  const t = useTranslations("workers");
  const store = useQueryClient();
  const { roleOnSide } = useRoleWords(me);
  const { keyOnSide } = useKeyWords(me);
  const rolesId = useId();
  const keysId = useId();
  const [open, setOpen] = useState<Open | null>(null);
  // The line that says what the last change did, or that someone else changed the worker first.
  const [news, setNews] = useState<string | null>(null);

  // Where the keyboard goes when a form closes (worker-actions.tsx): Ghairi, back to Ongeza kazi; a change, to the
  // line that says what happened. A new object each time, so each close moves it.
  const addButton = useRef<HTMLButtonElement>(null);
  const newsLine = useRef<HTMLDivElement>(null);
  const [backTo, setBackTo] = useState<{ to: "add" | "news" } | null>(null);
  useEffect(() => {
    if (backTo === null) return;
    if (backTo.to === "news") newsLine.current?.focus();
    else addButton.current?.focus();
  }, [backTo]);

  // Who may see the buttons (see the top).
  const mayChange = worker.status !== "left" && worker.id !== me.staff.id;

  function said(sentence: string) {
    setOpen(null);
    setNews(sentence);
    setBackTo({ to: "news" });
  }

  function cancelled() {
    setOpen(null);
    setBackTo({ to: "add" });
    // Asked again: a give whose answer was lost may have been made (worker-actions.tsx).
    void store.invalidateQueries({ queryKey: WORKERS });
  }

  return (
    <Card>
      <CardContent className="grid gap-6">
        <section aria-labelledby={rolesId} className="grid gap-2">
          <h2 id={rolesId} className="text-lg font-semibold">
            {t("view.roles")}
          </h2>
          {worker.roles.length === 0 ? (
            <p>{t("noRole")}</p>
          ) : (
            // One a line: a manager on both sides reads each at a glance. role="list" written out, as Safari with
            // VoiceOver stops calling a styled <ul> a list.
            <ul role="list" className="grid gap-1">
              {worker.roles.map((given) => (
                <li key={given.id}>{roleOnSide(given)}</li>
              ))}
            </ul>
          )}
        </section>
        <section aria-labelledby={keysId} className="grid gap-2">
          <h2 id={keysId} className="text-lg font-semibold">
            {t("view.extraKeys")}
          </h2>
          {worker.keys.length === 0 ? (
            <p>{t("view.noExtraKeys")}</p>
          ) : (
            <ul role="list" className="grid gap-1">
              {inTheServersOrder(worker.keys).map((given) => (
                <li key={given.id}>{keyOnSide(given)}</li>
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
            onCancel={cancelled}
          />
        ) : (
          <div>
            <Button
              ref={addButton}
              kind="second"
              onClick={() => {
                setNews(null);
                setOpen({ form: "give" });
                onGiving?.(true);
              }}
            >
              {t("giving.add")}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** The keys in the order permissions.py lists their codes, so selling's come first and the page reads the same each
 * time; one code on two sides keeps the server's order between them. A code this app doesn't know yet comes last. */
function inTheServersOrder(keys: GivenKey[]): GivenKey[] {
  const place = (code: string) =>
    isPermission(code) ? EVERY_KEY.indexOf(code) : EVERY_KEY.length;
  // A copy: sort() changes the array it is given, and this one is the store's.
  return [...keys].sort((a, b) => place(a.permission) - place(b.permission));
}
