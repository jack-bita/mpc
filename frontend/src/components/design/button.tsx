// button.tsx — the shop's button: the one every screen uses for an action (UI-8, ADR-0039).
//
// shadcn's button (components/ui/button.tsx) gives the behaviour, through Base UI: a real <button>, the
// keyboard, focus, and type="button" unless told otherwise, so a button inside a form never sends it by
// accident. This piece only sets the look. It hands shadcn's button our classes, and the cn() inside it
// lets ours win wherever the two clash (shadcn's h-8 gives way to our height).
//
// Three kinds for screens, by what pressing does:
//   main    green, filled: the one action a screen is for (Uza, Hifadhi).
//   second  blue outline: another action beside it (Rudi, Ghairi).
//   danger  faded-red outline: an action that takes something away (Batilisha). An outline, not a
//           fill: it must never shout louder than the screen's main action.
// And one for the green top bar (UI-1), where none of the three can sit: the green main button
// vanishes into the green, and the blue outline reads at only 1.74:1 on it.
//   bar     the main button with a white edge: green on green, so the edge is what shows it.
// Two heights: big (52 px, the default, sized for a finger at the counter) and normal (44 px).
//
// ButtonLink, below, is the same look on a link: for a step that opens another page, like Sajili kifaa
// hiki on the home page (UI-3). A real link, so a screen reader says "link" and Enter follows it.
//
// button.test.tsx does the sums on the classes the browser really gets: every kind's text reads at
// 4.5:1 at rest, on hover and when pressed, on what it sits on: a white screen and a pale panel, or
// for the bar kind, the green bar.
import { cva } from "class-variance-authority";
import Link from "next/link";
import type { ComponentProps } from "react";

import { buttonVariants, Button as ShadcnButton } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type { PieceProps } from "./types";

export const BUTTON_KINDS = ["main", "second", "danger", "bar"] as const;
// The kinds a screen uses, on a white screen or a pale panel. "bar" sits only on the green top bar.
export const SCREEN_BUTTON_KINDS = ["main", "second", "danger"] as const;
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
    // shadcn's error ring (aria-invalid:ring-destructive/20) comes later in Tailwind's CSS than the one
    // above, so a focused button with an error, like a date picker a form refused, would show only a
    // faint pink ring. This comes later still, as on the box (input.tsx).
    "aria-invalid:focus-visible:ring-ring",
    // Switched off, it looks and acts switched off, however it was switched off. shadcn fades only a
    // button with the real disabled attribute (disabled:opacity-50). One that stays reachable by Tab
    // (focusableWhenDisabled, so a screen reader can still find it) has aria-disabled instead, and
    // would look ready to press. Base UI marks both with data-disabled. Faded to half on purpose: the
    // main button's white then reads at about 2:1, but WCAG asks no contrast of a control that can't be
    // used, and the fade is what says it can't.
    "data-disabled:pointer-events-none data-disabled:opacity-50",
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
        bar: [
          // The main button's colours and hover, so its white text keeps the same sums: 5.02:1 on the
          // green, 6.1:1 on hover. Its own green paint, not see-through: what it reads on is known.
          "bg-primary text-primary-foreground",
          "hover:bg-[color-mix(in_srgb,var(--primary)_88%,black)]",
          "active:bg-[color-mix(in_srgb,var(--primary)_80%,black)]",
          // The white edge is the button's outline on the green: 5.02:1, where WCAG asks 3:1 of the
          // edge of a control. The focus ring reads --ring, which the top bar sets to white.
          "border-primary-foreground",
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

// The outlines start from shadcn's outline, not its "destructive": that one is a pink fill with a faint
// red focus ring (ring-destructive/20), and both would need undoing. The two filled kinds start from its
// default, the filled one.
function shadcnVariant(kind: ButtonKind): "default" | "outline" {
  return kind === "main" || kind === "bar" ? "default" : "outline";
}

export function Button({
  kind = "main",
  size = "big",
  className,
  ...props
}: ButtonProps) {
  return (
    <ShadcnButton
      variant={shadcnVariant(kind)}
      className={cn(look({ kind, size }), className)}
      {...props}
    />
  );
}

/**
 * A link that looks like the button of its kind. Not Base UI's button with a link inside: its docs say
 * it must not be used for links, as it tells a screen reader "button" and takes the Space key. So this
 * is Next's own Link, a real <a>, given exactly the classes shadcn's button would get, joined the same
 * way, so every colour sum in button.test.tsx holds for it too (the test compares the two). No `bar`
 * kind and no switched-off look: a link on the green bar, or a link that can't be followed, waits for
 * a screen that needs one.
 */
export function ButtonLink({
  kind = "main",
  size = "big",
  className,
  ...props
}: Omit<ComponentProps<typeof Link>, "className"> & {
  kind?: (typeof SCREEN_BUTTON_KINDS)[number];
  size?: ButtonSize;
  className?: string;
}) {
  return (
    <Link
      className={cn(
        buttonVariants({
          variant: shadcnVariant(kind),
          className: cn(look({ kind, size }), className),
        }),
      )}
      {...props}
    />
  );
}
