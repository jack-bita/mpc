// flags.ts — the flags as the office reads them (CTRL-4, 03 §5.10): the key that opens them, their place in the store of
// server answers, the list read a page at a time, and the words of a flag's kind, day and those it names.
//
// GET /api/v1/control/flags/ answers one tab, what waits or what is closed, newest found first, 50 at a time, and how
// many wait. A flag shows only to whoever may close it: flag.review on its side, or on the whole shop for a flag of no
// side (02 §13). The office home offers the button only to someone holding it somewhere; the server asks the key again
// on every read and every action.
"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useFormatter, useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import type { Weekday } from "@/features/attendance/attendance-month";
import { sidesWhere, type WhoIsHere } from "@/features/people/who-is-here";
import {
  dayPart,
  formatDate,
  formatDayMonth,
  formatTime,
  weekdayOf,
} from "@/lib/format";
import { shopToday } from "@/offline/rules";

export type FlagLine = components["schemas"]["FlagLine"];
export type Flag = components["schemas"]["Flag"];
export type FlagNote = components["schemas"]["FlagNote"];
export type FlagKind = components["schemas"]["FlagKindEnum"];
type FlagsAnswer = components["schemas"]["PaginatedFlagLineList"];

/** The list's two tabs. An explained flag still waits: only a close ends one. */
export const FLAG_STATES = ["waiting", "closed"] as const;
export type FlagState = (typeof FLAG_STATES)[number];

/** The kinds the server raises today, each with its words in the books (backend/tests/test_flag_kinds.py holds the two
 * together). The server knows more, for the cards to come: one it raised before the app had its words, as a laptop's
 * page left open over a release, reads as a flag of another kind, never as a blank. */
export const RAISED_KINDS = [
  "unverified_time",
  "suspended_staff_activity",
  "device_gap",
  "permission_break",
  "invalid_document",
] as const satisfies readonly FlagKind[];
export type RaisedKind = (typeof RAISED_KINDS)[number];

/** The key that opens a side's flags, and closes them: the Owner's and the Manager's (03 §5.8). */
export const REVIEWS_FLAGS = "flag.review";

/** The flags' place in the store of server answers. Each action asks them again. */
export const FLAGS = ["control", "flags"] as const;

/** What a person may do to a flag that waits: say why, or close it one way or the other. */
export const FLAG_ACTIONS = ["explain", "resolve", "dismiss"] as const;
export type FlagAction = (typeof FLAG_ACTIONS)[number];

/** One flag's place in the store of server answers. */
export function flagKey(id: string | null) {
  return [...FLAGS, "one", id] as const;
}

/** Tofauti, the list. */
export const FLAGS_PAGE = "/flags/";

/** A flag's own page, by its id: a query string, as the app is plain files with no page per id (ADR-0016). */
export function flagPage(id: string): string {
  return `/flags/view/?id=${id}`;
}

/** Whether the person may open Tofauti: flag.review on some side. Held on the whole shop, it is on every side too. */
export function mayReviewFlags(me: WhoIsHere): boolean {
  return sidesWhere(me, REVIEWS_FLAGS).length > 0;
}

/** What *Chuja* keeps the list to: a side by its id, or the whole shop's own, and a kind; null for each left open. */
export interface FlagFilter {
  side: string | null;
  kind: RaisedKind | null;
}

/** The whole shop's own flags, in a filter's `side` and in the address: no side's id is this word. */
export const WHOLE_SHOP = "shop";

/** The sides a person may choose between in *Chuja*: those whose flags they may close, by id, and the whole shop's own
 * for someone who may close those too, as attendance's flags are. */
export function sidesToFilter(me: WhoIsHere): {
  sides: { id: string; name: string }[];
  wholeShop: boolean;
} {
  return {
    sides: sidesWhere(me, REVIEWS_FLAGS),
    wholeShop: me.permissions.whole_shop.includes(REVIEWS_FLAGS),
  };
}

/** The filter the address names, kept to what the person may choose: an old link to a side since gone, or a kind no
 * longer known, filters by neither, rather than show an empty list that looks like good news. */
