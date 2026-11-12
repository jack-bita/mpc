// who-is-here.test.ts — which side the top bar names once someone logs in at a device: the side they work
// on (UI-4).
import { describe, expect, it } from "vitest";

import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { staffRow } from "@/test/laptop";

import { sideAt, sideOfStaffRow } from "./who-is-here";

describe("sideAt", () => {
  it("is the device's home side when the person works there", () => {
    // A Dawa seller who also helps on Vyakula, at the Dawa laptop.
    const me = whoIsHere([
      { side: VYAKULA, permissions: ["sale.make"] },
      { side: DAWA, permissions: ["sale.make"] },
    ]);

    expect(sideAt(me, DAWA.id)?.name).toBe("Dawa");
  });

  it("is the side they work on when it isn't the device's", () => {
    // A Vyakula seller who logs in at the Dawa laptop.
    const me = whoIsHere([{ side: VYAKULA, permissions: ["sale.make"] }]);

    expect(sideAt(me, DAWA.id)?.name).toBe("Vyakula");
  });

  it("is none when they hold no key on any side", () => {
    expect(sideAt(whoIsHere([]), DAWA.id)).toBeUndefined();
  });
});

describe("sideOfStaffRow", () => {
  // The laptop's two sides, as its sync left them; Juma's staff row, with keys as each test gives.
  const SIDES = [
    { ...DAWA, sale_flow: "one_screen" as const, is_live: true },
    { ...VYAKULA, sale_flow: "one_screen" as const, is_live: true },
  ];
  const juma = (
    every_side: string[],
    sides: { side: string; permissions: string[] }[],
  ) => ({
    ...staffRow("019a5e00-0000-7000-8000-0000000000c3", "Juma Mfano", "Juma"),
    permissions: { every_side, sides },
  });

  it("is the device's home side when he holds a key there", () => {
    const row = juma(
      [],
      [
        { side: VYAKULA.id, permissions: ["sale.make"] },
        { side: DAWA.id, permissions: ["sale.make"] },
      ],
    );

    expect(sideOfStaffRow(row, DAWA.id, SIDES)?.name).toBe("Dawa");
  });

  it("is the first side he holds a key on when it isn't the device's", () => {
    // A Vyakula seller at the Dawa laptop sells Vyakula's goods.
    const row = juma([], [{ side: VYAKULA.id, permissions: ["sale.make"] }]);

    expect(sideOfStaffRow(row, DAWA.id, SIDES)?.name).toBe("Vyakula");
  });

  it("is the home side for a key on the whole shop", () => {
    const row = juma(["sale.make"], []);

    expect(sideOfStaffRow(row, DAWA.id, SIDES)?.name).toBe("Dawa");
  });

  it("is none when he holds no key, even with sides listed", () => {
    const row = juma([], [{ side: DAWA.id, permissions: [] }]);

    expect(sideOfStaffRow(row, DAWA.id, SIDES)).toBeUndefined();
  });
});
