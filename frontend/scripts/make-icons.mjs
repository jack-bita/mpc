// make-icons.mjs — draws the app's godown icon into public/icons/ (UI-7, ADR-0039).
//
// Chrome offers to install the app only when its manifest (src/app/manifest.ts) lists PNG icons of
// 192 and 512 pixels. The icon is a green square, a white building and a blue door, like the shop's
// godown. It has no letters and no shop's name, because one app serves every shop.
//
// Why a script and not a drawing app: anyone can read how the icon is made and make it again, and it
// needs only Node's own modules, so no package to install. Its PNG files are committed: the build
// never runs this script. Run it again only when the drawing changes, from frontend/:
//   node scripts/make-icons.mjs
//
// manifest.test.ts reads the PNG files and checks their colours against the tokens in globals.css,
// and that the Android icon stays inside its safe circle.
import { mkdirSync, writeFileSync } from "node:fs";
import { crc32, deflateSync } from "node:zlib";

// The tokens' colours, as [red, green, blue]: --primary and --secondary in globals.css.
const GREEN = [21, 128, 61];
const BLUE = [30, 64, 175];
const WHITE = [255, 255, 255];
// The door's pale lines: 60% white over the blue, so they read as a roller door and stay quiet.
const STRIPE = [165, 179, 223];

// The drawing lives on a grid of 64 by 64, so one drawing serves every size.
const GRID = 64;
const MIDDLE = GRID / 2;

// Each pixel is measured this many times across and down, then averaged. Without it, the sloping roof
// would look like stair-steps.
const SAMPLES = 4;

// - The first two show the drawing at full size, for Windows and for Android's plain icons.
// - "maskable": Android cuts an icon into a circle or a rounded square, and keeps only the circle in
//   the middle, 80% of the width, for sure. The building's corners reach past that circle at full
//   size, so here the drawing is 80% of its size, with a little room to spare.
const ICONS = [
  { file: "icon-192.png", size: 192, scale: 1 },
  { file: "icon-512.png", size: 512, scale: 1 },
  { file: "icon-maskable-512.png", size: 512, scale: 0.8 },
];

const folder = new URL("../public/icons/", import.meta.url);
mkdirSync(folder, { recursive: true });
for (const icon of ICONS) {
  const pixels = draw(icon);
  writeFileSync(new URL(icon.file, folder), png(icon.size, pixels));
  console.log(`wrote public/icons/${icon.file}`);
}

/** The colour at one point of the 64 by 64 drawing. */
function colourAt(x, y) {
  // The roof is highest in the middle (13) and falls to 26 at each wall (x is 10 or 54).
  const roofLine = 13 + Math.abs(x - MIDDLE) * (13 / 22);
  const inBuilding = x >= 10 && x <= 54 && y >= roofLine && y <= 49;
  if (!inBuilding) return GREEN;

  const inDoor = x >= 20 && x <= 44 && y >= 30;
  if (!inDoor) return WHITE;

  const onStripe = [35, 40, 45].some((line) => Math.abs(y - line) <= 0.75);
  return onStripe ? STRIPE : BLUE;
}

/** The colour of every pixel, row by row. */
function draw({ size, scale }) {
  const rows = [];
  for (let y = 0; y < size; y++) {
    const row = [];
    for (let x = 0; x < size; x++) row.push(averageAt(x, y, size, scale));
    rows.push(row);
  }
  return rows;
}

/** One pixel's colour: the average of the drawing at several points inside the pixel. */
function averageAt(pixelX, pixelY, size, scale) {
  // Where a point of the pixel falls on the grid. Dividing by scale shrinks the drawing around its
  // middle, so a smaller drawing stays centred.
  const onGrid = (pixel, step) => {
    const share = (pixel + (step + 0.5) / SAMPLES) / size;
    return (share * GRID - MIDDLE) / scale + MIDDLE;
  };

  const total = [0, 0, 0];
  for (let stepY = 0; stepY < SAMPLES; stepY++) {
    for (let stepX = 0; stepX < SAMPLES; stepX++) {
      const colour = colourAt(onGrid(pixelX, stepX), onGrid(pixelY, stepY));
      for (let channel = 0; channel < 3; channel++)
        total[channel] += colour[channel];
    }
  }
  return total.map((sum) => Math.round(sum / SAMPLES ** 2));
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
