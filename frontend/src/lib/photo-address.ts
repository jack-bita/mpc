// photo-address.ts — where an office screen opens a photo's file: the photos' own route, behind each kind's key (CTRL-3,
// 03 §5.13). A clock-in's photo on the attendance page (ATT-12), a worker's on their own page (PPL-9).
//
// An address for an <img>, not a call of the typed client: the browser asks for it itself, and sends the office's login
// with it. The answer is never kept by the browser (no-store), so a photo behind a key taken away stops opening.

/** The address of a photo's file, by the photo's id. */
export function photoAddress(id: string): string {
  return `/api/v1/control/attachments/${id}/file/`;
}
