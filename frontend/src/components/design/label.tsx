// label.tsx — the shop's label: the name above a box, read aloud with it (UI-8, ADR-0039).
//
// shadcn's label (components/ui/label.tsx) is a plain <label>; this piece sets the look. A label must
// name its box with htmlFor, or a screen reader reads the box with no name. Field (field.tsx) does
// that for you, so most screens never use Label alone.
import { Label as ShadcnLabel } from "@/components/ui/label";
import { cn } from "@/lib/utils";

import type { PieceProps } from "./types";

export function Label({ className, ...props }: PieceProps<typeof ShadcnLabel>) {
  return (
    <ShadcnLabel
      // 16 px and semibold: shadcn's 14 px is small at arm's length, and the label is what tells a
      // seller which box is which. leading-snug, as a long Swahili label can run to two lines.
      className={cn("text-base leading-snug font-semibold", className)}
      {...props}
    />
  );
}
