// worker-day.tsx — one day of a worker's month, open under their calendar (ATT-12, 03 §5.10), as Jack approved it
// (20 Nov 2026):
//
//   Alhamisi 12/11/2026
//   ! Inahitaji uamuzi
//   Kwa nini: hakuna Toka
//   Ingia 07:20 asubuhi · Laptop ya Dawa
//   [ the photo ]
//   Hakuna Toka.
//
// Its status, and its fine on a day with one; their share of the day's meal money, *Chakula: TSh 1,000*, where there is
// one (WAGE-7); why it waits, on a day to decide, with the worker's working days for a
// day outside them; then each tap, Ingia or Toka, its time on the shop's clock with its part of the day (SYNC-11),
// the laptop, why the tap itself is in doubt, and its photo, or why there is none. Today says it isn't over, and shows
// its taps as they came.
//
// A day that is over is decided from here (ATT-6), as Jack pictured it (20 Nov 2026): *Amua siku hii* opens the sheet
// (decide-day.tsx); once decided, the day shows the decision first, who made it and when, its reason, then what the
// system worked out (*Mfumo ulisema:*), which stays (A2), and *Badilisha uamuzi*:
//
//   ✓ Siku kamili · uamuzi wa Baba, 20/11/2026
//   Sababu: Alisahau kubonyeza Toka
//   Mfumo ulisema: Inahitaji uamuzi · hakuna Toka
//   [ Badilisha uamuzi ]
//
// The button shows only where the server offers choices: never on a day the shop was shut, nor on the viewer's own
// month, which says its days aren't theirs to decide (Jack: A), in words true for the owner's own month too.
//
// A tap is fixed from here too (ATT-13), as Jack pictured it (21 Nov 2026): *Batilisha* under a tap that counts opens
// the sheet that crosses it out (void-tap.tsx); a tap crossed out stays on the day, struck through, with who, when and
// why, and counts for nothing (A2), so the day says what is missing as if it weren't there. A day decided before one of
// its taps changed keeps its decision, which says so, for whoever looks to decide it again (Jack: A):
//
//   Ingia 07:20 asubuhi · Laptop ya Dawa
//   [ Batilisha ]
//   ~~Toka 10:00 asubuhi · Laptop ya Dawa~~
//   Imebatilishwa na Baba, 19/11/2026 · Sababu: Alibonyeza kwa makosa
//   Hakuna Toka.
//
// Under the taps, *Ongeza Ingia au Toka* opens the sheet that adds one a worker forgot (add-tap.tsx), on any of the
// job's days up to today but a Sunday, as the server takes it; the tap added says who added it, when and why:
//
//   Toka 18:45 jioni · imeongezwa na Baba, 19/11/2026
//   Sababu: Alisahau kubonyeza Toka
//   Hakuna picha: imeongezwa ofisini
//   [ Ongeza Ingia au Toka ]
//
// No button on the viewer's own month, as nobody fixes their own taps; the server refuses them all the same.
//
// Everything comes from the server's one answer for the month (worker-month.ts): the page never works out what a day
// was, nor moves a time by the phone's zone. The photo is opened from its own route, which asks attendance.manage
// again and keeps no copy (CTRL-3), and only once the answer says its file came: a photo still on its way, or taken
// away, says so in words, never as a broken picture; and one that came but can't be opened now, as the phone went
// offline or the login ended while the page was open, says that instead (ATT-12's review).
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import Image from "next/image";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { Decimal } from "@/lib/decimal";
import { Button } from "@/components/design/button";
import {
  clockPart,
  formatDate,
  formatDay,
  formatMoney,
  weekdayOf,
} from "@/lib/format";
import { photoAddress } from "@/lib/photo-address";

import type { Weekday } from "./attendance-month";
import { AddTap } from "./add-tap";
import { DecideDay } from "./decide-day";
import { VoidTap } from "./void-tap";
import type {
  AttendanceTap,
  WorkerAttendance,
  WorkerDay,
} from "./worker-month";

