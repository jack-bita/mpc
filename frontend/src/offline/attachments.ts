// attachments.ts — a photo taken on this laptop, before it is saved with its record (CTRL-6, 03 §5.13): its label,
// read from its own bytes, and the checks that refuse at the counter a photo the server would refuse.
//
// A photo goes up in two parts, at two moments. Its label (id, kind, type, size, SHA-256) travels inside its record:
// the server writes the photo's row from it, in the record's own transaction (expect_attachment, ATT-3). Its bytes
// wait on the laptop, in attachment_files, and go up once the record is in (sync/attachments.ts); the server checks
// them against the label (CTRL-3).
//
// So a screen labels the photo first, with labelPhoto(), puts the label into its record's payload, and hands both to
// saveDocument() (outbox.ts), which writes the record and the photo in one transaction. The label is worked out
// before that transaction opens, on purpose: the SHA-256 comes from the browser's crypto.subtle, and a Dexie
// transaction ends at the first wait on a promise that isn't Dexie's, so working it out inside would end the
// transaction halfway (the card's Watch out).
import { newId } from "@/lib/ids";

import type { AttachmentFileRow, PhotoKind, PhotoType } from "./db";

/** The largest photo the server keeps: 1 MB, to the byte (CTRL-3). A camera's photo is shrunk well below it first
 * (about 150 KB, ATT-3). */
export const LARGEST_PHOTO = 1_048_576;

/** What a record says of its photo: the fields the server writes its row from, and checks the file against. */
export type PhotoLabel = Pick<
  AttachmentFileRow,
  "id" | "kind" | "content_type" | "size" | "sha256"
>;

/** A photo ready to save with its record: its label, which the record's payload carries, and its bytes, which wait
 * on the laptop. */
export interface LabelledPhoto {
  label: PhotoLabel;
  bytes: ArrayBuffer;
}

/** Why a photo can't be saved: the server would refuse it (`too_big`, `not_an_image`, under the same names as its
 * codes), or its record doesn't name it (`not_named`). Each a bug in the screen or the camera, never the person's:
 * kept, the photo would only wait on the laptop to be set aside, so it fails at the counter instead. */
export type PhotoProblem = "too_big" | "not_an_image" | "not_named";

export class BrokenPhoto extends Error {
  constructor(readonly problem: PhotoProblem) {
    super(`The photo can't be saved: ${problem}.`);
    this.name = "BrokenPhoto";
  }
}

/**
 * Labels a photo: its type by its first bytes, its size, its SHA-256, and a new id. Refused when the server would
 * refuse the file: over 1 MB, or not a JPEG or a WebP. The type comes from the bytes, never from what the file says
 * it is (`file.type`), as the server reads the bytes too: a label that disagreed with them would get the photo set
 * aside as `file_differs`, once its record was in.
 */
export async function labelPhoto(
  file: Blob,
  kind: PhotoKind,
): Promise<LabelledPhoto> {
  // Asked before the type, as the server asks (its route reads the length first), and before the file is read: a
  // phone's own 12 MB photo, handed over unshrunk by mistake, is refused without being read into memory first.
  if (file.size > LARGEST_PHOTO) throw new BrokenPhoto("too_big");
  const bytes = await file.arrayBuffer();
  const contentType = imageTypeOf(new Uint8Array(bytes));
  if (contentType === null) throw new BrokenPhoto("not_an_image");
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return {
    label: {
      id: newId(),
      kind,
      content_type: contentType,
      size: bytes.byteLength,
      sha256: toHex(new Uint8Array(digest)),
    },
    bytes,
  };
}

/**
 * Refuses a photo whose record doesn't name its id anywhere in its payload: the server writes a photo's row only
 * from its record's label, so a photo the record forgot would find no row, and wait on the laptop for good. Where
 * the payload names it is each record's own (ATT-3, STK-4), so the whole payload is searched.
 */
export function checkPhotosNamed(
  payload: unknown,
  photos: readonly LabelledPhoto[],
): void {
  for (const photo of photos)
    if (!names(payload, photo.label.id)) throw new BrokenPhoto("not_named");
}

/** What a file is, by its first bytes, as the server tells (CTRL-3): every JPEG starts with FF D8 FF, and every WebP
 * with "RIFF", its length in four bytes, then "WEBP". An empty file is neither. A worker's photo that comes down is
 * read the same way (PPL-14, sync/staff-photos.ts). */
export function imageTypeOf(bytes: Uint8Array): PhotoType | null {
  if (startsWith(bytes, 0, [0xff, 0xd8, 0xff])) return "image/jpeg";
  if (
    startsWith(bytes, 0, ascii("RIFF")) &&
    startsWith(bytes, 8, ascii("WEBP"))
  )
    return "image/webp";
  return null;
}

function startsWith(
  bytes: Uint8Array,
  at: number,
  expected: readonly number[],
): boolean {
  return expected.every((byte, i) => bytes[at + i] === byte);
}

function ascii(text: string): number[] {
  return Array.from(text, (letter) => letter.charCodeAt(0));
}

// Lower case, two digits a byte, as the server writes a SHA-256 (hashlib's hexdigest) and compares it.
function toHex(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
}

// Whether `value` holds the string `id`, at any depth: in an object's values or a list's items.
function names(value: unknown, id: string): boolean {
  if (value === id) return true;
  if (typeof value !== "object" || value === null) return false;
  return Object.values(value).some((inner) => names(inner, id));
}
