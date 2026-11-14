// outages.test.ts — the laptop's offline periods (SYNC-14, 03 §6.11): one open at a time, kept up while the
// app sees the laptop cut off, closed when the server answers, and ended where the app last saw it when it
// was closed or asleep meanwhile. Every time is handed in, so each test sets the laptop's clock itself.
import Dexie from "dexie";
import { afterEach, describe, expect, it } from "vitest";

import { DAWA_LAPTOP } from "@/test/devices";

import { databaseName, openShopDatabase, type ShopDatabase } from "../db";
import { LOST_SIGHT, noteBack, noteCutOff, noteStillHere } from "./outages";

const SHOP = DAWA_LAPTOP.shop.id;

const opened: ShopDatabase[] = [];
/** The shop's database as one tab opens it: two calls are two tabs of one laptop. */
function aTab(): ShopDatabase {
  const db = openShopDatabase(SHOP);
  opened.push(db);
  return db;
}
afterEach(async () => {
  for (const db of opened.splice(0)) db.close();
  await Dexie.delete(databaseName(SHOP));
});

/** A time on the laptop's clock, on 14 Nov 2026, in UTC: "10:05" is 13:05 in Arusha; "10:14:30" has seconds. */
const at = (time: string) =>
  Date.parse(`2026-11-14T${time.length === 5 ? `${time}:00` : time}Z`);
const MINUTE = 60_000;

/** The open app's moments from `from` to `to`, every 30 s, each meeting no network (triggers.tsx). */
async function cutOffFrom(db: ShopDatabase, from: number, to: number) {
  for (let now = from; now <= to; now += 30_000) await noteCutOff(db, now);
}

/** What the push would send of each period, and whether it is still open. */
async function periods(db: ShopDatabase) {
  return (await db.outages.toArray())
    .map(({ started_at, ended_at }) => ({ started_at, ended_at }))
    .sort((a, b) => a.started_at.localeCompare(b.started_at));
}

