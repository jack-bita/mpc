// shrink-photo.test.ts — a photo is made small on the laptop before it is kept (ATT-3, 03 §5.13): its
// longest side at most 1,600 px, its shape kept, and the first JPEG quality that comes to about 150 KB.
//
// The tests' browser (jsdom) has no canvas, so these test the two decisions, the size and the quality,
// with a pretend encoder. The drawing itself is proven in real Chromium, by the browser test of the
// clock-in photo (e2e/clock-in-photo.spec.ts).
import { describe, expect, it } from "vitest";

import {
  AIM,
  fitWithin,
  LONGEST_SIDE,
  QUALITIES,
  shrinkFrame,
  smallEnough,
} from "./shrink-photo";

describe("fitWithin", () => {
  it("brings a wide camera frame down to 1,600 px, keeping its shape", () => {
    // A laptop's full-HD webcam.
    expect(fitWithin(1920, 1080)).toEqual({ width: 1600, height: 900 });
  });

  it("brings a tall phone photo down by its height", () => {
    // The shop's own registered phone, held upright; a phone's 4000 × 3000 photo too.
    expect(fitWithin(1080, 1920)).toEqual({ width: 900, height: 1600 });
    expect(fitWithin(3000, 4000)).toEqual({ width: 1200, height: 1600 });
  });

  it("leaves a frame already small enough as it is", () => {
    // Most laptop webcams give 1280 × 720: nothing to shrink, only the quality to choose.
    expect(fitWithin(1280, 720)).toEqual({ width: 1280, height: 720 });
    expect(fitWithin(LONGEST_SIDE, 1200)).toEqual({
      width: 1600,
      height: 1200,
    });
  });

  it("never rounds a thin side down to nothing", () => {
    expect(fitWithin(10_000, 3)).toEqual({ width: 1600, height: 1 });
  });
});

/** A pretend encoder: the size each quality gives, and the qualities it was asked for, in order. */
function encoder(sizes: Record<number, number>) {
  const asked: number[] = [];
  const encode = (quality: number) => {
    asked.push(quality);
    return Promise.resolve(
      new Blob([new Uint8Array(sizes[quality] ?? 0)], { type: "image/jpeg" }),
    );
  };
  return { encode, asked };
}

describe("smallEnough", () => {
  it("keeps the first quality that comes to about 150 KB, and tries no lower", async () => {
    // A busy picture: the best two qualities are too big, the third fits.
    const { encode, asked } = encoder({
      0.85: 400_000,
      0.75: 260_000,
      0.65: 140_000,
      0.55: 100_000,
    });

    expect((await smallEnough(encode)).size).toBe(140_000);
    expect(asked).toEqual([0.85, 0.75, 0.65]);
  });

  it("keeps the best quality when it already fits", async () => {
    // A plain wall behind the worker: small at once, so the face stays as sharp as it can be.
    const { encode, asked } = encoder({ 0.85: 90_000 });

    expect((await smallEnough(encode)).size).toBe(90_000);
    expect(asked).toEqual([0.85]);
  });

  it("keeps the smallest when none fits", async () => {
    // Every quality over the aim: the smallest is still kept, and labelPhoto refuses it only over 1 MB.
    const sizes = Object.fromEntries(
      QUALITIES.map((quality, place) => [quality, AIM + 50_000 - place]),
    );
    const { encode, asked } = encoder(sizes);

    expect((await smallEnough(encode)).size).toBe(AIM + 50_000 - 4);
    expect(asked).toEqual([...QUALITIES]);
  });
});

describe("shrinkFrame", () => {
  it("refuses a frame with no picture in it yet", async () => {
    // A camera that has started but sent no frame reports a size of 0 × 0: nothing to draw, so the
    // clock-in goes on without a photo rather than with an empty one.
    await expect(shrinkFrame(new Image(), 0, 0)).rejects.toThrow();
  });
});
