// pointer.test.ts — the hand pointer invites a click only where a click does something (UI-7).
//
// jsdom has no mouse and doesn't work out a pointer from a stylesheet. It does run real selectors, so
// this test takes the rule's selector from globals.css and asks real elements whether it matches them,
// which says more than finding the rule's text. Seeing the hand itself is on the card's Done list.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

// From the folder the tests run in: under jsdom, Vite turns new URL(…, import.meta.url) into a web
// address, which a file read can't use (manifest.test.ts). Comments removed: only rules count.
const CSS = readFileSync(
  resolve(process.cwd(), "src/app/globals.css"),
  "utf8",
).replace(/\/\*[\s\S]*?\*\//g, "");

const selector = /([^{}]+)\{\s*cursor:\s*pointer/.exec(CSS)?.[1]?.trim() ?? "";

function element(html: string): Element {
  const holder = document.createElement("div");
  holder.innerHTML = html;
  return holder.firstElementChild as Element;
}

describe("the hand pointer", () => {
  it("finds the rule", () => {
    expect(selector).not.toBe("");
  });

  it.each([
    "<button>Hifadhi</button>",
    '<div role="button">Hifadhi</div>',
    '<input type="submit" value="Tuma">',
    '<input type="button" value="Tuma">',
    "<summary>Maelezo</summary>",
  ])("shows on what can be pressed: %s", (html) => {
    expect(element(html).matches(selector)).toBe(true);
  });

  it.each([
    "<button disabled>Hifadhi</button>",
    // Base UI can keep a disabled button focusable, so a keyboard can still reach it. It then says
    // disabled this way instead, and pressing it still does nothing.
    '<button aria-disabled="true">Hifadhi</button>',
    '<div role="button" aria-disabled="true">Hifadhi</div>',
    '<input type="submit" value="Tuma" disabled>',
    '<input type="button" value="Tuma" disabled>',
    "<span>Maelezo</span>",
  ])("stays off what can't be pressed: %s", (html) => {
    expect(element(html).matches(selector)).toBe(false);
  });
});