describe("an offline period", () => {
  it("is one period of ten minutes for ten minutes offline", async () => {
    // The router goes off at 10:05 with the power; the open app notes the cut at each moment, every 30 s,
    // and the server answers again at 10:15.
    const db = aTab();
    await cutOffFrom(db, at("10:05"), at("10:14:30"));
    await noteBack(db, at("10:15"));

    expect(await periods(db)).toEqual([
      {
        started_at: "2026-11-14T10:05:00.000Z",
        ended_at: "2026-11-14T10:15:00.000Z",
      },
    ]);
  });

  it("is one period, not two, when two tabs see the same cut", async () => {
    // Mahudhurio in one tab and Kompyuta hii in another: both hear the network go at once.
    const counter = aTab();
    const other = aTab();
    await Promise.all([
      cutOffFrom(counter, at("10:05"), at("10:14:30")),
      cutOffFrom(other, at("10:05"), at("10:14:30")),
    ]);
    await Promise.all([
      noteBack(counter, at("10:15")),
      noteBack(other, at("10:15")),
    ]);

    expect(await periods(counter)).toEqual([
      {
        started_at: "2026-11-14T10:05:00.000Z",
        ended_at: "2026-11-14T10:15:00.000Z",
      },
    ]);
  });

  it("stays one period across a reload", async () => {
    // Asha reloads the page at 10:06, a minute into the cut: the page is gone for a few seconds, and the
    // app comes back still cut off, and goes on.
    const db = aTab();
    await cutOffFrom(db, at("10:05"), at("10:05:30"));
    await cutOffFrom(db, at("10:06") + 5_000, at("10:14:35"));
    await noteBack(db, at("10:15"));

    expect(await periods(db)).toEqual([
      {
        started_at: "2026-11-14T10:05:00.000Z",
        ended_at: "2026-11-14T10:15:00.000Z",
      },
    ]);
  });

  it("ends where the app last saw it, when the app was closed meanwhile", async () => {
    // Cut off at 18:30; the shop closes and the laptop is shut at 19:00; it opens at 07:30 the next
    // morning with the internet back. Nobody knows about the night: the period ends at 19:00.
    const db = aTab();
    await cutOffFrom(db, at("18:30"), at("19:00"));
    await noteBack(db, at("19:00") + 12.5 * 60 * MINUTE);

    expect(await periods(db)).toEqual([
      {
        started_at: "2026-11-14T18:30:00.000Z",
        ended_at: "2026-11-14T19:00:00.000Z",
      },
    ]);
  });

  it("keeps going while the app saw it within three minutes, and ends where it was seen after that", async () => {
    // A hidden tab's moments slow down: seen at 10:05, then 10:08, it is the same period. Seen last at
    // 10:08 and next at 10:12, the app was away: the period ended at 10:08.
    const kept = aTab();
    await noteCutOff(kept, at("10:05"));
    await noteBack(kept, at("10:05") + LOST_SIGHT);
    expect(await periods(kept)).toEqual([
      {
        started_at: "2026-11-14T10:05:00.000Z",
        ended_at: "2026-11-14T10:08:00.000Z",
      },
    ]);

    await noteCutOff(kept, at("11:00"));
    await noteBack(kept, at("11:00") + LOST_SIGHT + 1);
    expect((await periods(kept))[1]).toEqual({
      started_at: "2026-11-14T11:00:00.000Z",
      ended_at: "2026-11-14T11:00:00.000Z",
    });
  });

  it("starts again when the app opens still cut off after it was away", async () => {
    // Shut at 19:00 with no internet, opened at 07:30 still with none: two periods, as nobody saw the
    // night, and the second goes on from 07:30.
    const db = aTab();
    await cutOffFrom(db, at("18:30"), at("19:00"));
    const morning = at("19:00") + 12.5 * 60 * MINUTE;
    await cutOffFrom(db, morning, morning + 4.5 * MINUTE);
    await noteBack(db, morning + 5 * MINUTE);

    expect(await periods(db)).toEqual([
      {
        started_at: "2026-11-14T18:30:00.000Z",
        ended_at: "2026-11-14T19:00:00.000Z",
      },
      {
        started_at: "2026-11-15T07:30:00.000Z",
        ended_at: "2026-11-15T07:35:00.000Z",
      },
    ]);
  });

  it("is kept up while a sync hangs, and never opened by an app that is only still here", async () => {
    // Wi-Fi up, internet gone: the sync's calls hang for minutes before they fail (answer.ts). The
    // moments meanwhile keep the open period in sight; with none open, they open none.
    const db = aTab();
    await noteStillHere(db, at("10:00"));
    expect(await db.outages.count()).toBe(0);

    await noteCutOff(db, at("10:05"));
    for (let tick = 1; tick <= 10; tick++)
      await noteStillHere(db, at("10:05") + tick * 30_000);
    await noteBack(db, at("10:10"));

    expect(await periods(db)).toEqual([
      {
        started_at: "2026-11-14T10:05:00.000Z",
        ended_at: "2026-11-14T10:10:00.000Z",
      },
    ]);
  });

  it("keeps its end unknown when the app lost sight of it, and known when the server's answer ended it", async () => {
    // The power goes at 18:59 and the laptop dies 10 seconds later: the next morning it knows only that the
    // cut began then, and when it last saw it. A cut the server's answer ended was seen to its end
    // (SYNC-14's review).
    const db = aTab();
    await cutOffFrom(db, at("18:59"), at("18:59"));
    const morning = at("18:59") + 12.5 * 60 * MINUTE;
    await noteBack(db, morning);
    await cutOffFrom(db, morning + MINUTE, morning + 5 * MINUTE);
    await noteBack(db, morning + 5.5 * MINUTE);

    const rows = (await db.outages.toArray()).sort((a, b) =>
      a.started_at.localeCompare(b.started_at),
    );
    expect(
      rows.map(({ started_at, ended_at, end_unknown }) => ({
        started_at,
        ended_at,
        end_unknown,
      })),
    ).toEqual([
      {
        started_at: "2026-11-14T18:59:00.000Z",
        ended_at: "2026-11-14T18:59:00.000Z",
        end_unknown: true,
      },
      {
        started_at: "2026-11-15T07:30:00.000Z",
        ended_at: "2026-11-15T07:34:30.000Z",
        end_unknown: false,
      },
    ]);
  });

  it("notes nothing when the server answers with no period open", async () => {
    const db = aTab();
    await noteBack(db, at("10:00"));

    expect(await db.outages.count()).toBe(0);
  });

  it("keeps the laptop's times as its clock read them, even after the clock was put back", async () => {
    // Someone puts the laptop's clock back 20 minutes during the cut: the period ends before it starts.
    // The server keeps it so (DeviceOutage), and the office page says so.
    const db = aTab();
    await noteCutOff(db, at("10:05"));
    await noteBack(db, at("09:50"));

    expect(await periods(db)).toEqual([
      {
        started_at: "2026-11-14T10:05:00.000Z",
        ended_at: "2026-11-14T09:50:00.000Z",
      },
    ]);
  });

  it("closes a second open period rather than keep it open for good", async () => {
    // Only a bug could leave two open, both in sight: one goes on, the other ends where it was last seen,
    // and none is left open.
    const db = aTab();
    await db.outages.bulkAdd([
      {
        id: "0192f000-0000-7000-8000-0000000000e1",
        started_at: "2026-11-14T10:04:00.000Z",
        ended_at: null,
        seen_at: "2026-11-14T10:05:00.000Z",
        end_unknown: false,
      },
      {
        id: "0192f000-0000-7000-8000-0000000000e2",
        started_at: "2026-11-14T10:05:00.000Z",
        ended_at: null,
        seen_at: "2026-11-14T10:05:30.000Z",
        end_unknown: false,
      },
    ]);
    await noteBack(db, at("10:06"));

    expect(await periods(db)).toEqual([
      {
        started_at: "2026-11-14T10:04:00.000Z",
        ended_at: "2026-11-14T10:06:00.000Z",
      },
      {
        started_at: "2026-11-14T10:05:00.000Z",
        ended_at: "2026-11-14T10:05:30.000Z",
      },
    ]);
  });
});
