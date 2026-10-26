// page-size.ts — how big the paper must be for the slip (SPIKE-2).
//
// CSS can't say "a page as long as its content": `size: 80mm auto` is invalid and Chrome drops
// it (04 v1.11). So the slip page measures the slip and writes its length into
// `@page { size: … }` itself, just before printing.

/** The roll's width (OWN-1: the shop's Epson takes 80 mm paper). */
const PAPER_WIDTH_MM = 80;

/** In CSS, 96 px is always one inch, and an inch is 25.4 mm. */
const MM_PER_PX = 25.4 / 96;

/**
 * The `@page` size for a slip `heightPx` CSS pixels tall, such as "80mm 106mm".
 * Rounded up to a whole millimetre: a page a hair too short would push the slip's last line
 * onto a second page.
 */
export function pageSizeFor(heightPx: number): string {
  const heightMm = Math.ceil(heightPx * MM_PER_PX);
  return `${PAPER_WIDTH_MM}mm ${heightMm}mm`;
}