export function TheDay({
  day,
  answer,
  timezone,
}: {
  day: string;
  answer: WorkerAttendance;
  /** The shop's zone, for the date a decision was made on; none while the page doesn't know the shop yet. */
  timezone: string | null;
}) {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  const headingId = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  // The day as the book kept it, or none for today, which the book keeps only once it is over.
  const kept = answer.days.find((each) => each.date === day);
  const isToday = day === answer.today;
  // The day's taps, in the order they were made, as the server sent them, the crossed-out ones too, struck through
  // (ATT-13); and those that count, without them, for what the day is missing.
  const taps = answer.taps.filter((tap) => tap.date === day);
  const counted = taps.filter((tap) => tap.voided === null);
  // Whether the sheet that adds a tap is open over the day: opened by its button, closed by Ghairi or once added.
  const [adding, setAdding] = useState(false);
  // A day opened, by a tap on the calendar or from a line of Zinahitaji uamuzi, takes the focus: a phone scrolls it
  // into view under the calendar, and a screen reader reads where it now is. Once per day opened, not each time the
  // month is asked again.
  useEffect(() => {
    heading.current?.focus();
  }, [day]);

  const title = {
    weekday: monthWords(`weekdays.${String(weekdayOf(day)) as Weekday}`),
    date: formatDay(day),
  };
  return (
    <section aria-labelledby={headingId} className="grid gap-3">
      {/* A third level: the worker's name is the first, the month the second. -1: focused by the page, never by Tab. */}
      <h3
        id={headingId}
        ref={heading}
        tabIndex={-1}
        className="rounded-sm text-lg font-semibold outline-none focus-visible:ring-3 focus-visible:ring-ring"
      >
        {isToday ? t("dayTitleToday", title) : t("dayTitle", title)}
      </h3>
      {isToday ? <p>{t("notOverYet")}</p> : null}
      {/* A day the book doesn't count, opened for its taps alone (the calendar's +): it says so. */}
      {!isToday && kept === undefined ? <p>{t("notCounted")}</p> : null}
      {kept ? <Kept day={kept} answer={answer} timezone={timezone} /> : null}
      {taps.length > 0 ? (
        // A list, named, so a screen reader says how many taps the day had. role="list" written out, as Safari with
        // VoiceOver stops calling a styled <ul> a list (workers-screen.tsx).
        <ul role="list" aria-label={t("tapsLabel")} className="grid gap-4">
          {taps.map((tap) => (
            <li key={tap.id}>
              <Tap tap={tap} answer={answer} timezone={timezone} />
            </li>
          ))}
        </ul>
      ) : null}
      <Missing kept={kept} taps={counted} isToday={isToday} />
      {mayAddOn(day, answer, kept) ? (
        <Button
          kind="second"
          size="normal"
          className="justify-self-start"
          onClick={() => setAdding(true)}
        >
          {t("addTap")}
        </Button>
      ) : null}
      {/* Mounted only while open, so a sheet closed with Ghairi forgets what was typed (as the decision's). */}
      {adding ? (
        <AddTap day={day} answer={answer} onClose={() => setAdding(false)} />
      ) : null}
    </section>
  );
}

/** Whether a tap may be added on `day`, as the server takes one (add_tap): one of the job's days, from its first to its
 * last, up to today, and never a Sunday, when the shop is shut and a tap counts nothing; and a day the book keeps, or
 * today, which it keeps once it is over: so never a day attendance was off, which the book keeps nothing for, as a tap
 * there would count nothing (ATT-13's review). Never on the viewer's own month. The server checks again, and refuses
 * with its own words. */
function mayAddOn(
  day: string,
  answer: WorkerAttendance,
  kept: WorkerDay | undefined,
): boolean {
  return (
    !answer.yours &&
    day <= answer.today &&
    answer.started_on <= day &&
    (answer.left_on === null || day <= answer.left_on) &&
    weekdayOf(day) !== SUNDAY &&
    (kept !== undefined || day === answer.today)
  );
}

/** Sunday, as weekdayOf numbers the days (JavaScript's own, Sunday 0). */
const SUNDAY = 0;

/** The day as the book kept it, or as someone decided it: the decision first, who and when, its reason, and what the
 * system said beside it (A2); else its status and fine, then why it waits, and the worker's days for one outside them.
 * Then their share of the day's meals, and the way to decide it, where the server offers one. */
