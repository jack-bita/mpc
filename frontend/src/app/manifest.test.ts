// manifest.test.ts — the manifest gives Chrome what it needs before it offers to install the app, and
// carries the shop's look (SPIKE-1, UI-7).
//
// Chrome reads the manifest only in a real browser, so this test checks what we control: the fields
// Chrome looks for, that every icon the manifest names really exists in public/, that the manifest's
// colours equal the app's tokens, and what the icon files really hold, pixel by pixel.
//
// It runs in plain Node, not in jsdom's fake browser (vitest.config.mts): it needs no page, and it
// reads files on disk. Under jsdom, Vite turns new URL(…, import.meta.url) into a web address,
// which fileURLToPath can't read; in Node it stays a file:// address.
// @vitest-environment node
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { inflateSync } from "node:zlib";

import { describe, expect, it } from "vitest";

import sw from "../../messages/sw.json";
import manifest from "./manifest";

// public/ is served at the site's root, so the icon "/icons/icon-192.png" is public/icons/icon-192.png.
const PUBLIC = fileURLToPath(new URL("../../public", import.meta.url));

// Comments removed, because one could name a token and match first, and only rules count.
const CSS = readFileSync(
  fileURLToPath(new URL("./globals.css", import.meta.url)),
  "utf8",
).replace(/\/\*[\s\S]*?\*\//g, "");

/** A colour token's value from globals.css, like "#15803d". */
function token(name: string): string | undefined {
  return new RegExp(`${name}:\\s*(#[0-9a-f]{6})`).exec(CSS)?.[1];
}

/**
 * The size and pixels of a PNG as scripts/make-icons.mjs writes it: red, green and blue with no
 * transparency, and no row filter. Enough for our own files; not a general PNG reader.
 */
function readIcon(src: string) {
  const file = readFileSync(`${PUBLIC}${src}`);
  const size = file.readUInt32BE(16);
  // After the 8-byte signature, each chunk is: its length, its type, its data, a 4-byte checksum.
  const data: Buffer[] = [];
  for (let at = 8; at < file.length; at += 12 + file.readUInt32BE(at)) {
    if (file.toString("latin1", at + 4, at + 8) === "IDAT")
      data.push(file.subarray(at + 8, at + 8 + file.readUInt32BE(at)));
  }
  const raw = inflateSync(Buffer.concat(data));
  // Each row is one filter byte, then 3 bytes per pixel.
  const pixel = (x: number, y: number) => {
    const start = y * (1 + size * 3) + 1 + x * 3;
    return `#${raw.subarray(start, start + 3).toString("hex")}`;
  };
  return { size, pixel };
}

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
    expect(token("--primary")).toBeDefined();
    expect(app.theme_color).toBe(token("--primary"));
    // The screen while the app starts. The icon's own green sits on it, so any other colour would
    // show the icon's edge as a square.
    expect(app.background_color).toBe(token("--primary"));
  });

  it("names only icons that exist in public/", () => {
    // A typo in a file name would pass every check above, and Chrome would then refuse to install.
    expect(icons.length).toBeGreaterThan(0);
    for (const icon of icons)
      expect(existsSync(`${PUBLIC}${icon.src}`), icon.src).toBe(true);
  });
});

describe("the godown icon", () => {
  const icons = manifest().icons ?? [];

  describe.each(icons)("$src", ({ src, sizes }) => {
    it("really is the size the manifest says", () => {
      // A file of the wrong size would pass every check above, and Chrome would refuse to install.
      expect(`${readIcon(src).size}x${readIcon(src).size}`).toBe(sizes);
    });

    it("is a green square with a white building and a blue door", () => {
      // Each point is a share of the width, so it holds at any size, and for the smaller drawing too.
      const { size, pixel } = readIcon(src);
      const last = size - 1;
      for (const [x, y] of [
        [0, 0],
        [last, 0],
        [0, last],
        [last, last],
      ] as const)
        expect(pixel(x, y)).toBe(token("--primary"));
      // The icon uses the same tokens as the app, so it can't drift from the screens (ADR-0039).
      expect(pixel(size / 2, size / 2)).toBe(token("--secondary"));
      // Whole pixels only: 30% of 192 is 57.6, and a fractional position would read the wrong bytes.
      expect(pixel(Math.floor(size * 0.3), Math.floor(size * 0.6))).toBe(
        "#ffffff",
      );
    });
  });

  it("keeps the whole godown inside Android's safe circle", () => {
    // Android cuts an icon into a circle or a rounded square. Only the middle circle, 80% of the
    // width, is sure to survive, so anything but plain green outside it could be cut.
    const maskable = icons.find((icon) => icon.purpose === "maskable");
    if (!maskable) throw new Error("the manifest lists no maskable icon");
    const { size, pixel } = readIcon(maskable.src);
    const safeRadius = size * 0.4;
    let outside = 0;
    for (let y = 0; y < size; y++) {
      for (let x = 0; x < size; x++) {
        const fromMiddle = Math.hypot(x + 0.5 - size / 2, y + 0.5 - size / 2);
        if (fromMiddle > safeRadius && pixel(x, y) !== token("--primary"))
          outside++;
      }
    }
    expect(outside).toBe(0);
  });
});
