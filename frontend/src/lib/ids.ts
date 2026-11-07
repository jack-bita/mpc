// ids.ts — the id of a new row, made on the device: a UUID of version 7 (ADR-0007, 03 §5.10).
//
// The app names every new row itself, before it sends it. A request sent twice, by a double tap or
// after an answer lost on a weak network, then carries the same id both times, so the server finds the
// row the first one made and answers with it, never making a second (CreateOnceMixin,
// backend/apps/core/api/base.py). Offline documents will need the same: a device makes them with no
// server to ask for a number.
//
// Version 7, not the browser's own crypto.randomUUID(), which makes version 4: the server refuses any
// other version (id.not_uuid7, backend/apps/core/api/ids.py). Its first 48 bits are the time it was
// made, so new rows land side by side at the end of the table's index, where random ids would scatter
// them across it (ADR-0007). The other 74 bits are random, from the browser's secure random source.
//
// The layout, RFC 9562 §5.7, as 16 bytes:
//   0–5   the time, in milliseconds since 1 Jan 1970 (UTC), biggest byte first
//   6     0111 (the version, 7), then 4 random bits
//   7     8 random bits
//   8     10 (the variant: "this is an RFC 9562 UUID"), then 6 random bits
//   9–15  56 random bits
//
// Two ids made in the same millisecond are in no set order between them: RFC 9562 lets a maker keep a
// counter for that, and we don't need one. An id says only "this row", never "which came first": the
// order of a device's documents is the outbox's own (03 §6), and of the server's changes, their numbers
// (SYNC-1).

/** The largest time 48 bits can hold: about the year 10889. */
const LAST_MILLISECOND = 2 ** 48 - 1;

/**
 * A UUIDv7 from a time and 16 random bytes, of which the first 6 are not used: the time takes their
 * place. Split from newId() so a test can give a known time and known bytes, and check the answer
 * against RFC 9562's own example.
 */
export function uuidv7(milliseconds: number, random: Uint8Array): string {
  if (
    !Number.isInteger(milliseconds) ||
    milliseconds < 0 ||
    milliseconds > LAST_MILLISECOND
  )
    throw new RangeError(`A UUIDv7's time must fit 48 bits: ${milliseconds}`);
  if (random.length !== 16)
    throw new RangeError("A UUIDv7 needs 16 random bytes.");

  const bytes = Uint8Array.from(random);
  // The time, one byte at a time from the smallest end. Division, not JavaScript's bit shifts: those
  // work on 32 bits only, and the time needs 48. Every step is a whole number below 2^53, so exact.
  let time = milliseconds;
  for (let index = 5; index >= 0; index -= 1) {
    bytes[index] = time % 256;
    time = Math.floor(time / 256);
  }
  // The version in the top 4 bits of byte 6, and the variant in the top 2 of byte 8, each over the
  // random bits that were there. Without them the server reads another version and refuses the id.
  // The "!" says the byte is there, which TypeScript can't see: the length was checked above.
  bytes[6] = 0x70 | (bytes[6]! & 0x0f);
  bytes[8] = 0x80 | (bytes[8]! & 0x3f);

  // 32 hex digits, lowercase as Python writes a UUID, with dashes after the 8th, 12th, 16th and 20th.
  const hex = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join("-");
}

/** The id of a new row: now, and 16 bytes from the browser's secure random source. */
export function newId(): string {
  // getRandomValues, not Math.random(): Math.random() is made for games, and its numbers can be
  // foreseen from earlier ones, so two devices could make the same id far more often than chance.
  return uuidv7(Date.now(), crypto.getRandomValues(new Uint8Array(16)));
}
