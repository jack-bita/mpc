// pin.lockout.test.ts — the offline lock (SYNC-10, 03 §5.9): five wrong PINs lock a person on this
// laptop for a minute, each lock twice as long as the last, up to an hour, the server's own numbers
// (apps/people/pins.py). A try is counted before its check, so a crash in the check gives no free try.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ASHA_PIN,
  ASHA_ROW,
  ashaLoggedInOnline,
  BARAKA_PIN,
  BARAKA_ROW,
  EIGHT_AM,
  FEW_TURNS,
  laptopWithStaff,
  throwAway,
} from "@/test/pins";

import type { ShopDatabase } from "./db";
import {
  checkPinOffline,
  FIRST_LOCK_MINUTES,
  LONGEST_LOCK_MINUTES,
  PIN_TRIES,
  rememberPin,
} from "./pin";

const MINUTE = 60_000;
const WRONG = "2581";

let db: ShopDatabase;
beforeEach(async () => {
  db = await laptopWithStaff();
  await ashaLoggedInOnline(db);
});
afterEach(async () => {
  vi.restoreAllMocks();
  await throwAway(db);
});

/** Asha's tile, `times` wrong PINs at `at`: the last answer's refusal. */
async function wrongPins(times: number, at: number): Promise<unknown> {
  let last: unknown;
  for (let i = 0; i < times; i++)
    last = await checkPinOffline(db, ASHA_ROW.id, WRONG, at).catch(
      (refused: unknown) => refused,
    );
  return last;
}

/** The blender, watched: a locked or a suspended person must cost no check. */
function watchTheBlender() {
  return vi.spyOn(crypto.subtle, "deriveBits");
}

describe("the offline lock", () => {
  it("has the server's numbers", () => {
    expect([PIN_TRIES, FIRST_LOCK_MINUTES, LONGEST_LOCK_MINUTES]).toEqual([
      5, 1, 60,
    ]);
  });

  it("locks a person here for a minute after five wrong PINs", async () => {
    // The first four: wrong, and nothing more.
    expect(await wrongPins(4, EIGHT_AM)).toMatchObject({ code: "pin.wrong" });
    // The fifth starts the lock, and says how long, in seconds, as the server does.
    expect(await wrongPins(1, EIGHT_AM)).toMatchObject({
      code: "pin.locked",
      params: { wait: 60 },
    });
    // During it, even her right PIN is refused, with the time left.
    await expect(
      checkPinOffline(db, ASHA_ROW.id, ASHA_PIN, EIGHT_AM + 20_000),
    ).rejects.toMatchObject({ code: "pin.locked", params: { wait: 40 } });
  });

  it("lets her in with the right PIN once the minute is over", async () => {
    await wrongPins(5, EIGHT_AM);

    expect(
      await checkPinOffline(db, ASHA_ROW.id, ASHA_PIN, EIGHT_AM + MINUTE),
    ).toEqual(ASHA_ROW);
  });

  it("doubles each lock, up to an hour", async () => {
    let now = EIGHT_AM;
    for (const minutes of [1, 2, 4, 8, 16, 32, 60, 60]) {
      expect(await wrongPins(5, now)).toMatchObject({
        code: "pin.locked",
        params: { wait: minutes * 60 },
      });
      now += minutes * MINUTE;
    }
  });

  it("says the wait in whole seconds, rounded up", async () => {
    await wrongPins(5, EIGHT_AM);

    // 59.4 seconds left: "wait 60", never "wait 59" with part of a second still to go. Not 59.5, which
    // plain rounding would also make 60, so the test couldn't tell rounding up from rounding.
    await expect(
      checkPinOffline(db, ASHA_ROW.id, ASHA_PIN, EIGHT_AM + 600),
    ).rejects.toMatchObject({ params: { wait: 60 } });
  });

  it("starts the count again after her right PIN", async () => {
    expect(await wrongPins(4, EIGHT_AM)).toMatchObject({ code: "pin.wrong" });
    await checkPinOffline(db, ASHA_ROW.id, ASHA_PIN, EIGHT_AM);

    // Four more: still only wrong, as the right one wiped the four before.
    expect(await wrongPins(4, EIGHT_AM)).toMatchObject({ code: "pin.wrong" });
  });

  it("starts the locks at a minute again after her right PIN", async () => {
    await wrongPins(5, EIGHT_AM);
    const later = EIGHT_AM + MINUTE;
    await checkPinOffline(db, ASHA_ROW.id, ASHA_PIN, later);

    // The next lock is a minute again, not two: the server lifts a lock the same way.
    expect(await wrongPins(5, later)).toMatchObject({
      code: "pin.locked",
      params: { wait: 60 },
    });
  });

  it("lets her in when her fifth try is right", async () => {
    // As the server does: the fifth try is counted, and the lock it starts is lifted by the right PIN.
    await wrongPins(4, EIGHT_AM);

    expect(await checkPinOffline(db, ASHA_ROW.id, ASHA_PIN, EIGHT_AM)).toEqual(
      ASHA_ROW,
    );
    expect(await wrongPins(1, EIGHT_AM)).toMatchObject({ code: "pin.wrong" });
  });

  it("counts a try before it checks it, so a crash gives no free try", async () => {
    // The tab is closed, or the blender fails, in the middle of the check.
    watchTheBlender().mockRejectedValue(new Error("The tab closed."));

    for (let i = 0; i < PIN_TRIES; i++)
      await expect(
        checkPinOffline(db, ASHA_ROW.id, ASHA_PIN, EIGHT_AM),
      ).rejects.toThrow("The tab closed.");

    // Five tries that never finished their check still made the lock.
    vi.restoreAllMocks();
    await expect(
      checkPinOffline(db, ASHA_ROW.id, ASHA_PIN, EIGHT_AM),
    ).rejects.toMatchObject({ code: "pin.locked" });
  });

  it("makes no check while she is locked", async () => {
    await wrongPins(5, EIGHT_AM);
    const blender = watchTheBlender();

    await expect(
      checkPinOffline(db, ASHA_ROW.id, ASHA_PIN, EIGHT_AM + 1_000),
    ).rejects.toMatchObject({ code: "pin.locked" });
    expect(blender).not.toHaveBeenCalled();
  });

  it("locks only her, on this laptop", async () => {
    await rememberPin(db, BARAKA_ROW.id, BARAKA_PIN, FEW_TURNS);
    await wrongPins(5, EIGHT_AM);

    expect(
      await checkPinOffline(db, BARAKA_ROW.id, BARAKA_PIN, EIGHT_AM),
    ).toEqual(BARAKA_ROW);
  });

  it("is lifted by her next online login", async () => {
    await wrongPins(5, EIGHT_AM);

    // The server said yes to her PIN: her lock here goes too, as a new check is made.
    await ashaLoggedInOnline(db);

    expect(await checkPinOffline(db, ASHA_ROW.id, ASHA_PIN, EIGHT_AM)).toEqual(
      ASHA_ROW,
    );
  });
});
