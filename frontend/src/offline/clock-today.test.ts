// clock-today.test.ts — which taps were made "today" (SYNC-11, 02 §12): the shop's day, in the shop's own
// time zone, by this laptop's clock, the same clock its taps are written with; and the day turns at
// midnight by itself, with nothing saved or pulled.
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import { DAWA_LAPTOP } from "@/test/devices";

import {
  DAY_CHECK_EVERY,
  dayWindow,
  peopleToday,
  type Tap,
  tapsOnDay,
  useClockDay,
} from "./clock-today";
import type { DocumentRow } from "./db";

// Fake people's ids: made up.
const ASHA = "019a5e00-0000-7000-8000-0000000000c2";
const JUMA = "019a5e00-0000-7000-8000-0000000000c3";
const SERVER_TIME = "2026-11-13T04:00:00Z";

/** A clock document as the laptop saved it, made at `at` by its clock (UTC, with Z). */
function tap(
  id: string,
  at: string,
  kind: "in" | "out",
  by = ASHA,
): DocumentRow {
  return {
    id,
    type: "clock",
    schema_version: 1,
    client_time: at,
    created_by: by,
    payload: { kind, last_server_time: SERVER_TIME },
  };
}

const DAR = "Africa/Dar_es_Salaam";

describe("the taps of a day", () => {
  it("keeps the taps made on the shop's day, in its own zone, in their order", () => {
    // Dar is 3 hours ahead of UTC: 20:59 UTC on the 12th is 23:59 there, still the 12th; 21:01 UTC is
    // 00:01 on the 13th.
    const documents = [
      tap(
        "019a5e00-0000-7000-8000-000000000201",
        "2026-11-12T20:59:00.000Z",
        "out",
      ),
      tap(
        "019a5e00-0000-7000-8000-000000000202",
        "2026-11-12T21:01:00.000Z",
        "in",
      ),
      tap(
        "019a5e00-0000-7000-8000-000000000203",
        "2026-11-13T15:02:00.000Z",
        "out",
        JUMA,
      ),
    ];

    expect(tapsOnDay(documents, DAR, "2026-11-13")).toEqual([
      {
        id: "019a5e00-0000-7000-8000-000000000202",
        staffId: ASHA,
        kind: "in",
        at: "2026-11-12T21:01:00.000Z",
      },
      {
        id: "019a5e00-0000-7000-8000-000000000203",
        staffId: JUMA,
        kind: "out",
        at: "2026-11-13T15:02:00.000Z",
      },
    ]);
  });

  it("leaves out a document whose payload isn't a tap's", () => {
    // A damaged row, or one an older or newer app wrote: never a tap of nobody's kind.
    const broken = {
      ...tap(
        "019a5e00-0000-7000-8000-000000000204",
        "2026-11-13T05:00:00.000Z",
        "in",
      ),
      payload: { kind: "lunch" },
    };

    expect(tapsOnDay([broken], DAR, "2026-11-13")).toEqual([]);
  });

  it("reads its window wide enough for any shop's zone", () => {
    // From 14 hours ahead of UTC (Kiritimati) to 12 hours behind: a shop anywhere finds all of its day.
    const [from, to] = dayWindow("2026-11-13");
    // 00:00 of the 13th in Kiritimati (+14) is 10:00 UTC on the 12th; 23:59 of the 13th at -12 is 11:59 UTC
    // on the 14th. Both inside, as ISO texts with Z compare as the times they name.
    expect(from <= "2026-11-12T10:00:00.000Z").toBe(true);
    expect(to >= "2026-11-14T11:59:59.999Z").toBe(true);
    const kiritimati = tap(
      "019a5e00-0000-7000-8000-000000000205",
      "2026-11-12T10:30:00.000Z",
      "in",
    );
    expect(
      tapsOnDay([kiritimati], "Pacific/Kiritimati", "2026-11-13"),
    ).toHaveLength(1);
  });
});

