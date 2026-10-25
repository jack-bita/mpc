// version.test.ts — the version shown on screen is the commit, cut as GitHub cuts it (SPIKE-1).
import { describe, expect, it } from "vitest";

import { shortVersion } from "./version";

describe("shortVersion", () => {
  it("keeps the first 7 characters of a commit", () => {
    expect(shortVersion("130bd6d637b36a633965d5e9fd99a402957c800f")).toBe(
      "130bd6d",
    );
  });

  it("is dev when the build got no version", () => {
    expect(shortVersion(undefined)).toBe("dev");
    expect(shortVersion("")).toBe("dev");
  });
});
