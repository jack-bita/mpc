// manifest.test.ts — the manifest gives Chrome what it needs before it offers to install the app (SPIKE-1).
//
// Chrome reads the manifest only in a real browser, so this test checks what we control: the fields
// Chrome looks for, and that every icon the manifest names really exists in public/.
//
// It runs in plain Node, not in jsdom's fake browser (vitest.config.mts): it needs no page, and it
// reads files on disk. Under jsdom, Vite turns new URL(…, import.meta.url) into a web address,
// which fileURLToPath can't read; in Node it stays a file:// address.
// @vitest-environment node
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import sw from "../../messages/sw.json";
import manifest from "./manifest";

// public/ is served at the site's root, so the icon "/icons/icon-192.png" is public/icons/icon-192.png.
const PUBLIC = fileURLToPath(new URL("../../public", import.meta.url));

describe("manifest", () => {
  const app = manifest();
  const icons = app.icons ?? [];

  it("names the app from the message files", () => {
    // The name shows under the icon. Like all screen text, it lives in the message files (ADR-0032).
    expect(app.name).toBe(sw.app.title);
    expect(app.short_name).toBe(sw.app.title);
  });

  it("opens the home page in a window of its own, under a fixed id", () => {
    expect(app.start_url).toBe("/");
    expect(app.display).toBe("standalone");
    // Without an id, Chrome takes start_url as the app's identity. Counter devices will later start on
    // the sale screen (03 §7.7); a fixed id keeps every installed copy the same app when that changes.
    expect(app.id).toBe("/");
  });

  it("lists PNG icons of 192 and 512 pixels, and a maskable one", () => {
    // An icon with no purpose counts as "any": shown as drawn.
    const plainSizes = icons
      .filter((icon) => (icon.purpose ?? "any") === "any")
      .map((icon) => icon.sizes);
    expect(plainSizes).toEqual(expect.arrayContaining(["192x192", "512x512"]));
    expect(
      icons.some(
        (icon) => icon.purpose === "maskable" && icon.sizes === "512x512",
      ),
    ).toBe(true);
    for (const icon of icons) expect(icon.type).toBe("image/png");
  });

  it("uses the same green as the app's main colour", () => {
    // The manifest is plain data, so it can't read the token and has to repeat it. Without this check
    // the two could drift, and the app would open in one green and carry on in another (ADR-0039).
    const css = readFileSync(
      fileURLToPath(new URL("./globals.css", import.meta.url)),
      "utf8",
    );
    const primary = /--primary:\s*(#[0-9a-f]{6})/.exec(css)?.[1];
    expect(primary).toBeDefined();
    expect(app.theme_color).toBe(primary);
  });

  it("names only icons that exist in public/", () => {
    // A typo in a file name would pass every check above, and Chrome would then refuse to install.
    expect(icons.length).toBeGreaterThan(0);
    for (const icon of icons)
      expect(existsSync(`${PUBLIC}${icon.src}`), icon.src).toBe(true);
  });
});
