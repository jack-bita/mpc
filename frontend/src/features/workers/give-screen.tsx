// give-screen.tsx — Ongeza kazi kwa Juma, at /workers/give/?id=…: Ongeza kazi's form on a page of its own (UI-11),
// opened from Ongeza kazi on Cheo's heading row. Before UI-11 the form opened under the worker's roles, its six roles or
// 38 keys and its sides pushing the rest of the page down the manager's phone; as Jack pictured it (20 Nov 2026), a long
// form keeps a page of its own.
//
// The form itself is give-form.tsx, as PPL-8 built it: Anapewa nini?, the role or the key, the side, what the giver may
// give, the give's own id, and every refusal. This page gives it a title, the worker, and the shop's roles, which it
// asks itself, in the part always on the page, and hands down as values (RolesRead, PPL-8's review): the worker's page
// no longer asks them at all.
//
// Given, it goes where the page's arrow goes, back to the worker's page (backToWorker), and leaves its line for Cheo
// there, with the keyboard on it (page-news.ts): "Juma amepewa Muuzaji (Dawa). Kompyuta za duka zitajua baada ya
// kusawazisha."; or, Juma having been marked left since, staff.left's sentence, as the worker's page reads him again.
// No Ghairi (Jack's yes to the screens, 21 Nov 2026): the arrow leaves with nothing sent.
//
// The page's title takes the keyboard as the form shows, so a screen reader says what opened, as the form's own title
// did inside the worker's page (PPL-8); the first question is a list of choices, which a keyboard would otherwise pick
// from by landing on it.
//
// The form opens on Juma's own read, never the list's copy shown meanwhile (placeholderData, useWorker): what he holds
// already decides what the lists offer (giving.ts). A page opened from its address for a worker it can't act on says
// why in place of the form, in the server's own sentence, as the worker's page offers no Ongeza kazi there: one's own
// job (staff.own) or a worker who left (staff.left), whose roles stay as history.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useRouter } from "next/navigation";
import { type RefObject, useEffect, useRef } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Card, CardContent } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import { useWhoIsHere, type WhoIsHere } from "@/features/people/who-is-here";
import { codeMessage, useCodeWords } from "@/i18n/codes";

import { GiveForm } from "./give-form";
import { leaveNews } from "./page-news";
import {
  backToWorker,
  LIST_PAGE,
  type RolesRead,
  useRoles,
  useWorker,
  type Worker,
  workerPage,
} from "./workers";

export function GiveScreen({ id }: { id: string | null }) {
  const t = useTranslations("workers");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const codes = useCodeWords();
  const who = useWhoIsHere();
  const worker = useWorker(id);
  // The worker's own read has answered: not the list's copy shown meanwhile (see the top).
  const fresh = worker.data !== undefined && !worker.isPlaceholderData;
  // Until both answer, the worker's own read included, through the store's own tries too (workers-screen.tsx); a read
  // that failed for good waits no more, and its refusal shows. With no id, nothing is asked, so nothing is waited for.
  const waiting =
    who.isPending || (id !== null && !fresh && worker.error === null);
  // The shop's roles, from the page's first draw: the form shows its own wait for them, and its own refusal
  // (give-form.tsx). Each of its values read here, so the page draws again when any changes (RolesRead, workers.ts).
  const rolesRead = useRoles(id !== null);
  const roles: RolesRead = {
    data: rolesRead.data,
    error: rolesRead.error,
    isPending: rolesRead.isPending,
  };
  const heading = useRef<HTMLHeadingElement>(null);

  return (
    <div className="grid max-w-2xl gap-6">
      {/* "Ongeza kazi kwa Juma" once Juma is read; until then "Mfanyakazi", as on his page. From a bookmark, the arrow
          leads to his page, where Ongeza kazi is. */}
      <PageHeader
        title={
          worker.data
            ? t("giving.title", { name: worker.data.display_name })
            : t("view.title")
        }
        fallback={id === null ? LIST_PAGE : workerPage(id)}
        headingRef={heading}
      />
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {id === null ? <p>{t("view.noWorker")}</p> : null}
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {who.data && !waiting ? <ApiErrorAlert error={worker.error} /> : null}
      {who.data && worker.data && fresh && !waiting ? (
        worker.data.id === who.data.staff.id ? (
          <p>{codeMessage(codes, "staff.own")}</p>
        ) : worker.data.status === "left" ? (
          <p>{codeMessage(codes, "staff.left")}</p>
        ) : (
          // A form of its own for each worker: as the browser's back and forward move the address between two of these
          // pages, Juma's choices and their ids never go to Baraka.
          <Give
            key={worker.data.id}
            worker={worker.data}
            me={who.data}
            roles={roles}
            heading={heading}
          />
        )
      ) : null}
    </div>
  );
}

/** The form, for one worker, and where it goes once done. */
function Give({
  worker,
  me,
  roles,
  heading,
}: {
  worker: Worker;
  me: WhoIsHere;
  roles: RolesRead;
  /** The page's title, which takes the keyboard as the form shows (see the top). */
  heading: RefObject<HTMLHeadingElement | null>;
}) {
  const router = useRouter();
  useEffect(() => heading.current?.focus(), [heading]);

  /** Done: the line for Cheo, then back to the worker's page. */
  function back(sentence: string) {
    leaveNews({ worker: worker.id, card: "roles", sentence });
    backToWorker(router, worker.id);
  }

  return (
    <Card>
      <CardContent>
        <GiveForm
          worker={worker}
          me={me}
          roles={roles}
          onDone={back}
          onChangedMeanwhile={back}
        />
      </CardContent>
    </Card>
  );
}
