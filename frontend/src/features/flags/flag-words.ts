// flag-words.ts — what a flag's page says in the shop's words (CTRL-4): what happened, by the flag's kind and what its
// record says of itself, and a note's words, which are the person's own, or a code the system wrote.
//
// Every sentence is a whole one in the word books, never glued from parts, so each language orders its words its own
// way. A device's missing numbers are counts of records, never money or a quantity (02 §13), kept exact all the same. A
// tap that came after its day's pay was approved (WAGE-10) is said with its day, its time and the day it was sent, each
// on the shop's own clock, so the sentence takes the shop's zone.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

import type {
  MonthNumber,
  Weekday,
} from "@/features/attendance/attendance-month";
import { useRefusedRecordWords } from "@/i18n/refused-record";
import { Decimal } from "@/lib/decimal";
import { dayPart, formatDayMonth, formatTime, weekdayOf } from "@/lib/format";
import { shopToday } from "@/offline/rules";

import { type Flag, type FlagNote, isRaised } from "./flags";

/** The system's own notes (SYSTEM_NOTES, apps/control/services.py), each a code, with the words it is said in. */
const SYSTEM_NOTES = {
  "flag.device_gap_filled": "deviceGapFilled",
} as const;

/** A record's number as a person reads it: "42" of "42.000". */
function recordNumber(number: string | null): string {
  return new Decimal(number ?? "0").toFixed(0);
}

/** What happened, in a sentence, and why the server refused the record, if it did. `timezone`: the shop's, whose clock
 * a late tap's day and time are said by (WAGE-10). */
export function useWhatHappened(timezone: string): (flag: Flag) => {
  sentence: string;
  why: string | null;
} {
  const t = useTranslations("flags.what");
  const flags = useTranslations("flags");
  const tapKind = useTranslations("flags.tapKind");
  const weekdays = useTranslations("attendanceMonth.weekdays");
  const months = useTranslations("attendanceMonth.monthNames");
  const attendance = useTranslations("attendance");
  const refusedFor = useRefusedRecordWords();
  // A day as the flag's facts say it, "Jumatatu 30/11", from the shop's business date.
  const dayWords = (day: string) =>
    flags("day", {
      weekday: weekdays(String(weekdayOf(day)) as Weekday),
      date: formatDayMonth(day),
    });
  return (flag) => {
    // Whom it is about: the tap's own worker first (ATT-1), the one who loaded a file, the record's maker.
    const name = flag.people[0] ?? t("someone");
    // About loading a rescue file, not about the record in it (SYNC-12): the server says so, by the people themselves.
    const loaded = flag.about_loading;
    const why = flag.refused_for === "" ? null : refusedFor(flag.refused_for);
    const said = (sentence: string) => ({ sentence, why });
    const { kind } = flag;
    // A kind newer than this app (flags.ts): its page still says who, where and when.
    if (!isRaised(kind)) return said(t("another"));
    // No default: the type checker refuses a kind of RAISED_KINDS with no sentence here, so a card that raises one can't
    // forget it (CTRL-4's review).
    switch (kind) {
      case "unverified_time":
        return said(
          flag.tap === null
            ? t("unverifiedTime", { name })
            : t("unverifiedTap", { name, kind: tapKind(flag.tap.kind) }),
        );
      case "suspended_staff_activity":
        if (loaded) return said(t("suspendedLoaded", { name }));
        return said(
          flag.tap === null
            ? t("suspendedRecord", { name })
            : t("suspendedTap", { name, kind: tapKind(flag.tap.kind) }),
        );
      case "permission_break":
        return said(
          loaded
            ? t("permissionLoaded", { name })
            : t("permissionRecord", { name }),
        );
      case "device_gap": {
        const numbers = {
          expected: recordNumber(flag.expected),
          actual: recordNumber(flag.actual),
        };
        const missing = new Decimal(flag.difference ?? "0");
        // Below zero, the laptop's numbers went back, as after a reset: no record is missing (SYNC-5).
        return said(
          missing.lt("0")
            ? t("numbersWentBack", numbers)
            : t("recordsMissing", { ...numbers, missing: missing.toFixed(0) }),
        );
      }
      case "invalid_document":
        return said(t("recordRefused"));
      case "late_record":
        // Asha's Ingia of Monday 30/11 at 07:20, by the laptop's clock, the only time it has; sent on Wednesday 2/12,
        // when the server saw it, after November's approval. Its month is the tap's own day's.
        return said(
          flag.tap === null || flag.made_at === null
            ? t("lateRecord", { name })
            : t("lateTap", {
                name,
                kind: tapKind(flag.tap.kind),
                day: dayWords(flag.tap.day),
                time: attendance("timeOfDay", {
                  time: formatTime(flag.made_at, timezone),
                  part: dayPart(flag.made_at, timezone),
                }),
                sent: dayWords(shopToday(timezone, Date.parse(flag.raised_at))),
                month: months(flag.tap.day.slice(5, 7) as MonthNumber),
              }),
        );
    }
  };
}

/** The demo's ready notes (DEMO_NOTES, apps/control/models.py), each a code, with the words it is said in. */
const READY_NOTES = {
  asked_them: "askedThem",
  checked_laptop: "checkedLaptop",
  honest_mistake: "honestMistake",
} as const;

/** A ready note's words; one newer than this app, its code, which a person can still read out. */
export function useReadyNoteWords(): (code: string) => string {
  const t = useTranslations("flags.ready");
  return (code) =>
    code in READY_NOTES
      ? t(READY_NOTES[code as keyof typeof READY_NOTES])
      : code;
}

/** A note's words: as the person wrote them, in their language; or a code, said in the reader's: the system's own, or
 * on the demo, where every note is a ready one. */
export function useNoteWords(): (note: FlagNote, flag: Flag) => string {
  const t = useTranslations("flags.systemNote");
  const ready = useReadyNoteWords();
  return (note, flag) => {
    if (note.by === null && note.text in SYSTEM_NOTES)
      return t(SYSTEM_NOTES[note.text as keyof typeof SYSTEM_NOTES]);
    return flag.ready_notes.includes(note.text) ? ready(note.text) : note.text;
  };
}
