// health.test.ts — the rules behind the device health page (SYNC-14): synced today by the shop's own
// day, the clock's words with their 2-minute slack, and each offline period's length, a period whose end
// is before its start included.
import { describe, expect, it } from "vitest";

import {
  clockState,
  duration,
  outageLength,
  syncedToday,
  totalWorthSaying,
  weekOfOutages,
} from "./health";

const ARUSHA = "Africa/Dar_es_Salaam";

const period = (started_at: string, ended_at: string, end_unknown = false) => ({
  id: "019a8000-0000-7000-8000-000000000001",
  started_at,
  ended_at,
  end_unknown,
});

describe("a device's day", () => {
  it("has synced today when its last sync is on the shop's today", () => {
    // 14 Nov, 09:00 in Arusha (06:00 UTC); it synced at 07:40 there.
    const now = Date.parse("2026-11-14T06:00:00Z");
    expect(syncedToday("2026-11-14T04:40:00Z", ARUSHA, now)).toBe(true);
  });

  it("has not synced today when it last synced late last night, though UTC still calls it today", () => {
    // 23:50 on 13 Nov in Arusha is 20:50 UTC on the 13th; at 00:30 on the 14th there, UTC is still the 13th.
    const now = Date.parse("2026-11-13T21:30:00Z");
    expect(syncedToday("2026-11-13T20:50:00Z", ARUSHA, now)).toBe(false);
  });

  it("has not synced today when it never synced", () => {
    expect(syncedToday(null, ARUSHA, Date.now())).toBe(false);
  });
});

describe("a device's clock", () => {
  it("is not known before its first push", () => {
    expect(clockState(null)).toEqual({ kind: "unknown" });
  });

  it("is right within 2 minutes either way, the clock-ins' own slack", () => {
    expect(clockState(0)).toEqual({ kind: "right" });
    expect(clockState(120)).toEqual({ kind: "right" });
    expect(clockState(-120)).toEqual({ kind: "right" });
  });

  it("is behind or ahead past that, in whole minutes", () => {
    // The Vyakula laptop, 6 min 20 s slow; another, 2 min 1 s fast.
    expect(clockState(-380)).toEqual({ kind: "behind", minutes: 6 });
    expect(clockState(121)).toEqual({ kind: "ahead", minutes: 2 });
  });
});

describe("an offline period", () => {
  it("lasts from its start to its end", () => {
    expect(
      outageLength(period("2026-11-14T07:05:00Z", "2026-11-14T07:15:00Z")),
    ).toBe(10 * 60_000);
  });

  it("has no length when it ends before it starts, its clock put back during it", () => {
    expect(
      outageLength(period("2026-11-14T07:05:00Z", "2026-11-14T06:50:00Z")),
    ).toBeNull();
  });

  it("is said in hours and minutes, rounded to the minute, or as under a minute", () => {
    expect(duration(25 * 60_000)).toEqual({
      kind: "time",
      hours: 0,
      minutes: 25,
    });
    expect(duration(2 * 3_600_000 + 15 * 60_000 + 40_000)).toEqual({
      kind: "time",
      hours: 2,
      minutes: 16,
    });
    expect(duration(59 * 60_000 + 50_000)).toEqual({
      kind: "time",
      hours: 1,
      minutes: 0,
    });
    expect(duration(20_000)).toEqual({ kind: "underAMinute" });
  });

  it("counts in the week's total only when its length can be told", () => {
    // Two cuts of 10 and 15 minutes, and one whose clock was put back.
    expect(
      weekOfOutages([
        period("2026-11-14T07:05:00Z", "2026-11-14T07:15:00Z"),
        period("2026-11-12T12:30:00Z", "2026-11-12T12:45:00Z"),
        period("2026-11-11T08:00:00Z", "2026-11-11T07:40:00Z"),
      ]),
    ).toEqual({ count: 3, total: 25 * 60_000, atLeast: false });
  });

  it("counts a period whose end is unknown up to where it was seen, and says the total is the least", () => {
    // A 10-minute cut seen to its end, and one the laptop saw for 5 minutes before it went off.
    const week = weekOfOutages([
      period("2026-11-14T07:05:00Z", "2026-11-14T07:15:00Z"),
      period("2026-11-13T15:59:00Z", "2026-11-13T16:04:00Z", true),
    ]);
    expect(week).toEqual({ count: 2, total: 15 * 60_000, atLeast: true });
    expect(totalWorthSaying(week)).toBe(true);
  });

  it('has no total worth saying as "at least under a minute"', () => {
    // The laptop died 10 seconds into the cut: "at least under a minute" would say nothing.
    const week = weekOfOutages([
      period("2026-11-13T15:59:00Z", "2026-11-13T15:59:10Z", true),
    ]);
    expect(totalWorthSaying(week)).toBe(false);
  });

  it("has no total when no period's length can be told", () => {
    expect(
      weekOfOutages([period("2026-11-11T08:00:00Z", "2026-11-11T07:40:00Z")]),
    ).toEqual({ count: 1, total: null, atLeast: false });
  });
});