function Kept({
  day,
  answer,
  timezone,
}: {
  day: WorkerDay;
  answer: WorkerAttendance;
  timezone: string | null;
}) {
  const t = useTranslations("attendanceWorker");
  // Whether the sheet is open over the day: opened by the button below, closed by Ghairi or once decided.
  const [deciding, setDeciding] = useState(false);
  return (
    <>
      {day.decision !== null ? (
        <Decided day={day} answer={answer} timezone={timezone} />
      ) : (
        <BookSays day={day} answer={answer} />
      )}
      {/* Their share of the day's meal money, as the book kept it (WAGE-7), on a day with one, whether the system or a
          person said what the day was: the same for everyone who came. */}
      {new Decimal(day.meal_share).gt("0") ? (
        <p>
          {t("meals", { amount: formatMoney(new Decimal(day.meal_share)) })}
        </p>
      ) : null}
      {day.choices.length > 0 ? (
        <Button
          kind={day.decision === null ? "main" : "second"}
          size="normal"
          className="justify-self-start"
          onClick={() => setDeciding(true)}
        >
          {day.decision === null ? t("decide") : t("changeDecision")}
        </Button>
      ) : null}
      {/* The viewer's own month: they may see it, never decide it (Jack: A). Said on a working day, as nothing on a
          shut day waits for anyone. */}
      {answer.yours && day.status !== "off" ? <p>{t("yours")}</p> : null}
      {/* Opened afresh each time, with the decision on the screen picked and an empty reason: mounted only while open,
          so a sheet closed with Ghairi forgets what was typed. */}
      {deciding ? (
        <DecideDay
          day={day}
          answer={answer}
          open
          onClose={() => setDeciding(false)}
        />
      ) : null}
    </>
  );
}

/** What the system worked out, as ATT-12 showed it: the status and its fine, why it waits, and the worker's days for a
 * day outside them. */
function BookSays({
  day,
  answer,
}: {
  day: WorkerDay;
  answer: WorkerAttendance;
}) {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  // Asked on every drawing, never inside a condition (React's rule for its hooks).
  const statusWords = useStatusWords(day);
  const whyWords = useWhyWords(day);
  return (
    <>
      <p className="flex gap-2 text-lg">
        {/* The mark for the eye, as on the calendar; the status in words for everyone. */}
        <span aria-hidden className="font-semibold">
          {day.status === "off"
            ? t("mark.off")
            : monthWords(`mark.${day.status}`)}
        </span>
        <span>{statusWords}</span>
      </p>
      {whyWords !== null ? <p>{t("why", { why: whyWords })}</p> : null}
      {/* Outside the job's days (ATT-11): the days as they are now, for whoever decides whether to pay it. */}
      {day.reason === "outside_job" ? (
        <p>
          {answer.left_on === null
            ? t("jobFrom", { first: formatDay(answer.started_on) })
            : t("jobBetween", {
                first: formatDay(answer.started_on),
                last: formatDay(answer.left_on),
              })}
        </p>
      ) : null}
    </>
  );
}

/** A decided day: "✓ Siku kamili · uamuzi wa Baba, 20/11/2026", its reason, then what the system said (A2). */
function Decided({
  day,
  answer,
  timezone,
}: {
  day: WorkerDay;
  answer: WorkerAttendance;
  timezone: string | null;
}) {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  const decision = day.decision;
  const statusWords = useStatusWords(day);
  const whyWords = useWhyWords(day);
  if (decision === null) return null;
  // An absence by its kind, office duty paid; a late or half day with its fine, where it has one.
  const fine = new Decimal(decision.fine);
  const what = t(`decision.${decision.absence_type ?? decision.status}`);
  const words = fine.gt(new Decimal("0"))
    ? t("option.withFine", { decision: what, amount: formatMoney(fine) })
    : what;
  // On the demo, a ready reason is kept as its code (the answer's ready_reasons): said in words here.
  const ready = answer.ready_reasons.find((code) => code === decision.reason);
  const reason =
    ready === undefined ? decision.reason : t(`readyReason.${ready}`);
  // What the system worked out, kept beside the decision (A2): its status, and why it waited, if it did.
  const said =
    whyWords === null
      ? t("systemSaid", { said: statusWords })
      : t("systemSaidWhy", { said: statusWords, why: whyWords });
  return (
    <>
      <p className="flex gap-2 text-lg">
        {/* The calendar's mark for it: an absence by its kind, O, R or H; else what was decided. */}
        <span aria-hidden className="font-semibold">
          {decision.absence_type === null
            ? monthWords(`mark.${decision.status}`)
            : t(`mark.${decision.absence_type}`)}
        </span>
        <span>
          {timezone === null
            ? t("decidedByNoDate", { decision: words, by: decision.by })
            : t("decidedBy", {
                decision: words,
                by: decision.by,
                date: formatDate(decision.at, timezone),
              })}
        </span>
      </p>
      <p>{t("decisionReason", { reason })}</p>
      <p className="text-muted-foreground">{said}</p>
      {/* A tap added, arrived or crossed out after the decision (Jack: A, ATT-13): the decision stays, and says so,
          for whoever looks to decide the day again. */}
      {day.taps_changed ? (
        <p className="font-semibold">{t("tapsChanged")}</p>
      ) : null}
    </>
  );
}

