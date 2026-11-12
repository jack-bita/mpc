// pin.check.test.ts — a PIN checked on the laptop itself (SYNC-10, 03 §5.9): someone who logged in
// once online can log in offline; someone who never did can't; and the laptop keeps a salted check of
// the PIN, never the PIN.
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  ASHA_PIN,
  ASHA_ROW,
  ashaLoggedInOnline,
  BARAKA_PIN,
  BARAKA_ROW,
  FEW_TURNS,
  laptopWithStaff,
  PIN_CHANGED_AT,
  throwAway,
} from "@/test/pins";

import type { ShopDatabase } from "./db";
import {
  checkPinOffline,
  PIN_ITERATIONS,
  PinRefused,
  rememberPin,
} from "./pin";

let db: ShopDatabase;
beforeEach(async () => {
  db = await laptopWithStaff();
});
afterEach(() => throwAway(db));

describe("an offline PIN login", () => {
  it("lets in someone who logged in once online on this laptop", async () => {
    await ashaLoggedInOnline(db);

    // The person, as the laptop's staff row has her: the screen shows her name, language and font.
    expect(await checkPinOffline(db, ASHA_ROW.id, ASHA_PIN)).toEqual(ASHA_ROW);
  });

  it("refuses someone who never logged in online on this laptop", async () => {
    await ashaLoggedInOnline(db);

    // Baraka works here, but no check of his PIN was ever made on this laptop.
    await expect(
      checkPinOffline(db, BARAKA_ROW.id, BARAKA_PIN),
    ).rejects.toMatchObject({ code: "pin.offline_first" });
  });

  it("refuses a wrong PIN", async () => {
    await ashaLoggedInOnline(db);

    const refused = checkPinOffline(db, ASHA_ROW.id, "2581");

    await expect(refused).rejects.toBeInstanceOf(PinRefused);
    await expect(refused).rejects.toMatchObject({ code: "pin.wrong" });
  });

  it("refuses someone the laptop doesn't know", async () => {
    await ashaLoggedInOnline(db);
    const stranger = "019a5e00-0000-7000-8000-0000000000c9";

    await expect(checkPinOffline(db, stranger, ASHA_PIN)).rejects.toMatchObject(
      { code: "pin.offline_first" },
    );
  });

  it("takes the PIN of the latest online login", async () => {
    // A manager gave Asha a new PIN; the laptop has pulled it, and she logged in online with it.
    await ashaLoggedInOnline(db);
    await db.staff.put({ ...ASHA_ROW, pin_changed_at: PIN_CHANGED_AT });
    await rememberPin(db, ASHA_ROW.id, "1357", FEW_TURNS);

    expect(await checkPinOffline(db, ASHA_ROW.id, "1357")).toMatchObject({
      id: ASHA_ROW.id,
    });
    await expect(
      checkPinOffline(db, ASHA_ROW.id, ASHA_PIN),
    ).rejects.toMatchObject({ code: "pin.wrong" });
  });
});

describe("what the laptop keeps", () => {
  it("keeps a check of the PIN, never the PIN", async () => {
    await ashaLoggedInOnline(db);

    const row = await db.pin_checks.get(ASHA_ROW.id);
    expect(row).toMatchObject({
      staff_id: ASHA_ROW.id,
      pin_changed_at: ASHA_ROW.pin_changed_at,
      iterations: FEW_TURNS,
    });
    // Hex: 16 bytes of salt, 32 of check.
    expect(row?.salt).toMatch(/^[0-9a-f]{32}$/);
    expect(row?.check).toMatch(/^[0-9a-f]{64}$/);
    // Nowhere in the row, as typed.
    expect(JSON.stringify(row)).not.toContain(ASHA_PIN);
  });

  it("gives two people with the same PIN different checks", async () => {
    // Baraka chose 2580 too: a salt of each check's own hides that they share a PIN.
    await ashaLoggedInOnline(db);
    await rememberPin(db, BARAKA_ROW.id, ASHA_PIN, FEW_TURNS);

    const asha = await db.pin_checks.get(ASHA_ROW.id);
    const baraka = await db.pin_checks.get(BARAKA_ROW.id);
    expect(asha?.salt).not.toEqual(baraka?.salt);
    expect(asha?.check).not.toEqual(baraka?.check);
  });

  it("makes a new salt at each online login", async () => {
    await ashaLoggedInOnline(db);
    const first = await db.pin_checks.get(ASHA_ROW.id);
    await ashaLoggedInOnline(db);
    const second = await db.pin_checks.get(ASHA_ROW.id);

    expect(second?.salt).not.toEqual(first?.salt);
  });

  it("makes a check with 600,000 turns of the blender, and reads it back", async () => {
    // The real cost, once: about a third of a second here.
    await rememberPin(db, ASHA_ROW.id, ASHA_PIN);

    expect(PIN_ITERATIONS).toBe(600_000);
    expect((await db.pin_checks.get(ASHA_ROW.id))?.iterations).toBe(600_000);
    expect(await checkPinOffline(db, ASHA_ROW.id, ASHA_PIN)).toEqual(ASHA_ROW);
  });

  it("saves nothing for someone with no staff row on the laptop", async () => {
    // A laptop not filled yet: no pin_changed_at to tie a check to.
    const stranger = "019a5e00-0000-7000-8000-0000000000c9";

    await rememberPin(db, stranger, ASHA_PIN, FEW_TURNS);

    expect(await db.pin_checks.get(stranger)).toBeUndefined();
  });
});
