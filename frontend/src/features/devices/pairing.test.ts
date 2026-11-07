// pairing.test.ts — a new device's code: its life measured on the server's clock, read out in two
// groups, counted down in minutes and seconds (UI-3).
import { describe, expect, it } from "vitest";

import { codeForReading, lifetime, timeLeft } from "./pairing";

const SERVER_NOW = "Sat, 07 Nov 2026 09:00:00 GMT";
const EXPIRES = "2026-11-07T09:10:00Z";

describe("lifetime", () => {
  it("is measured on the server's clock", () => {
    // The laptop's clock is an hour ahead: the code still has its 10 minutes, less the second its Date
    // header may have cut off.
    const anHourAhead = Date.parse("2026-11-07T10:00:00Z");
    expect(lifetime(EXPIRES, SERVER_NOW, anHourAhead)).toBe(
      10 * 60 * 1000 - 1000,
    );
  });

  it("falls back on the device's clock with no Date header", () => {
    const deviceNow = Date.parse("2026-11-07T09:02:00Z");
    expect(lifetime(EXPIRES, null, deviceNow)).toBe(8 * 60 * 1000);
    expect(lifetime(EXPIRES, "not a date", deviceNow)).toBe(8 * 60 * 1000);
  });

  it("is never below zero", () => {
    expect(lifetime(EXPIRES, "Sat, 07 Nov 2026 09:20:00 GMT", 0)).toBe(0);
  });
});

describe("codeForReading", () => {
  it("splits the code in two groups of four", () => {
    expect(codeForReading("K7QM4RXT")).toBe("K7QM-4RXT");
  });

  it("leaves a code of another length as it is", () => {
    expect(codeForReading("K7QM4R")).toBe("K7QM4R");
  });
});

describe("timeLeft", () => {
  it("reads minutes and seconds", () => {
    expect(timeLeft(10 * 60 * 1000, 0)).toBe("10:00");
    expect(timeLeft(10 * 60 * 1000, 19 * 1000)).toBe("9:41");
    expect(timeLeft(65 * 1000, 0)).toBe("1:05");
  });

  it("counts a part of a second up, so 0:00 means expired", () => {
    expect(timeLeft(1000, 999)).toBe("0:01");
    expect(timeLeft(1000, 1000)).toBe("0:00");
    expect(timeLeft(1000, 5000)).toBe("0:00");
  });
});
