// make-icons.mjs — draws the app's placeholder icons into public/icons/ (SPIKE-1).
//
// Chrome offers to install the app only when its manifest (src/app/manifest.ts) lists PNG icons of
// 192 and 512 pixels. Until the design system sets the real ones, the icon is a placeholder in the
// shop's colours: a green square, a blue band and "MPC" in white letters.
//
// Why a script and not a drawing app: anyone can read how the icon is made and make it again, and it
// needs only Node's own modules, so no package to install. Its PNG files are committed: the build
// never runs this script. Run it again only when the drawing changes, from frontend/:
//   node scripts/make-icons.mjs
import { mkdirSync, writeFileSync } from "node:fs";
import { crc32, deflateSync } from "node:zlib";

// The shop's colours, as [red, green, blue]. Placeholders: the design system picks the real shades.
const GREEN = [21, 128, 61];
const BLUE = [29, 78, 216];
const WHITE = [255, 255, 255];

// The letters on a grid of 5 columns and 7 rows, as blocks: the simplest font that needs no font file.
const LETTERS = {
  M: ["X...X", "XX.XX", "X.X.X", "X.X.X", "X...X", "X...X", "X...X"],
  P: ["XXXX.", "X...X", "X...X", "XXXX.", "X....", "X....", "X...."],
  C: [".XXXX", "X....", "X....", "X....", "X....", "X....", ".XXXX"],
};
const TEXT = "MPC";
// Three letters of 5 columns, with one empty column between them.
const TEXT_COLUMNS = TEXT.length * 5 + (TEXT.length - 1);
const TEXT_ROWS = 7;

// Every share below is a part of the icon's width or height, so one drawing serves every size.
// - "any": the icon as drawn, for Windows and for Android's plain icons.
// - "maskable": Android cuts an icon into a circle or a rounded square, and keeps only the circle in
//   the middle, 80% of the width, for sure. So its letters are smaller and nearer the middle.
const ICONS = [
  {
    file: "icon-192.png",
    size: 192,
    textWidth: 0.62,
    textMiddle: 0.42,
    band: [0.64, 0.72],
  },
  {
    file: "icon-512.png",
    size: 512,
    textWidth: 0.62,
    textMiddle: 0.42,
    band: [0.64, 0.72],
  },
  {
    file: "icon-maskable-512.png",
    size: 512,
    textWidth: 0.46,
    textMiddle: 0.45,
    band: [0.6, 0.66],
  },
];

const folder = new URL("../public/icons/", import.meta.url);
mkdirSync(folder, { recursive: true });
for (const icon of ICONS) {
  const pixels = draw(icon);
  writeFileSync(new URL(icon.file, folder), png(icon.size, pixels));
  console.log(`wrote public/icons/${icon.file}`);
}

/** The colour of every pixel, row by row: a function of where the pixel sits. */
function draw({ size, textWidth, textMiddle, band }) {
  // A whole number of pixels per letter block, so every block has the same size and sharp edges.
  const block = Math.floor((size * textWidth) / TEXT_COLUMNS);
  const left = Math.floor((size - block * TEXT_COLUMNS) / 2);
  const top = Math.round(size * textMiddle - (block * TEXT_ROWS) / 2);
  const [bandTop, bandBottom] = band.map((share) => Math.round(size * share));

  const rows = [];
  for (let y = 0; y < size; y++) {
    const row = [];
    for (let x = 0; x < size; x++) {
      if (
        isLetter(Math.floor((x - left) / block), Math.floor((y - top) / block))
      )
        row.push(WHITE);
      else if (y >= bandTop && y < bandBottom) row.push(BLUE);
      else row.push(GREEN);
    }
    rows.push(row);
  }
  return rows;
}

/** True when the block at this column and row of the text is part of a letter. */
function isLetter(column, row) {
  if (column < 0 || column >= TEXT_COLUMNS || row < 0 || row >= TEXT_ROWS)
    return false;
  // Each letter takes 6 columns: its own 5 and the gap after it.
  const letter = LETTERS[TEXT[Math.floor(column / 6)]];
  return letter[row][column % 6] === "X";
}

/** A PNG file: a fixed signature, then three chunks: the size, the pixels, the end. */
function png(size, rows) {
  // The header: width and height, then 8 bits per colour, colour type 2 (red, green, blue, with no
  // transparency: the icon fills its square), and the standard compression, filter and no interlace.
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header.set([8, 2, 0, 0, 0], 8);

  // Each row starts with a filter byte; 0 means the row's bytes are stored as they are.
  const raw = Buffer.concat(rows.map((row) => Buffer.from([0, ...row.flat()])));

  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

/** One PNG chunk: its length, its type, its data, then a checksum that lets a reader spot damage. */
function chunk(type, data) {
  const typeAndData = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(typeAndData));
  return Buffer.concat([length, typeAndData, checksum]);
}
