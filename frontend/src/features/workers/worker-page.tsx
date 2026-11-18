// worker-page.tsx — one worker's own page, opened by tapping their name on Wafanyakazi (PPL-6): everything of theirs,
// and under it the buttons that change them (worker-actions.tsx).
//
// As Jack pictured it at PPL-4 (17 Nov 2026): tap a name and see the whole worker. Their full name, nickname, job
// title and first day; their status, and their last day once they left; each role with its side; the keys given apart
// from a role, counted (their names come with PPL-8); and whether the superuser switched them off. Later cards add
// here: the roles' buttons and the PIN (PPL-8), fixing a name (PPL-10), the photo (PPL-9), and the pay so far (WAGE-2),
// so the owner pays one who leaves at once.
//
// At /workers/view/?id=…, as the app has no [id] pages (ADR-0016): the page around it reads the id from the address
// (app/(office)/workers/view/page.tsx). It asks GET /api/v1/people/staff/{id}/, and shows the list's copy at once when
// the person came from the list (useWorker). The back arrow leads to the list when the page was opened from outside
// the app, as from a link in a message.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Card, CardContent } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import { useWhoIsHere, type WhoIsHere } from "@/features/people/who-is-here";
import { formatDay } from "@/lib/format";

import { WorkerActions } from "./worker-actions";
import { useRoleWords, useWorker, type Worker } from "./workers";

/** Where the back arrow leads when the person didn't come from inside the app. */
const THE_LIST = "/workers/";

export function WorkerScreen({ id }: { id: string | null }) {
  const t = useTranslations("workers");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  const worker = useWorker(id);
  // Until both answer the first time; with no id, nothing is asked, so nothing is waited for.
  const waiting =
    (who.isPending && who.failureCount === 0) ||
    (id !== null && worker.isPending && worker.failureCount === 0);

  return (
    <div className="grid max-w-2xl gap-6">
      {/* The worker's nickname as the title, the name the shop calls them by; until it comes, "Mfanyakazi". */}
      <PageHeader
        title={worker.data?.display_name ?? t("view.title")}
        fallback={THE_LIST}
      />
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {id === null ? <p>{t("view.noWorker")}</p> : null}
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {/* A failed read above the worker, not in their place: a refresh that fails keeps the worker last read on the
          screen, with the reason above, as on the list. Asked here alone and handed down (workers-screen.tsx says
          why: a part that mounts on a failed read asks again, round and round). */}
      {who.data && !waiting ? <ApiErrorAlert error={worker.error} /> : null}
      {who.data && worker.data && !waiting ? (
        <>
          <WorkerDetails worker={worker.data} me={who.data} />
          {/* Simamisha, Rudisha and Ameondoka, as the worker's status allows (worker-actions.tsx). */}
          <WorkerActions worker={worker.data} me={who.data} />
        </>
      ) : null}
    </div>
  );
}

/** Everything of the worker's, as label and value pairs: a description list, which a screen reader reads as pairs. */
function WorkerDetails({ worker, me }: { worker: Worker; me: WhoIsHere }) {
  const t = useTranslations("workers");
  const { roleOnSide } = useRoleWords(me);

  return (
    <Card>
      <CardContent>
        <dl className="grid gap-4">
          <Pair label={t("form.fullName")}>{worker.full_name}</Pair>
          <Pair label={t("form.nickname")}>{worker.display_name}</Pair>
          <Pair label={t("form.jobTitle")}>
            {worker.job_title === "" ? t("view.noJobTitle") : worker.job_title}
          </Pair>
          <Pair label={t("form.firstDay")}>{formatDay(worker.started_on)}</Pair>
          <Pair label={t("view.status")}>
            <span className={STATUS_LOOK[worker.status]}>
              {t(`status.${worker.status}`)}
            </span>
          </Pair>
          {worker.left_on !== null ? (
            <Pair label={t("view.lastDay")}>{formatDay(worker.left_on)}</Pair>
          ) : null}
          <Pair label={t("view.roles")}>
            {worker.roles.length === 0 ? (
              t("noRole")
            ) : (
              // One role a line: a manager on both sides reads each at a glance. role="list" written out, as Safari
              // with VoiceOver stops calling a styled <ul> a list.
              <ul role="list" className="grid gap-1">
                {worker.roles.map((given) => (
                  <li key={given.id}>{roleOnSide(given)}</li>
                ))}
              </ul>
            )}
          </Pair>
          {/* Counted only: their names come with PPL-8, which gives them. */}
          {worker.keys.length > 0 ? (
            <Pair label={t("view.extraKeys")}>
              {t("extraKeys", { count: worker.keys.length })}
            </Pair>
          ) : null}
        </dl>
        {/* Apart from the job's status (PPL-4's review): switched off in the admin, on every shop at once. */}
        {worker.switched_off ? (
          <p className="mt-4 font-semibold text-destructive">
            {t("switchedOff")}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** One label and its value. */
function Pair({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-1">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-semibold">{children}</dd>
    </div>
  );
}

/** How each status looks, as on the list: a suspension stands out, a worker who left fades. */
const STATUS_LOOK: Record<Worker["status"], string> = {
  active: "",
  suspended: "text-destructive",
  left: "text-muted-foreground",
};
