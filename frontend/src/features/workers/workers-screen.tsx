// workers-screen.tsx — Wafanyakazi, the shop's workers, on the owner's phone (PPL-6, 03 §5.10): each worker's
// nickname and full name, the roles they hold with their sides, and whether they work, are suspended, or left.
//
// As Jack pictured it at PPL-4 (17 Nov 2026): the list first; a name opens the worker's own page, with everything
// of theirs and the buttons. Those still at the shop come first, newest first as the server sends them, so a worker
// just added is at the top; those who left sit under their own heading at the bottom (a default of the card), so
// the list a manager reads each day stays short as the years add names.
//
// An office screen: it asks the server through the store of server answers (rule 5), and needs the internet,
// which the office area says while it is gone. Its routes ask staff.manage on the whole shop (PPL-4); someone
// without it has no button on the office home, and opening the address shows the server's refusal.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useFormatter, useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Card } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import { useWhoIsHere, type WhoIsHere } from "@/features/people/who-is-here";

import { useRoleWords, useWorkers, type Worker } from "./workers";

export function WorkersScreen() {
  const t = useTranslations("workers");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  const workers = useWorkers();
  // Until both answer the first time: "Subiri kidogo…", never a title with nothing under it. The line is on the
  // page from the start and only its words change, as one that comes with its words in it often goes unsaid
  // (offline-banner.tsx).
  const waiting =
    (who.isPending && who.failureCount === 0) ||
    (workers.isPending && workers.failureCount === 0);

  return (
    <div className="grid max-w-2xl gap-6">
      <PageHeader title={t("title")} intro={t("intro")} />
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {/* The list is asked here alone and handed down, never asked again by the part that shows it: a part
          that mounts on a failed read asks it again (TanStack's retryOnMount), which brings the wait back,
          which takes the part away, which mounts again on the next failure, round and round, asking the
          server many times a second. */}
      {who.data && !waiting ? (
        <WorkerList me={who.data} list={workers} />
      ) : null}
    </div>
  );
}

function WorkerList({
  me,
  list,
}: {
  me: WhoIsHere;
  list: ReturnType<typeof useWorkers>;
}) {
  const t = useTranslations("workers");

  // A failed read shows above the list, not in its place: a refresh that fails (the session ended, the network
  // dropped) keeps the workers last read on the screen, with the reason above them, as on Vifaa. A first read
  // refused, as someone without staff.manage is, shows the reason alone.
  const failure = <ApiErrorAlert error={list.error} />;
  if (!list.data) return failure;
  // Two groups, each keeping the server's order. Suspended workers stay with those working: they come back.
  const here = list.data.filter((worker) => worker.status !== "left");
  const gone = list.data.filter((worker) => worker.status === "left");
  return (
    <>
      {failure}
      <Workers workers={here} me={me} />
      <section className="grid gap-3" aria-labelledby="workers-left">
        <h2 id="workers-left" className="text-lg font-semibold">
          {t("leftHeading")}
        </h2>
        {gone.length === 0 ? (
          <p>{t("noneLeft")}</p>
        ) : (
          <Workers workers={gone} me={me} />
        )}
      </section>
    </>
  );
}

/** One group of workers, in one panel, a row each. */
function Workers({ workers, me }: { workers: Worker[]; me: WhoIsHere }) {
  return (
    <Card className="py-0">
      {/* A list, so a screen reader says how many workers there are. role="list" written out: Safari with
          VoiceOver stops calling a <ul> a list once its bullets are styled away, as Tailwind does. */}
      <ul role="list" className="divide-y divide-border">
        {workers.map((worker) => (
          <li key={worker.id} className="grid gap-1 px-4 py-3">
            <WorkerRow worker={worker} me={me} />
          </li>
        ))}
      </ul>
    </Card>
  );
}

function WorkerRow({ worker, me }: { worker: Worker; me: WhoIsHere }) {
  const t = useTranslations("workers");
  const format = useFormatter();
  const { roleOnSide } = useRoleWords(me);
  // "Muuzaji (Dawa) na Keshia (Vyakula)": the browser joins them the language's own way.
  const roles =
    worker.roles.length === 0
      ? t("noRole")
      : format.list(worker.roles.map(roleOnSide), { type: "conjunction" });

  return (
    <>
      <p className="font-semibold">
        {t("names", {
          nickname: worker.display_name,
          fullName: worker.full_name,
        })}
      </p>
      <p>{roles}</p>
      {/* A key given apart from any role: counted only. Their names come with PPL-8, which gives them. */}
      {worker.keys.length > 0 ? (
        <p className="text-muted-foreground">
          {t("extraKeys", { count: worker.keys.length })}
        </p>
      ) : null}
      {/* In words, and a suspension in red too: the words alone say it, for anyone who can't tell the colours
          apart. */}
      <p className={STATUS_LOOK[worker.status]}>
        {t(`status.${worker.status}`)}
      </p>
      {/* Apart from the job's status (PPL-4's review): the superuser switched the person off in the admin, on
          every shop at once, and only he switches them on again. Working here or not, they can't log in. */}
      {worker.switched_off ? (
        <p className="font-semibold text-destructive">{t("switchedOff")}</p>
      ) : null}
    </>
  );
}

/** How each status looks: a suspension stands out, as the owner looks for it; a worker who left fades. */
const STATUS_LOOK: Record<Worker["status"], string> = {
  active: "",
  suspended: "font-semibold text-destructive",
  left: "text-muted-foreground",
};
