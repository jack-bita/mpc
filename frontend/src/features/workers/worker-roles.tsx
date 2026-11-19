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
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useId } from "react";
import { useTranslations } from "use-intl";

import { Card, CardContent } from "@/components/design/card";
import type { WhoIsHere } from "@/features/people/who-is-here";

import { EVERY_KEY, type GivenKey, isPermission, useKeyWords } from "./keys";
import { useRoleWords, type Worker } from "./workers";

export function WorkerRoles({ worker, me }: { worker: Worker; me: WhoIsHere }) {
  const t = useTranslations("workers");
  const { roleOnSide } = useRoleWords(me);
  const { keyOnSide } = useKeyWords(me);
  const rolesId = useId();
  const keysId = useId();

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
