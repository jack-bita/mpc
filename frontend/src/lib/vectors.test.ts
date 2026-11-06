// vectors.test.ts — every file in the shared answer book is run here, and the reader refuses what
// Python's reader refuses (03 §8). The TypeScript twin of the checks at the top of
// backend/tests/test_vectors.py.
//
// An answer-book file with no runner would check nothing in TypeScript, while pytest stays green: the
// device and the server could drift apart unseen.
// @vitest-environment node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { readCases, vectorFiles } from "@/test/vectors";

describe("the shared answer book", () => {
  it("has files to run", () => {
    // If the folder moved, every check below would pass on nothing.
    expect(vectorFiles()).toEqual(
      expect.arrayContaining(["rounding.json", "units.json"]),
    );
  });

  it.each(vectorFiles())("%s has a runner here", (file) => {
    // rounding.json → vectors.rounding.test.ts; a/b.json → vectors.a.b.test.ts.
    const runner = `vectors.${file
      .replace(/\.json$/, "")
      .split("/")
      .join(".")}.test.ts`;
    const code = readFileSync(
      resolve(process.cwd(), "src/lib", runner),
      "utf8",
    );
    expect(code).toContain(`casesIn<`);
    expect(code).toContain(`("${file}")`);
  });

  it("refuses two cases with one name", () => {
    expect(() =>
      readCases('{"cases": [{"name": "zero"}, {"name": "zero"}]}'),
    ).toThrow("share a name");
  });

  it.each(["2.5", "2", "1e3", "-0"])(
    "refuses %s written without quotes",
    (bare) => {
      expect(() =>
        readCases(`{"cases": [{"name": "bad", "amount": ${bare}}]}`),
      ).toThrow("bare number");
    },
  );

  it.each(["NaN", "-Infinity"])("refuses %s", (bare) => {
    // Not JSON at all, so JSON.parse refuses it before our check can: Python reads them, and refuses
    // them in its own check.
    expect(() =>
      readCases(`{"cases": [{"name": "bad", "amount": ${bare}}]}`),
    ).toThrow();
  });
});
