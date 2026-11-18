// format.phone.test.ts — a phone as the shop writes it (PPL-10): the server stores one form, "+255712345678", and the
// worker's page writes it "0712 345 678", as people type and say it.
import { describe, expect, it } from "vitest";

import { formatPhone } from "./format";

describe("a phone", () => {
  it("is written the Tanzanian way, with its leading 0, in groups of three", () => {
    expect(formatPhone("+255712345678")).toBe("0712 345 678");
  });

  it("of another country keeps its stored form, as the 0 is Tanzania's own", () => {
    expect(formatPhone("+254712345678")).toBe("+254712345678");
  });
});
