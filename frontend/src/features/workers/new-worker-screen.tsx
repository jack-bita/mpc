// new-worker-screen.tsx — Mfanyakazi mpya, at /workers/new/: Ongeza's form on a page of its own (UI-11), opened from
// Ongeza on Wafanyakazi's title row. Before UI-11 the form opened inside the list, above the workers, and pushed them
// down the manager's phone; as Jack pictured it (20 Nov 2026), a long form keeps a page of its own, and a short one a
// sheet (UI-10).
//
// The form itself is worker-form.tsx, as PPL-4, PPL-6 and PPL-11 built it: its five boxes, its checks, its id, and the
// phone of a worker who left, which offers Mwajiri tena. This page gives it a title, the shop's today, and whether this
// is the demo, and says what happens once it is saved.
//
// Hifadhi lands on the new worker's own page, in this page's place (router.replace), with the line that says he was
// added and gets a tile once he has a PIN, on Taarifa zake, above Kuingia's Weka PIN (Jack: A, UI-10; B was back to
// the list). In this page's place: the arrow on his page then leads to the list, never back into a form already sent.
// The line goes with the move as a note in the tab's memory (page-news.ts).
//
// No Ghairi (Jack's yes to the screens, 21 Nov 2026): the arrow leaves with nothing sent, the page's one way back, at
// the top (Jack, OPS-13). The list, opened again, reads its workers again, so a send whose answer was lost and did add
// the worker shows him there, as Ghairi's read did before.
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
import { askDemoOpen, DEMO_OPEN } from "@/features/devices/demo";
import { useWhoIsHere, type WhoIsHere } from "@/features/people/who-is-here";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { shopToday } from "@/offline/rules";

import { leaveNews } from "./page-news";
import { WorkerForm } from "./worker-form";
import { LIST_PAGE, mayManageStaff, workerPage } from "./workers";

export function NewWorkerScreen() {
  const t = useTranslations("workers");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const codes = useCodeWords();
  const who = useWhoIsHere();

  return (
    <div className="grid max-w-2xl gap-6">
      {/* From a bookmark, the arrow leads to the list, where Ongeza is. */}
      <PageHeader title={t("newTitle")} fallback={LIST_PAGE} />
      {/* On the page from the start, only its words change, as on the list (workers-screen.tsx). */}
      <p role="status" className={who.isPending ? "text-lg" : "sr-only"}>
        {who.isPending ? loginWords("waiting") : null}
      </p>
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {who.data ? (
        mayManageStaff(who.data) ? (
          <NewWorker me={who.data} />
        ) : (
          <p>{codeMessage(codes, "permission_denied")}</p>
        )
      ) : null}
    </div>
  );
}

/** The form, once the page knows who is here: for their shop's today. */
function NewWorker({ me }: { me: WhoIsHere }) {
  const t = useTranslations("workers");
  const router = useRouter();
  // The shop's today, read as the form opens, not as the app did: a phone left on this page overnight still starts on
  // the day it was opened, as the form did inside the list. Read once, so a draw never moves a box being typed.
  const [today] = useState(() => shopToday(me.shop.timezone, Date.now()));
  // Whether this is the demo, where no worker gets a phone (PPL-10, PPL-11): once a visit, as it changes only on a
  // deploy. Unknown, or not answered, the box is on: the server refuses a phone on the demo all the same
  // (demo.phones_fixed).
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
          demo={demo.data === true}
          onSaved={(worker) => {
            // Said once, on his page, where Weka PIN is: a laptop shows a tile only for someone with a PIN (PPL-4's
            // review), which Kuingia says he has not yet (PPL-12).
            leaveNews({
              worker: worker.id,
              card: "details",
              sentence: t("added", { name: worker.display_name }),
            });
            router.replace(workerPage(worker.id));
          }}
        />
      </CardContent>
    </Card>
  );
}