/** A day's status in words, with its fine on a day with one: a late day, or a late morning's half day (the owner,
 * ATT-4). The shop's own rule, which anyone working there may read; never the worker's rate or the day's pay
 * (WAGE-1). */
function useStatusWords(day: WorkerDay): string {
  const t = useTranslations("attendanceWorker");
  const fine = new Decimal(day.fine);
  const status = t(`status.${day.status}`);
  return fine.gt(new Decimal("0"))
    ? t("statusWithFine", { status, amount: formatMoney(fine) })
    : status;
}

/** Why a day waits, as the month page's list says it, "alifika saa 09:10 asubuhi": only came_late and left_early name
 * a time, and the book keeps that tap for them (to-decide.tsx). None on a day that didn't wait. */
function useWhyWords(day: WorkerDay): string | null {
  const monthWords = useTranslations("attendanceMonth");
  const attendance = useTranslations("attendance");
  if (day.reason === null) return null;
  const tap = day.reason === "left_early" ? day.first_out : day.first_in;
  const time =
    tap === null
      ? ""
      : attendance("timeOfDay", { time: tap, part: clockPart(tap) });
  return monthWords(`reason.${day.reason}`, { time });
}

/** One tap: "Ingia 07:20 asubuhi · Laptop ya Dawa", why it is in doubt, then its photo or why there is none; struck
 * through once crossed out, with who, when and why; and the way to cross it out, while it counts (ATT-13). */
function Tap({
  tap,
  answer,
  timezone,
}: {
  tap: AttendanceTap;
  answer: WorkerAttendance;
  timezone: string | null;
}) {
  const t = useTranslations("attendanceWorker");
  const attendance = useTranslations("attendance");
  const name = answer.worker.display_name;
  // Whether the sheet that crosses it out is open over the day: opened by Batilisha, closed by Ghairi or once done.
  const [crossing, setCrossing] = useState(false);
  // The time the server trusts, with its part of the day, so nobody reads 13:20 as Swahili time (Jack, SYNC-11); or,
  // for a tap whose time it doesn't trust, the laptop's own, said to be the laptop's. A tap entered in the office
  // (ATT-13) has no laptop clock, but always the time the manager typed, trusted; the server never sends neither.
  const said = (clock: string) =>
    attendance("timeOfDay", { time: clock, part: clockPart(clock) });
  const time =
    tap.time !== null
      ? said(tap.time)
      : t("laptopTime", { time: said(tap.laptop_time ?? "") });
  const kind = t(`tapKind.${tap.kind}`);
  // A laptop's tap names its laptop; one added in the office who added it and when (ATT-13).
  const line =
    tap.entered !== null
      ? timezone === null
        ? t("tapLineEnteredNoDate", { kind, time, by: tap.entered.by })
        : t("tapLineEntered", {
            kind,
            time,
            by: tap.entered.by,
            date: formatDate(tap.entered.at, timezone),
          })
      : tap.laptop === null
        ? t("tapLineNoLaptop", { kind, time })
        : t("tapLine", { kind, time, laptop: tap.laptop });
  // Whether the browser failed to open the photo the answer said is kept: a request of its own, which the route can
  // refuse though the month was read (no network now, a login ended, the key taken away, the file gone from the disk).
  const [photoFailed, setPhotoFailed] = useState(false);
  return (
    <div className="grid gap-2">
      {/* Its laptop, or none for a tap entered in the office, which no laptop made (ATT-13). Struck through once crossed
          out (<s>, what is no longer right), with who, when and why on the line under it, which a screen reader says
          too, as it says no strike (ATT-13). */}
      <p className={tap.voided === null ? undefined : "text-muted-foreground"}>
        {tap.voided === null ? line : <s>{line}</s>}
      </p>
      {tap.voided !== null ? (
        <p>{voidedWords(tap.voided, answer, timezone, t)}</p>
      ) : null}
      {/* Why it was added: on the demo a ready reason's code, said in words. */}
      {tap.entered !== null ? (
        <p>
          {t("decisionReason", {
            reason: readyWords(tap.entered.reason, answer.ready_add_reasons, t),
          })}
        </p>
      ) : null}
      {/* The tap itself in doubt (ATT-11): its worker was suspended or gone, or a later tap's time disagrees, said in
          words of its own, as the day's "saa yake ina shaka" after "Shaka:" said doubt twice (ATT-12's review). */}
      {tap.doubt !== null ? (
        <p className="font-semibold">
          {t("doubt", { why: t(`doubtWhy.${tap.doubt}`) })}
        </p>
      ) : null}
      {tap.photo?.state === "kept" && photoFailed ? (
        <p className="text-muted-foreground">{t("photoFailed")}</p>
      ) : tap.photo?.state === "kept" ? (
        // Opened from the photo route, as the browser sends the office's login with it. Not shrunk by Next.js, which
        // a static app can't (images.unoptimized), and said so here too, so the address is the route's own wherever
        // the page runs: the laptop shrank the photo already (03 §5.13). The size is a hint for the page's layout;
        // the photo keeps its own shape.
        <Image
          unoptimized
          src={photoAddress(tap.photo.id)}
          alt={t("photoAlt", { name, kind, time })}
          width={1600}
          height={900}
          className="h-auto w-48 rounded-lg"
          onError={() => setPhotoFailed(true)}
        />
      ) : tap.photo?.state === "waiting" ? (
        <p className="text-muted-foreground">{t("photoWaiting")}</p>
      ) : tap.photo?.state === "removed" ? (
        <p className="text-muted-foreground">{t("photoRemoved")}</p>
      ) : tap.no_photo !== null ? (
        <p className="text-muted-foreground">
          {t("noPhoto", { why: t(`noPhotoWhy.${tap.no_photo}`) })}
        </p>
      ) : null}
      {/* While it counts, and never on the viewer's own month (as nobody decides their own day, ATT-6). */}
      {tap.voided === null && !answer.yours ? (
        <Button
          kind="second"
          size="normal"
          className="justify-self-start"
          onClick={() => setCrossing(true)}
        >
          {t("voidTap")}
        </Button>
      ) : null}
      {/* Mounted only while open, so a sheet closed with Ghairi forgets what was typed (as the decision's). */}
      {crossing ? (
        <VoidTap
          tap={tap}
          said={{ kind, time }}
          answer={answer}
          onClose={() => setCrossing(false)}
        />
      ) : null}
    </div>
  );
}

