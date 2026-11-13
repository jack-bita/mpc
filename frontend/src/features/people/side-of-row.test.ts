// side-of-row.test.ts — which side the top bar names for someone at a device, from the laptop's own copy of
// their staff row and the shop's sides (SYNC-10, SYNC-11).
import { describe, expect, it } from "vitest";

import { DAWA, VYAKULA } from "@/test/devices";
import { staffRow } from "@/test/laptop";

import { sideOfStaffRow } from "./side-of-row";

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
