// ids.test.ts — an id made on the device is a UUIDv7 the server takes, and never the same twice
// (ADR-0007).
import { describe, expect, it } from "vitest";

import { newId, uuidv7 } from "./ids";

// Any UUIDv7, as text: the version digit is 7, and the variant digit is 8, 9, a or b (its top bits 10).
const UUID7 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("uuidv7", () => {
  it("gives RFC 9562's own example", () => {
    // RFC 9562, Appendix A.6: the time 0x017F22E279B0 (22 Feb 2022, 19:22:22 UTC), with the random
    // bits 0xCC3 and 0x18C4DC0C0C07398F. The first 6 bytes are ignored, and the top bits of bytes 6
    // and 8 are written over: the six 0xff bytes, and the extra top bits in 0xfc and 0xd8, prove both.
    const random = Uint8Array.from([
      0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xfc, 0xc3, 0xd8, 0xc4, 0xdc, 0x0c,
      0x0c, 0x07, 0x39, 0x8f,
    ]);
    expect(uuidv7(0x017f22e279b0, random)).toBe(
      "017f22e2-79b0-7cc3-98c4-dc0c0c07398f",
    );
  });

  it("puts the version and the variant over any random bits", () => {
    expect(uuidv7(0, new Uint8Array(16).fill(0x00))).toMatch(UUID7);
    expect(uuidv7(0, new Uint8Array(16).fill(0xff))).toMatch(UUID7);
  });

  it("writes the time in its first 48 bits, biggest byte first", () => {
    expect(uuidv7(2 ** 48 - 1, new Uint8Array(16))).toMatch(/^ffffffff-ffff-/);
    expect(uuidv7(1, new Uint8Array(16))).toMatch(/^00000000-0001-/);
  });

  it("refuses a time 48 bits can't hold", () => {
    const random = new Uint8Array(16);
    expect(() => uuidv7(-1, random)).toThrow(RangeError);
    expect(() => uuidv7(2 ** 48, random)).toThrow(RangeError);
    expect(() => uuidv7(1.5, random)).toThrow(RangeError);
  });

  it("refuses random bytes of the wrong length", () => {
    expect(() => uuidv7(0, new Uint8Array(15))).toThrow(RangeError);
  });

  it("leaves the random bytes it was given as they were", () => {
    const random = new Uint8Array(16).fill(0xff);
    uuidv7(0, random);
    expect(random.every((byte) => byte === 0xff)).toBe(true);
  });

  it("sorts by time, as text", () => {
    // The server's index keeps ids in this order, so rows made later land at its end (ADR-0007).
    const random = new Uint8Array(16).fill(0xff);
    const earlier = uuidv7(Date.UTC(2026, 10, 7, 9, 0, 0, 0), random);
    const later = uuidv7(Date.UTC(2026, 10, 7, 9, 0, 0, 1), new Uint8Array(16));
    expect(earlier < later).toBe(true);
  });
});

describe("newId", () => {
  it("is a UUIDv7 holding the time it was made", () => {
    const before = Date.now();
    const id = newId();
    const after = Date.now();
    expect(id).toMatch(UUID7);
    const made = parseInt(id.replaceAll("-", "").slice(0, 12), 16);
    expect(made).toBeGreaterThanOrEqual(before);
    expect(made).toBeLessThanOrEqual(after);
  });

  it("is never the same twice, even in one millisecond", () => {
    // 10,000 ids in a few milliseconds: their 74 random bits keep them apart.
    const ids = new Set(Array.from({ length: 10_000 }, () => newId()));
    expect(ids.size).toBe(10_000);
  });
});
