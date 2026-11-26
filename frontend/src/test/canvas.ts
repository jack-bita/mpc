// canvas.ts — a stand-in canvas for tests of the signature box (WAGE-9). Tests only. jsdom has no canvas of its own, so
// this records each stroke the box asks for, and hands back a made-up JPEG, as signature-pad.test.tsx does for itself.
import { fireEvent } from "@testing-library/react";
import { vi } from "vitest";

/** The made-up JPEG every saved signature comes back as: a JPEG's first bytes, then words that are no picture. */
export const DRAWN = "\xff\xd8\xff\xe0 Asha's signature, made up";

/** A canvas that draws nothing and saves DRAWN. Undone by vi.restoreAllMocks(), as every test file's afterEach does. */
export function standInCanvas(): void {
  const paper = {
    scale: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    setTransform: vi.fn(),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
  };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () => paper as unknown as CanvasRenderingContext2D,
  );
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(
    function toBlob(done: BlobCallback, type?: string) {
      done(new Blob([DRAWN], { type }));
    },
  );
}

/** A finger drawing one stroke on a signature box. */
export function signOn(box: HTMLElement): void {
  const finger = { pointerId: 1, pointerType: "touch", button: 0 };
  fireEvent.pointerDown(box, { ...finger, clientX: 10, clientY: 20 });
  fireEvent.pointerMove(box, { ...finger, clientX: 40, clientY: 30 });
  fireEvent.pointerUp(box, { ...finger, clientX: 40, clientY: 30 });
}
