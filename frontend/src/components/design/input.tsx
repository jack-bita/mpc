// input.tsx — the shop's box to type in: a name, a phone number, kilos (UI-8, ADR-0039).
//
// shadcn's input (components/ui/input.tsx) gives the behaviour through Base UI; this piece sets the look.
// Most screens want Field (field.tsx), which adds the label and the error. Use Input alone only where
// a visible label would get in the way, like a search box, and then give it an aria-label.
import { cva } from "class-variance-authority";

import { Input as ShadcnInput } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import type { PieceProps } from "./types";

export const INPUT_SIZES = ["big", "normal"] as const;
export type InputSize = (typeof INPUT_SIZES)[number];

const look = cva(
  [
    // White, with the dark edge (--input, 3:1 on white and on a pale panel): a box on a white screen
    // shows only its edge, so the edge is what says "type here" (UI-7).
    "rounded-lg border-input bg-background px-3",
    // 16 px on every screen. shadcn drops to 14 px on laptops (md:text-sm); on a phone, text under
    // 16 px also makes the browser zoom in when the box is touched.
    "text-base md:text-base",
    // Full strength: shadcn's ring-ring/50 reads at only 2.57:1 on white (UI-7).
    "focus-visible:ring-ring",
    // An error shows as a red edge. shadcn's error rule comes later in Tailwind's CSS than the focus
    // ring, so a focused box with an error would show only a faint pink ring (ring-destructive/20).
    // This class comes later still, and keeps the blue ring on the box you are typing in.
    "aria-invalid:focus-visible:ring-ring",
    // Switched off: the pale panel. shadcn paints it with --input at half strength (bg-input/50), and
    // --input is now the dark edge colour, so that would be a heavy grey (UI-7).
    "disabled:bg-muted",
  ],
  {
    variants: {
      size: {
        // h-(--control-big), not h-control-big: cn() knows this spelling is a height (src/lib/utils.ts).
        big: "h-(--control-big)",
        normal: "h-(--control-normal)",
      },
    },
  },
);

// `size` is ours, as on Button. The browser's own size attribute (a width in letters) goes, as the
// layout sets widths.
export type InputProps = Omit<PieceProps<typeof ShadcnInput>, "size"> & {
  size?: InputSize;
};

export function Input({ size = "big", className, ...props }: InputProps) {
  return <ShadcnInput className={cn(look({ size }), className)} {...props} />;
}
