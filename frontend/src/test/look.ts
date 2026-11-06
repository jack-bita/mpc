// look.ts — reads the shop's look from globals.css and does the contrast sums, for the tests that keep
// the look true: tokens.test.ts, pointer.test.ts and the pieces' tests in components/design/ (UI-8).
// Tests only: no screen imports it.
//
// It reads globals.css as plain text, because jsdom applies no stylesheet and lays out nothing. So the
// tests can only check what the file and the class names say, and the eye checks the rest, on /design.
// One copy of the sums, so the tokens and the pieces can never be judged by two different formulas.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * globals.css with its comments removed: they may name old values on purpose, like the first faded
 * red, and only what the browser reads counts. Read from the folder the tests run in, frontend/: under
 * jsdom, Vite turns new URL(…, import.meta.url) into a web address, which a file read can't use.
 */
export const CSS = readFileSync(
  resolve(process.cwd(), "src/app/globals.css"),
  "utf8",
).replace(/\/\*[\s\S]*?\*\//g, "");

/** The value of every token in the first `:root` block, by name: "--primary" -> "#15803d". */
export function readTokens(css: string): Map<string, string> {
  const block = /:root\s*\{([^}]*)\}/.exec(css)?.[1];
  if (block === undefined) throw new Error("globals.css has no :root block");
  return new Map(
    [...block.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map(
      (match): [string, string] => [match[1] ?? "", (match[2] ?? "").trim()],
    ),
  );
}

export const TOKENS = readTokens(CSS);

/**
 * A token's colour. A token that isn't plain hex fails here, so the sums never run on a bad value.
 * Small letters only, because Prettier rewrites a CSS colour that way when it formats the file.
 */
export function colour(name: string): string {
  const value = TOKENS.get(name);
  if (value === undefined || !/^#[0-9a-f]{6}$/.test(value))
    throw new Error(
      `${name} should be a colour like #15803d, not ${value ?? "missing"}`,
    );
  return value;
}

/** How bright a colour looks to the eye, from 0 (black) to 1 (white): the WCAG formula. */
export function brightness(hex: string): number {
  // Screens store colours bent to suit the eye; the formula needs them straightened out first.
  const channel = (start: number) => {
    const value = Number.parseInt(hex.slice(start, start + 2), 16) / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  // Weighted because the eye is most sensitive to green and least to blue.
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

/** The contrast of two colours: 1 for the same colour, 21 for black on white. The order doesn't matter. */
export function contrast(first: string, second: string): number {
  const lighter = Math.max(brightness(first), brightness(second));
  const darker = Math.min(brightness(first), brightness(second));
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * `share` of the colour `top` laid over `bottom`, from 0 to 1: what the screen shows. Browsers mix a
 * see-through colour (Tailwind's bg-primary/80) and color-mix(in srgb, …) this way, channel by channel
 * on the stored values, and the screen keeps whole numbers from 0 to 255.
 */
export function mix(top: string, bottom: string, share: number): string {
  const channel = (hex: string, start: number) =>
    Number.parseInt(hex.slice(start, start + 2), 16);
  const mixed = [1, 3, 5].map((start) =>
    Math.round(
      channel(top, start) * share + channel(bottom, start) * (1 - share),
    ),
  );
  return `#${mixed.map((value) => value.toString(16).padStart(2, "0")).join("")}`;
}
