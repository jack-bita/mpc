// button.tsx — the shop's button: the one every screen uses for an action (UI-8, ADR-0039).
//
// shadcn's button (components/ui/button.tsx) gives the behaviour, through Base UI: a real <button>, the
// keyboard, focus, and type="button" unless told otherwise, so a button inside a form never sends it by
// accident. This piece only sets the look. It hands shadcn's button our classes, and the cn() inside it
// lets ours win wherever the two clash (shadcn's h-8 gives way to our height).
//
// Three kinds, by what pressing does:
//   main    green, filled: the one action a screen is for (Uza, Hifadhi).
//   second  blue outline: another action beside it (Rudi, Ghairi).
//   danger  faded-red outline: an action that takes something away (Batilisha). An outline, not a
//           fill: it must never shout louder than the screen's main action.
// Two heights: big (52 px, the default, sized for a finger at the counter) and normal (44 px).
//
// button.test.tsx does the sums on the classes the browser really gets: every kind's text reads at
// 4.5:1 at rest, on hover and when pressed, on a white screen and on a pale panel.
import { cva } from "class-variance-authority";

import { Button as ShadcnButton } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { PieceProps } from "./types";

export const BUTTON_KINDS = ["main", "second", "danger"] as const;
export const BUTTON_SIZES = ["big", "normal"] as const;

export type ButtonKind = (typeof BUTTON_KINDS)[number];
export type ButtonSize = (typeof BUTTON_SIZES)[number];

const look = cva(
  [
    "rounded-lg font-semibold",
    // Full strength: shadcn fades the ring to half (ring-ring/50), which reads at only 2.57:1 on white,
    // under the 3:1 that someone on a keyboard needs to see where they are (UI-7). It reads --ring, so
    // a green area can set --ring to white for what sits on it (UI-1's top bar).
    "focus-visible:ring-ring",
  ],
  {
    variants: {
      kind: {
        main: [
          "bg-primary text-primary-foreground",
          // Darker on hover and press, never faded. White on green faded to 90% reads at only 4.17:1
          // (shadcn fades it to 80%); on green darkened to 88% it reads at 6.1:1, and at 80% darker still.
          "hover:bg-[color-mix(in_srgb,var(--primary)_88%,black)]",
          "active:bg-[color-mix(in_srgb,var(--primary)_80%,black)]",
        ],
        second: [
          "border-secondary bg-background text-secondary",
          // A light tint of its own blue, and the text stays blue: shadcn's outline turns grey with
          // dark text on hover, and the button would stop looking like itself.
          "hover:bg-secondary/5 hover:text-secondary active:bg-secondary/5",
          "aria-expanded:bg-secondary/5 aria-expanded:text-secondary",
        ],
        danger: [
          "border-destructive bg-background text-destructive",
          // 5% at most. The tint is see-through, so on a pale panel it sits over the panel: there the
          // faded red reads at 4.52:1 on a 5% tint, and at only 4.21:1 on 10% (UI-7's sums).
          "hover:bg-destructive/5 hover:text-destructive active:bg-destructive/5",
          "aria-expanded:bg-destructive/5 aria-expanded:text-destructive",
        ],
      },
      size: {
        // h-(--control-big), not h-control-big: cn() knows this spelling is a height and drops
        // shadcn's h-8. With the other one it keeps both, and CSS order decides (src/lib/utils.ts).
        big: [
          "h-(--control-big) gap-2 px-5 text-lg",
          "has-data-[icon=inline-end]:pr-4 has-data-[icon=inline-start]:pl-4",
          "[&_svg:not([class*='size-'])]:size-5",
        ],
        normal: [
          "h-(--control-normal) gap-2 px-4 text-base",
          "has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3",
          "[&_svg:not([class*='size-'])]:size-5",
        ],
      },
    },
  },
);

type ButtonProps = Omit<PieceProps<typeof ShadcnButton>, "variant" | "size"> & {
  kind?: ButtonKind;
  size?: ButtonSize;
};

export function Button({
  kind = "main",
  size = "big",
  className,
  ...props
}: ButtonProps) {
  return (
    <ShadcnButton
      // The outlines start from shadcn's outline, not its "destructive": that one is a pink fill with
      // a faint red focus ring (ring-destructive/20), and both would need undoing.
      variant={kind === "main" ? "default" : "outline"}
      className={cn(look({ kind, size }), className)}
      {...props}
    />
  );
}