/** Who crossed a tap out, when and why: "Imebatilishwa na Baba, 19/11/2026 · Sababu: Alibonyeza kwa makosa". On the
 * demo the reason is a ready one's code, said in words here. */
function voidedWords(
  voided: NonNullable<AttendanceTap["voided"]>,
  answer: WorkerAttendance,
  timezone: string | null,
  t: ReturnType<typeof useTranslations<"attendanceWorker">>,
): string {
  const reason = readyWords(voided.reason, answer.ready_void_reasons, t);
  return timezone === null
    ? t("voidedByNoDate", { by: voided.by, reason })
    : t("voidedBy", {
        by: voided.by,
        date: formatDate(voided.at, timezone),
        reason,
      });
}

/** What a day that is over is missing: no tap at all on a working day, or no Ingia, or no Toka. Today isn't over, so
 * nothing is missing yet; a shut day needs no tap. */
function Missing({
  kept,
  taps,
  isToday,
}: {
  kept: WorkerDay | undefined;
  taps: AttendanceTap[];
  isToday: boolean;
}) {
  const t = useTranslations("attendanceWorker");
  if (isToday || kept === undefined || kept.status === "off") return null;
  if (taps.length === 0) return <p>{t("noTaps")}</p>;
  const hasIn = taps.some((tap) => tap.kind === "in");
  const hasOut = taps.some((tap) => tap.kind === "out");
  return (
    <>
      {hasIn ? null : <p>{t("noIn")}</p>}
      {hasOut ? null : <p>{t("noOut")}</p>}
    </>
  );
}

/** A fix's reason in words: on the demo, a ready reason's code, said in words; elsewhere the words typed. */
function readyWords(
  reason: string,
  ready: readonly string[],
  t: ReturnType<typeof useTranslations<"attendanceWorker">>,
): string {
  const code = ready.find((each) => each === reason);
  return code === undefined
    ? reason
    : t(`readyTapReason.${code as "forgot_tap" | "wrong_tap"}`);
}