export function filterFrom(
  me: WhoIsHere,
  side: string | null,
  kind: string | null,
): FlagFilter {
  const { sides, wholeShop } = sidesToFilter(me);
  const known =
    side === WHOLE_SHOP ? wholeShop : sides.some((each) => each.id === side);
  return {
    side: known ? side : null,
    kind: RAISED_KINDS.find((each) => each === kind) ?? null,
  };
}

/** One tab's flags, kept to the filter, a page after another, from the store of server answers. Asked only while `on`:
 * the closed ones wait until their tab is opened. */
export function useFlags(state: FlagState, filter: FlagFilter, on: boolean) {
  return useInfiniteQuery({
    queryKey: [...FLAGS, "list", state, filter.side, filter.kind],
    queryFn: ({ pageParam }): Promise<FlagsAnswer> =>
      answerOf(
        api.GET("/api/v1/control/flags/", {
          params: {
            query: {
              state,
              ...(filter.side === null
                ? {}
                : filter.side === WHOLE_SHOP
                  ? { whole_shop: true }
                  : { side: filter.side }),
              ...(filter.kind === null ? {} : { kind: filter.kind }),
              ...(pageParam === null ? {} : { cursor: pageParam }),
            },
          },
        }),
      ),
    initialPageParam: null as string | null,
    // The next page's address, in full; only its cursor is ours to send back.
    getNextPageParam: (last) =>
      last.next ? new URL(last.next).searchParams.get("cursor") : null,
    enabled: on,
  });
}

/** One flag whole, for its own page, from the store of server answers; nothing is asked until the page knows which, and
 * who is here. */
export function useFlag(id: string | null, on: boolean) {
  return useQuery({
    queryKey: flagKey(id),
    queryFn: () =>
      answerOf(
        api.GET("/api/v1/control/flags/{id}/", {
          // Never null here: the query runs only once `enabled`.
          params: { path: { id: id ?? "" } },
        }),
      ),
    enabled: id !== null && on,
  });
}

/** A kind's words, "Saa yake haiaminiki". */
export function useKindWords(): (kind: FlagKind) => string {
  const t = useTranslations("flags");
  return (kind) => (isRaised(kind) ? t(`kind.${kind}`) : t("kind.another"));
}

/** Whether the app knows a kind: one the server raises today, with its words and its sentence. */
export function isRaised(kind: FlagKind): kind is RaisedKind {
  return (RAISED_KINDS as readonly FlagKind[]).includes(kind);
}

/** Those a flag names, "Asha na Neema": the browser joins them the language's own way. */
export function useNames(): (people: string[]) => string {
  const format = useFormatter();
  return (people) => format.list(people, { type: "conjunction" });
}

/** The day a moment falls on, "Jumapili 22/11", on the shop's own calendar, never the phone's. */
export function useDayWords(timezone: string): (at: string) => string {
  const t = useTranslations("flags");
  const weekdays = useTranslations("attendanceMonth.weekdays");
  return (at) => {
    const day = shopToday(timezone, Date.parse(at));
    return t("day", {
      weekday: weekdays(String(weekdayOf(day)) as Weekday),
      date: formatDayMonth(day),
    });
  };
}

/** A moment, "Jumapili 22/11/2026, saa 07:52 asubuhi", in the shop's zone: its weekday, its whole date, as a closed flag
 * may be years old, and its time with the part of the day (Jack, SYNC-11). */
export function useMomentWords(timezone: string): (at: string) => string {
  const t = useTranslations("flags");
  const attendance = useTranslations("attendance");
  const weekdays = useTranslations("attendanceMonth.weekdays");
  return (at) =>
    t("moment", {
      weekday: weekdays(
        String(weekdayOf(shopToday(timezone, Date.parse(at)))) as Weekday,
      ),
      date: formatDate(at, timezone),
      time: attendance("timeOfDay", {
        time: formatTime(at, timezone),
        part: dayPart(at, timezone),
      }),
    });
}
