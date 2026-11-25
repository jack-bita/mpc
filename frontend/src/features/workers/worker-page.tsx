// worker-page.tsx — one worker's own page, opened by tapping their name on Wafanyakazi (PPL-6): everything of theirs,
// in six headed cards, each with the buttons that change what it shows (UI-10).
//
// As Jack pictured it at PPL-4 (17 Nov 2026): tap a name and see the whole worker. Since UI-10 (20 Nov 2026, his
// "professional"), cards, each under its heading, so a manager's phone finds each thing by its name:
//   - Picha: their face, or that there is none, with Piga picha and Chagua picha (PPL-9, worker-photo.tsx);
//   - Taarifa zake: their full name, nickname, job title, first day and phone; their status, and their last day once
//     they left; and whether the superuser switched them off. Badilisha on the heading's row opens the details' form on
//     a page of its own (PPL-10, UI-11, edit-worker-screen.tsx); under them, the status's buttons (worker-actions.tsx);
//   - Kuingia: whether they have a PIN, Weka PIN and Nenosiri la muda (PPL-12, worker-logins.tsx);
//   - Cheo: their roles, then their extra keys, each by its name and side, with Ongeza kazi on the heading's row,
//     which opens its form on a page of its own (PPL-8, UI-11, worker-roles.tsx, give-screen.tsx);
//   - Malipo kwa siku: their daily pay rate and its history, for whoever holds settings.manage and staff.manage
//     (WAGE-1, worker-pay.tsx);
//   - Malipo ya mwezi: the month's pay so far, line by line, for them too, so the owner pays one who leaves at once
//     (WAGE-2, worker-month-pay.tsx).
//
// At /workers/view/?id=…, as the app has no [id] pages (ADR-0016): the page around it reads the id from the address
// (app/(office)/workers/view/page.tsx). It asks GET /api/v1/people/staff/{id}/, and shows the list's copy at once when
// the person came from the list (useWorker). The back arrow leads to the list when the page was opened from outside
// the app, as from a link in a message.
//
// A long form's own page lands here once it is saved (UI-11), and leaves the line that says what it did as a note
// (page-news.ts): the page takes it as it opens, and the card it names shows it, with the keyboard on it.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { PageHeader } from "@/components/design/page-header";
import { monthOf } from "@/features/attendance/attendance-month";
import { usePagesClock } from "@/features/attendance/month-switch";
import { askDemoOpen, DEMO_OPEN } from "@/features/devices/demo";
import { useWorkerPay } from "@/features/pay/pay";
import { useWhoIsHere } from "@/features/people/who-is-here";
import { formatDay, formatPhone } from "@/lib/format";
import { shopToday } from "@/offline/rules";

import { forgetNews, type PageNews, peekNews } from "./page-news";
import { maySeePay, usePayRates } from "./pay-rates";
import { WorkerActions } from "./worker-actions";
import { WorkerLogins } from "./worker-logins";
import { WorkerMonthPay } from "./worker-month-pay";
import { WorkerPay } from "./worker-pay";
import { WorkerPhoto } from "./worker-photo";
import { WorkerRoles } from "./worker-roles";
import { LIST_PAGE, useWorker, type Worker } from "./workers";

