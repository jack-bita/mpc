// edit-worker-screen.tsx — Badilisha taarifa za Juma, at /workers/edit/?id=…: Badilisha's form on a page of its own
// (UI-11), opened from Badilisha on Taarifa zake's heading row. Before UI-11 the form took the details' place inside the
// worker's page and pushed the rest down the manager's phone; as Jack pictured it (20 Nov 2026), a long form keeps a page
// of its own.
//
// The form itself is worker-details-form.tsx, as PPL-10 built it: its six boxes, its checks, the version it sends, and
// the refusals beside their boxes. This page gives it a title, the worker, the shop's today, and whether this is the
// demo, and says what happens once it is done.
//
// Done, in any of three ways, it goes where the page's arrow goes, back to the worker's page (backToWorker), and leaves
// its line for Taarifa zake there, with the keyboard on it (page-news.ts): "Taarifa za Juma zimehifadhiwa."; with every
// box as it was, "Hukubadilisha chochote."; or, someone else having changed Juma since the form opened, the sentence
// that says so, as the worker's page reads him again. No Ghairi (Jack's yes to the screens, 21 Nov 2026): the arrow
// leaves with nothing sent.
//
// The form opens on Juma's own read, never the list's copy the store shows while it comes (placeholderData, useWorker):
// the version the form sends back decides whose fix wins (PPL-10), and a copy from the list may be older than the
// last fix. Once open, the form keeps the boxes and the version it opened on: a later read, as when the phone's screen
// comes back on, never fills them again (worker-details-form.tsx).
//
// A page opened from its address for a worker it can't act on says why in place of the form, in the server's own
// sentence, as the worker's page offers no Badilisha there: one's own job (staff.own) or a worker who left
// (staff.left), whose job keeps what it said then (PPL-11). Someone without staff.manage on the whole shop is refused
// the worker's read itself, and sees that refusal.
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
import { askDemoOpen, DEMO_OPEN } from "@/features/devices/demo";
import { useWhoIsHere, type WhoIsHere } from "@/features/people/who-is-here";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { shopToday } from "@/offline/rules";

import { leaveNews } from "./page-news";
import { DetailsForm } from "./worker-details-form";
import {
  backToWorker,
  LIST_PAGE,
  useWorker,
  type Worker,
  workerPage,
} from "./workers";

export function EditWorkerScreen({ id }: { id: string | null }) {
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

  return (
    <div className="grid max-w-2xl gap-6">
      {/* "Badilisha taarifa za Juma" once Juma is read; until then "Mfanyakazi", as on his page. From a bookmark, the
          arrow leads to his page, where Badilisha is. */}
      <PageHeader
        title={
          worker.data
            ? t("actions.title.edit", { name: worker.data.display_name })
            : t("view.title")
        }
        fallback={id === null ? LIST_PAGE : workerPage(id)}
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
          // pages, Asha's boxes and version never go to Baraka.
          <Fix key={worker.data.id} worker={worker.data} me={who.data} />
        )
      ) : null}
    </div>
  );
}

/** The form, for one worker, and where it goes once done. */
function Fix({ worker, me }: { worker: Worker; me: WhoIsHere }) {
  const t = useTranslations("workers.actions");
  const router = useRouter();
  // The shop's today, read once as the form opens: what a far first day is measured from (worker-details-form.tsx).
  const [today] = useState(() => shopToday(me.shop.timezone, Date.now()));
  // Whether this is the demo, where no worker gets a phone (Jack, PPL-10: A): once a visit, as it changes only on a
  // deploy. Unknown, or not answered, the box is on: the server refuses a phone on the demo all the same
  // (demo.phones_fixed).
  const demo = useQuery({
    queryKey: DEMO_OPEN,
    queryFn: askDemoOpen,
    staleTime: Infinity,
  });

  /** Done: the line for Taarifa zake, then back to the worker's page. */
  function back(sentence: string) {
    leaveNews({ worker: worker.id, card: "details", sentence });
    backToWorker(router, worker.id);
  }

  return (
    <Card>
      <CardContent>
        <DetailsForm
          worker={worker}
          today={today}
          demo={demo.data === true}
          // The worker as the server answered: their nickname as it is now.
          onDone={(changed) =>
            back(t("done.edit", { name: changed.display_name }))
          }
          onNothingChanged={() => back(t("nothingChanged"))}
          onChangedMeanwhile={back}
        />
      </CardContent>
    </Card>
  );
}
