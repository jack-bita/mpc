// side-band.tsx — the thin strip under the top bar that shows, by colour, which side a screen is for
// (UI-8, ADR-0039).
//
// The shop's two sides look different in real life: the green container of the Drugs side, the Foods
// bags with their faded-red stripes. So the band comes in two looks:
//   blue     the blue at the godown's back
//   striped  white and faded red, like the Foods bags
// Which side gets which look is still open (04 §20, item 19), so a screen must always say.
//
// Colour only, with no words (Jack, 6 Nov 2026). The side's name stays in words in the top bar (UI-1),
// so nobody has to tell colours apart to know where they are, and no word ever sits on red and white
// stripes, where it would be hard to read. That makes the band decoration: it is hidden from screen
// readers, and it needs no contrast check (WCAG asks 3:1 only of what must be seen).
import { cn } from "@/lib/utils";

export const SIDE_BAND_LOOKS = ["blue", "striped"] as const;
export type SideBandLook = (typeof SIDE_BAND_LOOKS)[number];

const LOOK: Record<SideBandLook, string> = {
  blue: "bg-secondary",
  // Upright stripes 8 px wide, drawn from the tokens by name, so a changed token changes the band too.
  // "image:" tells Tailwind this is a picture for the background, not a colour.
  striped:
    "bg-[image:repeating-linear-gradient(90deg,var(--destructive)_0_8px,var(--background)_8px_16px)]",
};

export function SideBand({
  look,
  className,
}: {
  look: SideBandLook;
  className?: string;
}) {
  return (
    <div
      aria-hidden="true"
      data-look={look}
      // 6 px: enough to see at a glance, thin enough to leave the screen to the sale.
      className={cn("h-1.5 w-full", LOOK[look], className)}
    />
  );
}
