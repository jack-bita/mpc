// signature-pad.test.tsx — the box a worker signs in (WAGE-9): named for a screen reader, drawn on by a finger, a pen
// or a mouse, emptied by Futa sahihi, and handed over as a JPEG only once something is drawn (ADR-0039).
//
// jsdom paints nothing, and has no canvas of its own: a stand-in records each stroke the pad asks for, and hands back a
// made-up JPEG, so these tests check what is asked and when. How it looks and draws is checked by eye on /design and a
// phone, and by the browser test, whose Chromium draws with the mouse (e2e/payslip.spec.ts).
import { act, fireEvent, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setLanguage } from "@/i18n/language";
import { render } from "@/test/render";

import { SignaturePad, type SignaturePadHandle } from "./signature-pad";

// What the pad asked the canvas to do, in order: each stroke's spots, each fill of white.
let asked: string[] = [];

function standInCanvas() {
  const paper = {
    scale: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    setTransform: vi.fn(),
    fillRect: vi.fn(() => asked.push("white")),
    beginPath: vi.fn(),
    arc: vi.fn((x: number, y: number) => asked.push(`dot ${x},${y}`)),
    fill: vi.fn(),
    moveTo: vi.fn((x: number, y: number) => asked.push(`from ${x},${y}`)),
    lineTo: vi.fn((x: number, y: number) => asked.push(`to ${x},${y}`)),
    stroke: vi.fn(),
  };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () => paper as unknown as CanvasRenderingContext2D,
  );
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(
    function toBlob(done: BlobCallback, type?: string) {
      asked.push(`saved as ${type}`);
      done(new Blob(["\xff\xd8 made up"], { type }));
    },
  );
}

beforeEach(() => {
  asked = [];
  standInCanvas();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function pad(props: Partial<Parameters<typeof SignaturePad>[0]> = {}) {
  const handle = createRef<SignaturePadHandle>();
  const onDrawnChange = vi.fn();
  render(
    <SignaturePad
      ref={handle}
      label="Sahihi ya Asha"
      hint="Asha achore sahihi yake kwa kidole."
      onDrawnChange={onDrawnChange}
      {...props}
    />,
  );
  return {
    handle,
    onDrawnChange,
    box: screen.getByRole("img", { name: "Sahihi ya Asha" }),
  };
}

function futa(): HTMLButtonElement {
  return screen.getByRole("button", {
    name: "Futa sahihi",
  }) as HTMLButtonElement;
}

function sign(box: HTMLElement, pointer: Record<string, unknown> = {}) {
  // Asha's finger down at one spot, dragged to two more, and lifted.
  const finger = { pointerId: 1, pointerType: "touch", button: 0, ...pointer };
  fireEvent.pointerDown(box, { ...finger, clientX: 10, clientY: 20 });
  fireEvent.pointerMove(box, { ...finger, clientX: 30, clientY: 25 });
  fireEvent.pointerMove(box, { ...finger, clientX: 50, clientY: 40 });
  fireEvent.pointerUp(box, { ...finger, clientX: 50, clientY: 40 });
}

describe("SignaturePad", () => {
  it("is named by its label and says who signs", () => {
    const { box } = pad();
    const hint = document.getElementById(
      box.getAttribute("aria-describedby") ?? "",
    );
    expect(hint?.textContent).toBe("Asha achore sahihi yake kwa kidole.");
    // Its label shows above it too, tied to the box.
    expect(screen.getByText("Sahihi ya Asha").getAttribute("for")).toBe(box.id);
  });

  it("starts white, with nothing to hand over and nothing to clear", async () => {
    const { handle } = pad();
    expect(asked).toEqual(["white"]);
    expect(futa().disabled).toBe(true);
    await expect(handle.current?.picture()).resolves.toBeNull();
  });

  it("draws a stroke as many short lines, from where the finger went down", () => {
    const { box, onDrawnChange } = pad();
    sign(box);
    expect(asked).toEqual([
      "white",
      "dot 10,20",
      "from 10,20",
      "to 30,25",
      "from 30,25",
      "to 50,40",
    ]);
    // Said once, at the first touch: Nimemlipa turns on as Asha starts.
    expect(onDrawnChange.mock.calls).toEqual([[true]]);
    expect(futa().disabled).toBe(false);
  });

  it("draws nothing once the finger is lifted, until it goes down again", () => {
    const { box } = pad();
    sign(box);
    fireEvent.pointerMove(box, { pointerId: 1, clientX: 90, clientY: 90 });
    expect(asked).not.toContain("to 90,90");
  });

  it("hands over what is drawn as a JPEG", async () => {
    const { box, handle } = pad();
    sign(box);
    let picture: Blob | null = null;
    await act(async () => {
      picture = (await handle.current?.picture()) ?? null;
    });
    expect(picture).toBeInstanceOf(Blob);
    expect((picture as Blob | null)?.type).toBe("image/jpeg");
    expect(asked.at(-1)).toBe("saved as image/jpeg");
  });

  it("starts again white with Futa sahihi", async () => {
    const { box, handle, onDrawnChange } = pad();
    sign(box);
    fireEvent.click(futa());
    expect(asked.at(-1)).toBe("white");
    expect(onDrawnChange.mock.calls).toEqual([[true], [false]]);
    expect(futa().disabled).toBe(true);
    await expect(handle.current?.picture()).resolves.toBeNull();
  });

  it("draws with a mouse's main button only", () => {
    const { box, onDrawnChange } = pad();
    sign(box, { pointerType: "mouse", button: 2 });
    expect(asked).toEqual(["white"]);
    sign(box, { pointerType: "mouse", button: 0 });
    expect(onDrawnChange).toHaveBeenCalledWith(true);
  });

  it("takes no stroke and no Futa while the payment is on its way", () => {
    const { box, onDrawnChange } = pad({ disabled: true });
    sign(box);
    expect(asked).toEqual(["white"]);
    expect(onDrawnChange).not.toHaveBeenCalled();
    expect(futa().disabled).toBe(true);
  });

  it("never scrolls the page under the finger", () => {
    const { box } = pad();
    expect(box.className.split(/\s+/)).toContain("touch-none");
  });

  it("says Futa sahihi in English too", () => {
    setLanguage("en");
    pad();
    expect(
      screen.getAllByRole("button", { name: "Clear the signature" }),
    ).toHaveLength(1);
  });
});
