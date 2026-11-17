// blanks.test.ts — the names a sentence fills in, read as use-intl reads its ICU messages (UI-2).
import { describe, expect, it } from "vitest";

import { blanks } from "./blanks";

describe("blanks", () => {
  it("finds each name a sentence fills in", () => {
    expect(blanks("Toleo {version}")).toEqual(["version"]);
    expect(blanks("{unit} {count}")).toEqual(["unit", "count"]);
  });

  it("finds none in a sentence with nothing to fill in", () => {
    expect(blanks("Karibu")).toEqual([]);
  });

  it("reads a name written with spaces around it", () => {
    expect(blanks("Jaribu tena baada ya dakika { minutes }.")).toEqual([
      "minutes",
    ]);
  });

  it("reads a plural's own name, never the words in its branches", () => {
    const sentence =
      "Try again in {minutes} {minutes, plural, one {minute} other {minutes}}.";
    expect(blanks(sentence)).toEqual(["minutes"]);
  });

  it("finds a name that sits inside a branch", () => {
    const sentence =
      "{count, plural, one {one bag from {side}} other {# bags from {side}}}";
    expect(blanks(sentence)).toEqual(["count", "side"]);
  });
});
