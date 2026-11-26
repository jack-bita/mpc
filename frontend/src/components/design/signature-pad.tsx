// signature-pad.tsx — a box a worker signs in, with a finger on a phone or the mouse on a laptop, and Futa sahihi
// under it to start again (WAGE-9, ADR-0039): Asha's signature, as she is paid her November in cash, which proves she
// got it, as her signature on paper does at MPC today (Jack, 25 Nov 2026).
//
// How it draws: a canvas, a picture the page paints on. The browser tells it of a touch in three moments, one set for a
// finger, a pen and a mouse alike (pointer events): down, where the line starts; move, many times a second, each a
// short line from the last spot to this one, so many tiny lines make one smooth stroke; and up, the stroke ends. A tap
// with no move leaves a dot, as a full stop or an initial may be one. While the finger is down the canvas keeps every
// move to itself (setPointerCapture), so a stroke that runs off its edge and back is still one stroke.
//
// A drag on a phone scrolls the page; on this box it draws instead (`touch-none`, CSS's touch-action: none), or the
// sheet would slide under Asha's finger as she signs.
//
// What it holds is a picture, nothing else: the screen asks for it as a small JPEG (picture(), about 10 to 30 KB) as
// Nimemlipa is tapped, and sends it as the payment's body (pay-cash). Dark ink on white, painted in: a JPEG has no
// "nothing", and an empty canvas saved as one comes out black. It says whether anything is drawn (onDrawnChange), as
// Nimemlipa stays off until Asha has signed (Jack: A). Futa sahihi paints it white again.
//
// Its size: as wide as the sheet, a fixed height, drawn at the screen's own sharpness (devicePixelRatio, at most 2, so a
// picture stays small), set once as it opens. A phone turned while Asha signs keeps the picture as drawn, stretched to
// the new width: she may Futa and sign again.
//
// A screen reader names the box by its label, with the hint telling who signs. Nobody signs by keyboard: a signature is
// a hand's, and the worker is beside whoever pays them. On the demo a visitor draws too, and the screen keeps nothing
// (02 §12).
//
// "use client": it draws in the browser, and asks use-intl for Futa sahihi.
"use client";

