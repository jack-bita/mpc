// photos.ts — made-up photos, for tests (CTRL-6). Tests only.
//
// Never a real photo: the repo is public and holds no one's face (rule 10). A made-up photo is a few
// bytes that start as a JPEG or a WebP does, which is all the laptop and the server look at (03 §5.13);
// the rest is counting bytes, so two photos of one size are still the same file.

/** The bytes every JPEG starts with. */
const JPEG_START = [0xff, 0xd8, 0xff];

/** A made-up JPEG of `size` bytes (64 unless given), as the browser hands a camera's photo over. */
export function madeUpJpeg(size = 64, type = "image/jpeg"): Blob {
  return new Blob([withStart(JPEG_START, size)], { type });
}

/** A made-up WebP of `size` bytes: "RIFF", the file's length in four bytes, then "WEBP". */
export function madeUpWebp(size = 64): Blob {
  const riff = [...ascii("RIFF"), 0, 0, 0, 0, ...ascii("WEBP")];
  return new Blob([withStart(riff, size)], { type: "image/webp" });
}

/** A made-up PNG: a photo of a kind the server doesn't keep. */
export function madeUpPng(size = 64): Blob {
  const png = [0x89, ...ascii("PNG"), 0x0d, 0x0a, 0x1a, 0x0a];
  return new Blob([withStart(png, size)], { type: "image/png" });
}

function withStart(
  start: readonly number[],
  size: number,
): Uint8Array<ArrayBuffer> {
  const bytes = new Uint8Array(size);
  for (let i = 0; i < size; i += 1) bytes[i] = start[i] ?? i % 256;
  return bytes;
}

function ascii(text: string): number[] {
  return Array.from(text, (letter) => letter.charCodeAt(0));
}
