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
// Its status, and its fine on a day with one; why it waits, on a day to decide, with the worker's working days for a
// day outside them; then each tap, Ingia or Toka, its time on the shop's clock with its part of the day (SYNC-11),
// the laptop, why the tap itself is in doubt, and its photo, or why there is none. Today says it isn't over, and shows
// its taps as they came. It only shows: deciding the day is ATT-6's.
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
import { clockPart, formatDay, formatMoney, weekdayOf } from "@/lib/format";

import type { Weekday } from "./attendance-month";
import type {
  AttendanceTap,
  WorkerAttendance,
  WorkerDay,
} from "./worker-month";

/** The address of a photo's file, behind the photo route's key (CTRL-3). */
export function photoAddress(id: string): string {
  return `/api/v1/control/attachments/${id}/file/`;
}

export function TheDay({
  day,
  answer,
}: {
  day: string;
  answer: WorkerAttendance;
}) {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  const headingId = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  // The day as the book kept it, or none for today, which the book keeps only once it is over.
  const kept = answer.days.find((each) => each.date === day);
  const isToday = day === answer.today;
  // The day's taps, in the order they were made, as the server sent them.
  const taps = answer.taps.filter((tap) => tap.date === day);
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
      {kept ? <Kept day={kept} answer={answer} /> : null}
      {taps.length > 0 ? (
        // A list, named, so a screen reader says how many taps the day had. role="list" written out, as Safari with
        // VoiceOver stops calling a styled <ul> a list (workers-screen.tsx).
        <ul role="list" aria-label={t("tapsLabel")} className="grid gap-4">
          {taps.map((tap) => (
            <li key={tap.id}>
              <Tap tap={tap} name={answer.worker.display_name} />
            </li>
          ))}
        </ul>
      ) : null}
      <Missing kept={kept} taps={taps} isToday={isToday} />
    </section>
  );
}

/** The day as the book kept it: its status and fine, then why it waits, and the worker's days for one outside them. */
function Kept({ day, answer }: { day: WorkerDay; answer: WorkerAttendance }) {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  const attendance = useTranslations("attendance");
  // A fine only on a day with one: a late day, or a late morning's half day (the owner, ATT-4). The shop's own rule,
  // which anyone working there may read; never the worker's rate or the day's pay (WAGE-1).
  const fine = new Decimal(day.fine);
  const status = t(`status.${day.status}`);
  // The time a reason names, "alifika saa 09:10 asubuhi", as the month page's list says it (to-decide.tsx): only
  // came_late and left_early name one, and the book keeps that tap for them.
  const tap = day.reason === "left_early" ? day.first_out : day.first_in;
  const time =
    tap === null
      ? ""
      : attendance("timeOfDay", { time: tap, part: clockPart(tap) });
  return (
    <>
      <p className="flex gap-2 text-lg">
        {/* The mark for the eye, as on the calendar; the status in words for everyone. */}
        <span aria-hidden className="font-semibold">
          {day.status === "off"
            ? t("mark.off")
            : monthWords(`mark.${day.status}`)}
        </span>
        <span>
          {fine.gt(new Decimal("0"))
            ? t("statusWithFine", { status, amount: formatMoney(fine) })
            : status}
        </span>
      </p>
      {day.reason !== null ? (
        <p>{t("why", { why: monthWords(`reason.${day.reason}`, { time }) })}</p>
      ) : null}
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

/** One tap: "Ingia 07:20 asubuhi · Laptop ya Dawa", why it is in doubt, then its photo or why there is none. */
function Tap({ tap, name }: { tap: AttendanceTap; name: string }) {
  const t = useTranslations("attendanceWorker");
  const monthWords = useTranslations("attendanceMonth");
  const attendance = useTranslations("attendance");
  // The time the server trusts, with its part of the day, so nobody reads 13:20 as Swahili time (Jack, SYNC-11); or,
  // for a tap whose time it doesn't trust, the laptop's own, said to be the laptop's.
  const clock = tap.time ?? tap.laptop_time;
  const said = attendance("timeOfDay", { time: clock, part: clockPart(clock) });
  const time = tap.time === null ? t("laptopTime", { time: said }) : said;
  const kind = t(`tapKind.${tap.kind}`);
  // Whether the browser failed to open the photo the answer said is kept: a request of its own, which the route can
  // refuse though the month was read (no network now, a login ended, the key taken away, the file gone from the disk).
  const [photoFailed, setPhotoFailed] = useState(false);
  return (
    <div className="grid gap-2">
      <p>{t("tapLine", { kind, time, laptop: tap.laptop })}</p>
      {/* The tap itself in doubt (ATT-11): its worker was suspended or gone, or a later tap's time disagrees. */}
      {tap.doubt !== null ? (
        <p className="font-semibold">
          {t("doubt", { why: monthWords(`reason.${tap.doubt}`, { time: "" }) })}
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
    </div>
  );
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
