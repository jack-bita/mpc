// worker-page.tsx — one worker's own page, opened by tapping their name on Wafanyakazi (PPL-6): everything of theirs,
// and under it the buttons that change them (worker-actions.tsx).
//
// As Jack pictured it at PPL-4 (17 Nov 2026): tap a name and see the whole worker. Their full name, nickname, job
// title, first day and phone; their status, and their last day once they left; and whether the superuser switched
// them off. Badilisha turns the details into boxes, in their place (PPL-10, worker-details-form.tsx). Under the
// buttons, a card of their roles and extra keys, each by its name and side (PPL-8, worker-roles.tsx); under it, their
// daily pay rate and its history, for whoever holds settings.manage (WAGE-1, worker-pay.tsx). Later cards add here: the
// PIN and the temporary password (PPL-12), the photo (PPL-9), and the pay so far (WAGE-2), so the owner pays one who
// leaves at once.
//
// At /workers/view/?id=…, as the app has no [id] pages (ADR-0016): the page around it reads the id from the address
// (app/(office)/workers/view/page.tsx). It asks GET /api/v1/people/staff/{id}/, and shows the list's copy at once when
// the person came from the list (useWorker). The back arrow leads to the list when the page was opened from outside
// the app, as from a link in a message.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Card, CardContent } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import { askDemoOpen, DEMO_OPEN } from "@/features/devices/demo";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { formatDay, formatPhone } from "@/lib/format";

import { maySeePay, usePayRates } from "./pay-rates";
import { WorkerActions } from "./worker-actions";
import { WorkerPay } from "./worker-pay";
import { WorkerRoles } from "./worker-roles";
import { useRoles, useWorker, type Worker } from "./workers";

/** Where the back arrow leads when the person didn't come from inside the app. */
const THE_LIST = "/workers/";

export function WorkerScreen({ id }: { id: string | null }) {
  const t = useTranslations("workers");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  const worker = useWorker(id);
  // Until both answer the first time, through the store's own tries too, as on the list (workers-screen.tsx); with no
  // id, nothing is asked, so nothing is waited for. The list's copy, shown at once, is no wait (useWorker).
  const waiting = who.isPending || (id !== null && worker.isPending);
  // Badilisha's form is open: it holds the details in its boxes, so the page doesn't show them twice.
  const [editing, setEditing] = useState(false);
  // Whether this is the demo, where no worker gets a phone (Jack, PPL-10: A). Asked here, the part always on the page,
  // and handed down (PPL-6's list, #272), only once a form opens, and once a visit: it changes only on a
  // deploy, as for Jaribu demo (try-the-demo.tsx). Unknown, or not answered, the box is on: the server refuses a
  // phone on the demo all the same (demo.phones_fixed).
  const demo = useQuery({
    queryKey: DEMO_OPEN,
    queryFn: askDemoOpen,
    staleTime: Infinity,
    enabled: editing,
  });
  // Ongeza kazi's form has opened (PPL-8): the shop's roles are asked from then on, here, the part always on the page,
  // and handed down, as the demo's answer is. Opening a worker's page alone asks for none.
  const [giving, setGiving] = useState(false);
  // Each of its values read here, so the page draws again when any changes (RolesRead, workers.ts).
  const rolesRead = useRoles(giving);
  const roles = {
    data: rolesRead.data,
    error: rolesRead.error,
    isPending: rolesRead.isPending,
  };
  // The worker's pay rates (WAGE-1), for whoever may see them: asked here, the part always on the page, and handed down
  // by their values, as the roles are; asked for nobody else, as the server would refuse them.
  const seesPay = who.data !== undefined && maySeePay(who.data);
  const ratesRead = usePayRates(id, seesPay);
  const rates = {
    data: ratesRead.data,
    error: ratesRead.error,
    isPending: ratesRead.isPending,
  };
  // Which card has a form open, if any (PPL-8's review): one form at a time on the page, so a person never meets two
  // Hifadhi and two Ghairi, and a screen reader never hears the same names twice. The other cards' buttons hide
  // meanwhile. Each card's own callback, kept the same between draws, as each says "closed" as it goes (its unmount).
  const [formIn, setFormIn] = useState<"actions" | "roles" | "pay" | null>(
    null,
  );
  const actionsForm = useCallback(
    (open: boolean) =>
      setFormIn((now) => (open ? "actions" : now === "actions" ? null : now)),
    [],
  );
  const rolesForm = useCallback(
    (open: boolean) =>
      setFormIn((now) => (open ? "roles" : now === "roles" ? null : now)),
    [],
  );
  const payForm = useCallback(
    (open: boolean) =>
      setFormIn((now) => (open ? "pay" : now === "pay" ? null : now)),
    [],
  );

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
          {editing ? null : <WorkerDetails worker={worker.data} />}
          {/* Badilisha, Simamisha, Rudisha and Ameondoka, as the worker's status allows (worker-actions.tsx). */}
          <WorkerActions
            // A worker of its own: on another worker's page, as the browser's back and forward move the address, any
            // form open on the last one closes, its boxes and its version with it, so Asha's boxes never go to
            // Baraka; its unmount tells the page to show the details again (onEditing).
            key={worker.data.id}
            worker={worker.data}
            me={who.data}
            demo={demo.data === true}
            onEditing={setEditing}
            onForm={actionsForm}
            buttonsHidden={formIn !== null && formIn !== "actions"}
          />
          {/* Under the buttons, as Jack chose (PPL-8): each set of buttons beside what it changes. A worker of its own, as
              WorkerActions: Asha's open form never goes on to Baraka's page. Its key apart from WorkerActions', as two
              siblings with one key are one part to React, which then draws only one of them. */}
          <WorkerRoles
            key={`${worker.data.id}-roles`}
            worker={worker.data}
            me={who.data}
            roles={roles}
            onGiving={setGiving}
            onForm={rolesForm}
            buttonsHidden={formIn !== null && formIn !== "roles"}
          />
          {/* Under the roles, as Jack pictured it (WAGE-1), for whoever may see a worker's pay. A worker of its own, as
              the cards above: Asha's open form never goes on to Baraka's page. */}
          {seesPay ? (
            <WorkerPay
              key={`${worker.data.id}-pay`}
              worker={worker.data}
              me={who.data}
              rates={rates}
              onForm={payForm}
              buttonsHidden={formIn !== null && formIn !== "pay"}
            />
          ) : null}
        </>
      ) : null}
    </div>
  );
}

/** Everything of the worker's, as label and value pairs: a description list, which a screen reader reads as pairs. */
function WorkerDetails({ worker }: { worker: Worker }) {
  const t = useTranslations("workers");

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
          {/* As the shop writes it, 0712 345 678; for whoever manages the workers, never a laptop (PPL-10). */}
          <Pair label={t("form.phone")}>
            {worker.phone === null
              ? t("view.noPhone")
              : formatPhone(worker.phone)}
          </Pair>
          <Pair label={t("view.status")}>
            <span className={STATUS_LOOK[worker.status]}>
              {t(`status.${worker.status}`)}
            </span>
          </Pair>
          {worker.left_on !== null ? (
            <Pair label={t("view.lastDay")}>{formatDay(worker.left_on)}</Pair>
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
