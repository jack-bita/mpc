// new-worker-screen.tsx — Mfanyakazi mpya, at /workers/new/: Ongeza's form on a page of its own (UI-11), opened from
// Ongeza on Wafanyakazi's title row. And, with the job that ended in the address (`?again=…`), Mwajiri tena Baraka:
// the same form for a worker who left and comes back (PPL-11), opened from his old job's page. Before UI-11 both forms
// opened inside a page, the list or the old job's, and pushed the rest down the manager's phone; as Jack pictured it
// (20 Nov 2026), a long form keeps a page of its own, and a short one a sheet (UI-10).
//
// The form itself is worker-form.tsx, as PPL-4, PPL-6 and PPL-11 built it: its boxes, its checks, its id, and the phone
// of a worker who left, which offers Mwajiri tena from Ongeza itself. This page gives it a title, the shop's today, the
// old job, and whether this is the demo, and says what happens once it is saved.
//
// Hifadhi lands on the new job's own page, in this page's place (router.replace), with a line on Taarifa zake there
// (page-news.ts): for a new worker, that he was added and gets a tile once he has a PIN, above Kuingia's Weka PIN
// (Jack: A, UI-10; B was back to the list); for one hired again, from either way in, "Baraka ameajiriwa tena." (Jack's
// yes to the screens, 21 Nov 2026), where before UI-11 his new page opened with none. In this page's place: the arrow
// on the new page then leads to the list, or to the old job's page, never back into a form already sent.
//
// No Ghairi (Jack's yes to the screens): the arrow leaves with nothing sent, the page's one way back, at the top (Jack,
// OPS-13). The list, or the old job's page, opened again, reads its workers again, so a send whose answer was lost and
// did add the worker shows him there, as Ghairi's read did before.
//
// Mwajiri tena opens on the old job's own read, never the list's copy shown meanwhile (placeholderData, useWorker): its
// last day bounds the new first day, and whether the person is back already decides whether there is a form at all. A
// page opened for a worker who hasn't left says so (staff.not_left); for one back already, it says so and links to his
// new job's page, as his old page does (worker-actions.tsx).
//
// Behind staff.manage on the whole shop, as the list's Ongeza is: someone without it, who came by the address, sees the
// server's own sentence for a missing key, and no form, rather than boxes the server would refuse at the end.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Card, CardContent } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import { TextLink } from "@/components/design/text-link";
import { askDemoOpen, DEMO_OPEN } from "@/features/devices/demo";
import { useWhoIsHere, type WhoIsHere } from "@/features/people/who-is-here";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { shopToday } from "@/offline/rules";

import { leaveNews } from "./page-news";
import { WorkerForm } from "./worker-form";
import {
  LIST_PAGE,
  mayManageStaff,
  useWorker,
  type Worker,
  workerPage,
} from "./workers";

export function NewWorkerScreen({ again = null }: { again?: string | null }) {
  const t = useTranslations("workers");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const codes = useCodeWords();
  const who = useWhoIsHere();
  // The job that ended, for Mwajiri tena; nothing is asked for a new worker.
  const old = useWorker(again);
  // The old job's own read has answered: not the list's copy shown meanwhile (see the top).
  const fresh = old.data !== undefined && !old.isPlaceholderData;
  // Until both answer, the old job's own read included, through the store's own tries too (workers-screen.tsx); a read
  // that failed for good waits no more, and its refusal shows.
  const waiting =
    who.isPending || (again !== null && !fresh && old.error === null);

  return (
    <div className="grid max-w-2xl gap-6">
      {/* Mwajiri tena Baraka once his old job is read, until then "Mfanyakazi", as on his page. From a bookmark, the
          arrow leads where the button was: the list, or the old job's page. */}
      <PageHeader
        title={
          again === null
            ? t("newTitle")
            : old.data
              ? t("actions.title.hireAgain", { name: old.data.display_name })
              : t("view.title")
        }
        fallback={again === null ? LIST_PAGE : workerPage(again)}
        // In this page's place, as Hifadhi goes: the form never stays in the history (page-header.tsx).
        fallbackInPlace
      />
      {/* On the page from the start, only its words change, as on the list (workers-screen.tsx). */}
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {who.data && !waiting ? (
        !mayManageStaff(who.data) ? (
          <p>{codeMessage(codes, "permission_denied")}</p>
        ) : again === null ? (
          <NewWorker me={who.data} />
        ) : (
          <>
            <ApiErrorAlert error={old.error} />
            {old.data && fresh ? (
              <HireAgain me={who.data} old={old.data} />
            ) : null}
          </>
        )
      ) : null}
    </div>
  );
}

/** Mwajiri tena, for the job that ended: the form, or why there is none. */
function HireAgain({ me, old }: { me: WhoIsHere; old: Worker }) {
  const t = useTranslations("workers.actions");
  const codes = useCodeWords();
  // Working, or suspended: nobody to hire again, as the old job's page offers no Mwajiri tena then.
  if (old.status !== "left")
    return <p>{codeMessage(codes, "staff.not_left")}</p>;
  // Back already: his new job's page, in words and a link, as his old page says it.
  if (old.hired_again_as !== null)
    return (
      <p>
        {t("back", { name: old.display_name })}{" "}
        <TextLink href={workerPage(old.hired_again_as)}>
          {t("backLink")}
        </TextLink>
      </p>
    );
  // A form of its own for each old job: as the browser's back and forward move the address between two of these pages,
  // Baraka's boxes never go to Hamisi.
  return <NewWorker key={old.id} me={me} again={old} />;
}

/** The form, once the page knows who is here: for their shop's today, and the old job, for Mwajiri tena. */
function NewWorker({ me, again }: { me: WhoIsHere; again?: Worker }) {
  const t = useTranslations("workers");
  const router = useRouter();
  // The shop's today, read as the form opens, not as the app did: a phone left on this page overnight still starts on
  // the day it was opened, as the form did inside the list. Read once, so a draw never moves a box being typed.
  const [today] = useState(() => shopToday(me.shop.timezone, Date.now()));
  // Whether this is the demo, where no worker gets a phone (PPL-10, PPL-11): once a visit, as it changes only on a
  // deploy. Unknown, or not answered, the box is on: the server refuses a phone on the demo all the same
  // (demo.phones_fixed). Mwajiri tena has no phone box, but the answer is one read a visit, kept.
  const demo = useQuery({
    queryKey: DEMO_OPEN,
    queryFn: askDemoOpen,
    staleTime: Infinity,
  });

  return (
    <Card>
      <CardContent>
        <WorkerForm
          today={today}
          again={again}
          demo={demo.data === true}
          onSaved={(worker, hiredAgain) => {
            leaveNews({
              worker: worker.id,
              card: "details",
              sentence: hiredAgain
                ? // The same person, back: he has his PIN, if he had one, as it is the person's (PPL-11).
                  t("actions.done.hireAgain", { name: worker.display_name })
                : // Said once, on his page, where Weka PIN is: a laptop shows a tile only for someone with a PIN
                  // (PPL-4's review), which Kuingia says he has not yet (PPL-12).
                  t("added", { name: worker.display_name }),
            });
            router.replace(workerPage(worker.id));
          }}
        />
      </CardContent>
    </Card>
  );
}