describe("today on this laptop", () => {
  // Only the time and the timers are pretend; the clock still moves on its own.
  beforeEach(() => {
    vi.useFakeTimers({
      shouldAdvanceTime: true,
      toFake: [
        "setTimeout",
        "setInterval",
        "clearTimeout",
        "clearInterval",
        "Date",
      ],
    });
    saveDevice(DAWA_LAPTOP);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("is the shop's date, by the laptop's clock, in the shop's zone", () => {
    // 22:30 UTC on the 12th is 01:30 on the 13th in Dar, whatever zone the laptop itself is set to.
    vi.setSystemTime(new Date("2026-11-12T22:30:00Z"));

    const { result } = renderHook(() => useClockDay());

    expect(result.current).toBe("2026-11-13");
  });

  it("turns to the new day at midnight by itself, with nothing saved or pulled", async () => {
    // A screen left open across midnight: yesterday's clock-in must not keep showing Toka kazini.
    vi.setSystemTime(new Date("2026-11-12T20:59:30Z"));
    const { result } = renderHook(() => useClockDay());
    expect(result.current).toBe("2026-11-12");

    await act(() => vi.advanceTimersByTimeAsync(DAY_CHECK_EVERY));

    await waitFor(() => expect(result.current).toBe("2026-11-13"));
  });

  it("knows no day on a laptop with no shop", () => {
    saveDevice(null);

    const { result } = renderHook(() => useClockDay());

    expect(result.current).toBeUndefined();
  });
});

describe("each person's day so far", () => {
  /** A tap as the screen reads it: by whom, which kind, and when (UTC). */
  const read = (
    id: string,
    by: string,
    kind: "in" | "out",
    at: string,
  ): Tap => ({
    id,
    staffId: by,
    kind,
    at,
  });

  it("gives each person once, in the order they first came, with when they came and, if out, when they left", () => {
    // Juma came at 07:40 and is still here; Asha came at 07:55 and left at 18:02.
    const taps = [
      read(
        "019a5e00-0000-7000-8000-000000000301",
        JUMA,
        "in",
        "2026-11-13T04:40:00.000Z",
      ),
      read(
        "019a5e00-0000-7000-8000-000000000302",
        ASHA,
        "in",
        "2026-11-13T04:55:00.000Z",
      ),
      read(
        "019a5e00-0000-7000-8000-000000000303",
        ASHA,
        "out",
        "2026-11-13T15:02:00.000Z",
      ),
    ];

    expect(peopleToday(taps)).toEqual([
      { staffId: JUMA, cameAt: "2026-11-13T04:40:00.000Z", leftAt: null },
      {
        staffId: ASHA,
        cameAt: "2026-11-13T04:55:00.000Z",
        leftAt: "2026-11-13T15:02:00.000Z",
      },
    ]);
  });

  it("keeps the first clock-in, and no leaving time once she is back from lunch", () => {
    const taps = [
      read(
        "019a5e00-0000-7000-8000-000000000304",
        ASHA,
        "in",
        "2026-11-13T04:55:00.000Z",
      ),
      read(
        "019a5e00-0000-7000-8000-000000000305",
        ASHA,
        "out",
        "2026-11-13T09:30:00.000Z",
      ),
      read(
        "019a5e00-0000-7000-8000-000000000306",
        ASHA,
        "in",
        "2026-11-13T10:25:00.000Z",
      ),
    ];

    expect(peopleToday(taps)).toEqual([
      { staffId: ASHA, cameAt: "2026-11-13T04:55:00.000Z", leftAt: null },
    ]);
  });

  it("shows a clock-out with no clock-in before it, as one who forgot to clock in", () => {
    // The manager enters the missing clock-in later (ATT-6); the list shows what this laptop holds.
    const taps = [
      read(
        "019a5e00-0000-7000-8000-000000000307",
        JUMA,
        "out",
        "2026-11-13T15:10:00.000Z",
      ),
    ];

    expect(peopleToday(taps)).toEqual([
      { staffId: JUMA, cameAt: null, leftAt: "2026-11-13T15:10:00.000Z" },
    ]);
  });
});
