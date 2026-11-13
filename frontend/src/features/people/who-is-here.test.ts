// who-is-here.test.ts — which side the top bar names once someone logs in at a device: the side they work
// on (UI-4).
import { describe, expect, it } from "vitest";

import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";

import { sideAt } from "./who-is-here";

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
