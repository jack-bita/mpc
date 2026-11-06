// vectors.ts — reads the shared answer book, shared/test-vectors/*.json, for the Vitest runners (03 §8).
// Tests only. The TypeScript twin of the reader in backend/tests/test_vectors.py.
//
// Some sums are done twice: offline on a counter device, in TypeScript, and again on the server, in
// Python. So the right answers are written once, and both languages must pass the very same files:
// pytest there, Vitest here. Each file has its own runner here, src/lib/vectors.<file>.test.ts, and
// vectors.test.ts checks that none is missing.
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * The answer book's folder, beside frontend/. Read from the folder the tests run in, frontend/, as
 * look.ts reads globals.css: under jsdom, Vite turns new URL(…, import.meta.url) into a web address.
 */
export const VECTORS = resolve(process.cwd(), "../shared/test-vectors");

/**
 * The cases in an answer-book file's text. A number written without quotes is refused: JavaScript
 * reads every JSON number as a float, so 2.5 would already be inexact before any test ran. Every
 * number in the files is text, so a bare one is a mistake in the file. Python's reader refuses the
 * same, so a file one side refuses, the other refuses too.
 */
export function readCases<Case extends { name: string }>(text: string): Case[] {
  const data = JSON.parse(text, (_key, value: unknown) => {
    if (typeof value === "number")
      throw new Error(
        `${value} is a bare number: write it as text, in quotes.`,
      );
    return value;
  }) as { cases: Case[] };
  // Each name becomes a test's name, so a failure names its case. Two cases with one name would make
  // a failure point at either.
  const names = data.cases.map((item) => item.name);
  const twins = names.filter((name, at) => names.indexOf(name) !== at);
  if (twins.length)
    throw new Error(`Two cases share a name: ${twins.join(", ")}.`);
  return data.cases;
}

/** The cases in one answer-book file, by its path inside VECTORS: "rounding.json". */
export function casesIn<Case extends { name: string }>(file: string): Case[] {
  return readCases<Case>(readFileSync(resolve(VECTORS, file), "utf8"));
}

/** Every answer-book file, by its path inside VECTORS, a file in a subfolder too: "a/b.json". */
export function vectorFiles(): string[] {
  return readdirSync(VECTORS, { recursive: true, encoding: "utf8" })
    .filter((file) => file.endsWith(".json"))
    .map((file) => file.split("\\").join("/"))
    .sort();
}
