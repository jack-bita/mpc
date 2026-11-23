// shrink-photo.ts — a photo made small on the device before it is kept (ATT-3, 03 §5.13): its longest
// side at most 1,600 px, its shape kept, saved as a JPEG of about 150 KB. It owns those three numbers and
// how a frame is drawn and saved. Shared: the clock-in's live camera (shrinkFrame), a worker's photo, taken
// or chosen on the manager's phone (shrinkFile, PPL-9), and next a supplier's paper (STK-4).
//
// Why on the laptop, before the photo is kept: the server keeps no file over 1 MB (CTRL-3), about twenty
// clock-ins a day go up on the shop's internet bundle (some 3 MB at 150 KB each), and every photo stays on
// the server's disk and in its backups for 90 days. A full-HD camera frame at the best quality is some
// 500 KB; a phone's own photo, 3 to 5 MB.
//
// Why a canvas: the frame is drawn onto a fresh sheet, and the sheet is saved. The copy holds the picture's
// pixels only, none of the hidden data a camera writes into its own files (Exif: where it was taken, which
// phone, when). Nothing to strip: it was never copied.
//
// Why JPEG, not WebP: every browser saves a canvas as a JPEG; older Safari can't save a WebP, and a shop's
// phone may be old. The server takes both (CTRL-3).
//
// Why steps of quality, and not one: how big a JPEG comes out depends on the picture, a plain wall small, a
// busy shelf big. The best quality that fits keeps the face as sharp as it can be.

/** The longest side a photo keeps, in pixels: a face, or a supplier's paper, still reads clearly. */
export const LONGEST_SIDE = 1600;

/** About 150 KB: the size a photo is brought down to, when a lower quality can bring it there. */
export const AIM = 150 * 1024;

/** The JPEG qualities tried, best first: 0.45 is still a clear face at 1,600 px. */
export const QUALITIES = [0.85, 0.75, 0.65, 0.55, 0.45] as const;

export interface Size {
  width: number;
  height: number;
}

/**
 * The size a frame is drawn at: its longest side at most 1,600 px, its shape kept. A frame already small
 * enough keeps its size, as drawing it bigger would only add bytes. A side is never rounded down to nothing.
 */
export function fitWithin(width: number, height: number): Size {
  const longest = Math.max(width, height);
  if (longest <= LONGEST_SIDE) return { width, height };
  const scale = LONGEST_SIDE / longest;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

/** Saves the drawn picture as a JPEG at one quality, from 0 to 1. */
export type Encode = (quality: number) => Promise<Blob>;

/**
 * The first JPEG, best quality first, that comes to about 150 KB; when none does, the smallest. Never over
 * the aim by choice: a photo still over 1 MB is refused by labelPhoto (src/offline/attachments.ts), as the
 * server would refuse it.
 */
export async function smallEnough(encode: Encode): Promise<Blob> {
  const [best, ...lower] = QUALITIES;
  let smallest = await encode(best);
  if (smallest.size <= AIM) return smallest;
  for (const quality of lower) {
    const photo = await encode(quality);
    if (photo.size <= AIM) return photo;
    if (photo.size < smallest.size) smallest = photo;
  }
  return smallest;
}

/**
 * Draws one frame (a live video, an image) onto a fresh canvas at its shrunk size, and saves it as a JPEG of
 * about 150 KB. `width` and `height` are the frame's own size: a video's `videoWidth` and `videoHeight`.
 * Throws when there is nothing to draw (a camera that sent no frame yet) or the browser can't draw: the
 * caller goes on without a photo.
 */
export async function shrinkFrame(
  source: CanvasImageSource,
  width: number,
  height: number,
): Promise<Blob> {
  if (width < 1 || height < 1)
    throw new Error("The frame has no picture in it yet.");
  const size = fitWithin(width, height);
  const canvas = document.createElement("canvas");
  canvas.width = size.width;
  canvas.height = size.height;
  const context = canvas.getContext("2d");
  if (context === null) throw new Error("This browser can't draw a photo.");
  // The whole frame, scaled into the whole sheet: nothing cut off.
  context.drawImage(source, 0, 0, size.width, size.height);
  return smallEnough((quality) => asJpeg(canvas, quality));
}

/**
 * A photo already taken, as a phone's camera app or its gallery hands it over (PPL-9): read, stood upright, and
 * shrunk as a live frame is. Throws when this browser can't read it: no picture at all, or a kind it doesn't know,
 * as some don't an iPhone's HEIC. The caller says so, and sends nothing.
 */
export async function shrinkFile(file: Blob): Promise<Blob> {
  // A phone held upright saves its photo lying down, with a note of which way is up (Exif), which the drawn copy won't
  // carry: turned as the note says while it is read, or every face would lie on its side. A browser does that by itself
  // (in Chromium, proven by e2e/workers.spec.ts), so no option asks for it: one that doesn't know the option's value by
  // name would throw at `imageOrientation: "from-image"`, and every photo on that phone would be one it can't read
  // (PPL-9's review).
  const picture = await createImageBitmap(file);
  try {
    return await shrinkFrame(picture, picture.width, picture.height);
  } finally {
    // Its pixels, some 50 MB for a phone's 12-megapixel photo, are let go of now, not when the browser gets to it.
    picture.close();
  }
}

// The canvas's own saving, which answers by a callback: as a promise, and an empty answer as a failure.
function asJpeg(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (photo) => {
        if (photo) resolve(photo);
        else reject(new Error("The browser couldn't save the photo."));
      },
      "image/jpeg",
      quality,
    );
  });
}