export function WorkerScreen({ id }: { id: string | null }) {
  const t = useTranslations("workers");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  const worker = useWorker(id);
  // Until both answer the first time, through the store's own tries too, as on the list (workers-screen.tsx); with no
  // id, nothing is asked, so nothing is waited for. The list's copy, shown at once, is no wait (useWorker).
  const waiting = who.isPending || (id !== null && worker.isPending);
  // The line a form's own page left as it landed here (UI-11, page-news.ts), kept until the cards show, as they wait
  // for the worker. Read as the page draws for a worker, and again when the address's id changes with the page still on
  // the screen (the browser's back and forward), as React's docs keep a value from an earlier draw: by then the note is
  // spent, so a line never shows twice. Forgotten once the page is on the screen, whoever it names: a note for another
  // worker never shows on theirs later.
  const [arrival, setArrival] = useState(() => ({ id, news: peekNews() }));
  if (arrival.id !== id) setArrival({ id, news: peekNews() });
  useEffect(() => forgetNews(), [id]);
  /** The line for one card of this worker's, if the note names it. */
  const arrivedOn = (card: PageNews["card"], worker: Worker) =>
    arrival.news?.card === card && arrival.news.worker === worker.id
      ? arrival.news.sentence
      : null;
  // Whether the page offers Weka PIN and Nenosiri la muda (PPL-12), and Piga picha and Chagua picha (PPL-9): a worker
  // working or suspended, never one's own page, as the Kuingia and Picha cards decide too (worker-logins.tsx,
  // worker-photo.tsx).
  const changesOffered =
    who.data !== undefined &&
    worker.data !== undefined &&
    worker.data.status !== "left" &&
    worker.data.id !== who.data.staff.id;
  // Whether this is the demo, where nobody's PIN or password changes (Jack, PPL-12: A), and no worker's photo is kept
  // (Jack, PPL-9). Asked here, the part always on the page, and handed down (PPL-6's list, #272), only once the two
  // cards show their buttons: Kuingia's are off on the demo before anyone taps (Jack, PPL-12: A), Picha's Hifadhi, in
  // its sheet; and once a visit: it changes only on a deploy, as for Jaribu demo (try-the-demo.tsx). Unknown, or not
  // answered, they are on: the server refuses on the demo all the same (demo.logins_fixed, demo.photos_fixed).
  // Badilisha's page asks it for its phone box itself (edit-worker-screen.tsx).
  const demo = useQuery({
    queryKey: DEMO_OPEN,
    queryFn: askDemoOpen,
    staleTime: Infinity,
    enabled: changesOffered,
  });
  // The worker's pay rates (WAGE-1), for whoever may see them: asked here, the part always on the page, and handed down
  // by their values (RolesRead, workers.ts); asked for nobody else, as the server would refuse them. The shop's roles
  // are asked by Ongeza kazi's own page (give-screen.tsx, UI-11): opening a worker's page asks for none.
  const seesPay = who.data !== undefined && maySeePay(who.data);
  const ratesRead = usePayRates(id, seesPay);
  const rates = {
    data: ratesRead.data,
    error: ratesRead.error,
    isPending: ratesRead.isPending,
  };
  // The month's pay (WAGE-2), for them too: this month on the shop's clock, as the page opened, until ‹ › chooses another
  // for this worker; on another worker's page, as the browser's back and forward move the address, this month again.
  const { openedAt, now } = usePagesClock();
  const thisMonthAt = (moment: number) =>
    who.data ? monthOf(shopToday(who.data.shop.timezone, moment)) : null;
  const thisMonth = thisMonthAt(now);
  const [chosen, setChosen] = useState<{ id: string; month: string }>();
  const payOf =
    chosen !== undefined && chosen.id === id
      ? chosen.month
      : thisMonthAt(openedAt);
  // Asked for nobody else, as the server would refuse it.
  const payRead = useWorkerPay(seesPay ? id : null, payOf);
  const monthPay = {
    data: payRead.data,
    error: payRead.error,
    isPending: payRead.isPending,
  };
  // No form opens inside this page (UI-11): the four long ones have pages of their own, and the short ones are sheets,
  // which shut the page off behind them (UI-10). So one change is made at a time with no rule of the page's own, where
  // until UI-11 an open form in the page hid the other cards' buttons (PPL-8's review).

  return (
    <div className="grid max-w-2xl gap-6">
      {/* The worker's nickname as the title, the name the shop calls them by; until it comes, "Mfanyakazi". */}
      <PageHeader
        title={worker.data?.display_name ?? t("view.title")}
        fallback={LIST_PAGE}
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
          {/* First, as Jack drew it (PPL-9): the face says whose page this is. A worker of its own, as each card: a
              photo picked for Asha never goes on to Baraka's page. */}
          <WorkerPhoto
            key={`${worker.data.id}-photo`}
            worker={worker.data}
            me={who.data}
            demo={demo.data === true}
          />
          {/* Taarifa zake: the details, and Badilisha, Simamisha, Rudisha and Ameondoka, as the worker's status allows
              (worker-actions.tsx). */}
          <WorkerActions
            // A worker of its own: on another worker's page, as the browser's back and forward move the address, any
            // form open on the last one closes, its boxes with it, so Asha's boxes never go to Baraka.
            key={worker.data.id}
            worker={worker.data}
            me={who.data}
            details={<WorkerDetails worker={worker.data} />}
            arrived={arrivedOn("details", worker.data)}
          />
          {/* Between the status buttons and the roles, as Jack chose (PPL-12: A): a way in is neither. A worker of its
              own, as each card: Asha's open form never goes on to Baraka's page. */}
          <WorkerLogins
            key={`${worker.data.id}-logins`}
            worker={worker.data}
            me={who.data}
            demo={demo.data === true}
          />
          {/* Under Kuingia, as Jack chose (PPL-8, PPL-12): each set of buttons beside what it changes. A worker of its
              own, as WorkerActions: Asha's open form never goes on to Baraka's page. Its key apart from WorkerActions',
              as two siblings with one key are one part to React, which then draws only one of them. */}
          <WorkerRoles
            key={`${worker.data.id}-roles`}
            worker={worker.data}
            me={who.data}
            arrived={arrivedOn("roles", worker.data)}
          />
          {/* Under the roles, as Jack pictured it (WAGE-1), for whoever may see a worker's pay. A worker of its own, as
              the cards above: Asha's open form never goes on to Baraka's page. */}
          {seesPay ? (
            <WorkerPay
              key={`${worker.data.id}-pay`}
              worker={worker.data}
              me={who.data}
              rates={rates}
            />
          ) : null}
          {/* Under it, as Jack pictured it (WAGE-2): what a day pays, then what the month comes to. */}
          {seesPay && id !== null && payOf !== null && thisMonth !== null ? (
            <WorkerMonthPay
              month={payOf}
              thisMonth={thisMonth}
              onChoose={(month) => setChosen({ id, month })}
              timezone={who.data.shop.timezone}
              read={monthPay}
            />
          ) : null}
        </>
      ) : null}
    </div>
  );
}

/** Everything of the worker's, as label and value pairs: a description list, which a screen reader reads as pairs.
 * Drawn inside Taarifa zake's card, under its heading (worker-actions.tsx). */
function WorkerDetails({ worker }: { worker: Worker }) {
  const t = useTranslations("workers");

  return (
    <div>
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
    </div>
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
