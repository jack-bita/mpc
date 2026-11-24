// flag-words.ts — what a flag's page says in the shop's words (CTRL-4): what happened, by the flag's kind and what its
// record says of itself, and a note's words, which are the person's own, or a code the system wrote.
//
// Every sentence is a whole one in the word books, never glued from parts, so each language orders its words its own
// way. A device's missing numbers are counts of records, never money or a quantity (02 §13), kept exact all the same.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

import { codeMessage, useCodeWords } from "@/i18n/codes";
import { Decimal } from "@/lib/decimal";

import type { Flag, FlagNote } from "./flags";

/** The system's own notes (SYSTEM_NOTES, apps/control/services.py), each a code, with the words it is said in. */
const SYSTEM_NOTES = {
  "flag.device_gap_filled": "deviceGapFilled",
} as const;

/** A record's number as a person reads it: "42" of "42.000". */
function recordNumber(number: string | null): string {
  return new Decimal(number ?? "0").toFixed(0);
}

/** What happened, in a sentence, and why the server refused the record, if it did. */
export function useWhatHappened(): (flag: Flag) => {
  sentence: string;
  why: string | null;
} {
  const t = useTranslations("flags.what");
  const tapKind = useTranslations("flags.tapKind");
  const codes = useCodeWords();
  return (flag) => {
    // Whom it is about: the tap's own worker first (ATT-1), the one who loaded a file, the record's maker.
    const name = flag.people[0] ?? t("someone");
    // About loading a rescue file, not about the record in it: it names whoever loaded it (SYNC-12).
    const loaded = flag.loaded_by !== null && flag.people[0] === flag.loaded_by;
    const why =
      flag.refused_for === "" ? null : codeMessage(codes, flag.refused_for);
    const said = (sentence: string) => ({ sentence, why });
    switch (flag.kind) {
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
      default:
        // A kind newer than this app (flags.ts): its page still says who, where and when.
        return said(t("another"));
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