import {
  type PointerEvent,
  type Ref,
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { useTranslations } from "use-intl";

import { cn } from "@/lib/utils";

import { Button } from "./button";
import { Label } from "./label";

/** What a screen may ask of the pad: the drawing, as a JPEG to send. */
export type SignaturePadHandle = {
  /** The drawing as a JPEG, or null when nothing is drawn. Throws when the browser can't save it. */
  picture: () => Promise<Blob | null>;
};

export type SignaturePadProps = {
  /** "Sahihi ya Asha": the box's name, shown above it and read by a screen reader. */
  label: string;
  /** "Asha achore sahihi yake kwa kidole.": who signs, under the label. */
  hint?: string;
  /** Called with true once a stroke is drawn, and with false once Futa sahihi empties it. */
  onDrawnChange?: (drawn: boolean) => void;
  /** Held while the payment is on its way: no stroke and no Futa, so the drawing sent is the one shown. */
  disabled?: boolean;
  ref?: Ref<SignaturePadHandle>;
};

// The box's height on screen, in CSS pixels: room for a signature written large, as on a phone a finger writes big.
const HEIGHT = 160;
// The ink: the text's own colour (--foreground), read once from the page, so the signature looks as the words do.
const INK_FALLBACK = "#17231b";
// A stroke as wide as a pen's, in CSS pixels; round at its ends and corners, so the tiny lines join with no gaps.
const LINE_WIDTH = 2.5;
// At most twice the CSS pixels: sharper adds nothing a person can see, and makes the picture bigger to send.
const MOST_SHARPNESS = 2;
// How much detail the JPEG keeps: plenty for lines of one colour on white.
const QUALITY = 0.85;

export function SignaturePad({
  label,
  hint,
  onDrawnChange,
  disabled = false,
  ref,
}: SignaturePadProps) {
  const t = useTranslations("signaturePad");
  const id = useId();
  const canvas = useRef<HTMLCanvasElement>(null);
  // The spot the last line ended at, while a stroke goes on; null between strokes.
  const last = useRef<{ x: number; y: number } | null>(null);
  const [drawn, setDrawn] = useState(false);

  function paper(): CanvasRenderingContext2D | null {
    return canvas.current?.getContext("2d") ?? null;
  }

  // Sized to the box as it opens, at the screen's sharpness, and painted white.
  useEffect(() => {
    const box = canvas.current;
    if (box === null) return;
    const sharpness = Math.min(window.devicePixelRatio || 1, MOST_SHARPNESS);
    box.width = Math.round((box.clientWidth || 300) * sharpness);
    box.height = Math.round(HEIGHT * sharpness);
    const context = box.getContext("2d");
    if (context === null) return;
    // From here on, the drawing counts in CSS pixels, as the pointer's spots do.
    context.scale(sharpness, sharpness);
    whiten(context, box);
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      picture: () =>
        drawn && canvas.current
          ? asJpeg(canvas.current)
          : Promise.resolve(null),
    }),
    [drawn],
  );

  function spot(event: PointerEvent<HTMLCanvasElement>) {
    // Where the pointer is, in the box's own CSS pixels.
    const edge = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - edge.left, y: event.clientY - edge.top };
  }

  function start(event: PointerEvent<HTMLCanvasElement>) {
    if (disabled) return;
    // A mouse's other buttons draw nothing: only its main one, as a pen does on paper.
    if (event.pointerType === "mouse" && event.button !== 0) return;
    const context = paper();
    if (context === null) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const at = spot(event);
    last.current = at;
    // A dot where the stroke starts: a tap alone leaves a mark.
    context.fillStyle = ink(event.currentTarget);
    context.beginPath();
    context.arc(at.x, at.y, LINE_WIDTH / 2, 0, Math.PI * 2);
    context.fill();
    if (!drawn) {
      setDrawn(true);
      onDrawnChange?.(true);
    }
  }

  function move(event: PointerEvent<HTMLCanvasElement>) {
    const from = last.current;
    const context = paper();
    if (from === null || context === null) return;
    const to = spot(event);
    context.strokeStyle = ink(event.currentTarget);
    context.lineWidth = LINE_WIDTH;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.beginPath();
    context.moveTo(from.x, from.y);
    context.lineTo(to.x, to.y);
    context.stroke();
    last.current = to;
  }

  function end() {
    last.current = null;
  }

  function clear() {
    const box = canvas.current;
    const context = paper();
    if (box === null || context === null) return;
    whiten(context, box);
    last.current = null;
    setDrawn(false);
    onDrawnChange?.(false);
  }

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      {hint ? (
        <p id={`${id}-hint`} className="text-sm text-muted-foreground">
          {hint}
        </p>
      ) : null}
      <canvas
        ref={canvas}
        id={id}
        // A picture a hand draws: a screen reader names it by its label, and says who signs.
        role="img"
        aria-label={label}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onPointerDown={start}
        onPointerMove={move}
        onPointerUp={end}
        onPointerCancel={end}
        onLostPointerCapture={end}
        style={{ height: HEIGHT }}
        className={cn(
          // As wide as the sheet; the box's edge as a text box's (--input), so it reads as a place to write.
          "block w-full rounded-lg border border-input bg-white",
          // A drag draws here; it never scrolls the page (above).
          "touch-none",
          disabled && "opacity-50",
        )}
      />
      <div className="flex justify-end">
        <Button
          type="button"
          kind="second"
          size="normal"
          onClick={clear}
          disabled={disabled || !drawn}
        >
          {t("clear")}
        </Button>
      </div>
    </div>
  );
}

function whiten(context: CanvasRenderingContext2D, box: HTMLCanvasElement) {
  // White over the whole sheet, in its own pixels: a JPEG has no "nothing", and an empty one would come out black.
  context.save();
  context.setTransform(1, 0, 0, 1, 0, 0);
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, box.width, box.height);
  context.restore();
}

function ink(box: HTMLCanvasElement): string {
  // The text's colour, as the page has it: a token, never a value of the screen's own (ADR-0039).
  const colour = getComputedStyle(box).getPropertyValue("--foreground").trim();
  return colour || INK_FALLBACK;
}

function asJpeg(box: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    box.toBlob(
      (picture) => {
        if (picture) resolve(picture);
        else reject(new Error("The browser couldn't save the signature."));
      },
      "image/jpeg",
      QUALITY,
    );
  });
}
