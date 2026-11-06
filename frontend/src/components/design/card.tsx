// card.tsx — the shop's card: a white panel that groups one thing, like a sale's total (UI-8, ADR-0039).
//
// shadcn's card (components/ui/card.tsx) is plain <div>s; this piece sets the look. Its parts, in order:
// Card > CardHeader (CardTitle, CardDescription) > CardContent > CardFooter.
import {
  Card as ShadcnCard,
  CardContent as ShadcnCardContent,
  CardDescription as ShadcnCardDescription,
  CardFooter as ShadcnCardFooter,
  CardHeader as ShadcnCardHeader,
  CardTitle as ShadcnCardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

import type { PieceProps as Props } from "./types";

export function Card({
  className,
  ...props
}: Omit<Props<typeof ShadcnCard>, "size">) {
  return (
    <ShadcnCard
      // The shop's 8 px corners (--radius), not shadcn's rounder rounded-xl. The edge is the pale line
      // (--border), not shadcn's see-through dark ring (ring-foreground/10), a grey of no token's.
      // 16 px text, as everywhere in the shop.
      className={cn("rounded-lg text-base ring-border", className)}
      {...props}
    />
  );
}

export function CardHeader({
  className,
  ...props
}: Props<typeof ShadcnCardHeader>) {
  return (
    <ShadcnCardHeader className={cn("rounded-t-lg", className)} {...props} />
  );
}

export function CardTitle({
  className,
  ...props
}: Props<typeof ShadcnCardTitle>) {
  return (
    <ShadcnCardTitle
      className={cn("text-lg font-semibold", className)}
      {...props}
    />
  );
}

export function CardDescription({
  className,
  ...props
}: Props<typeof ShadcnCardDescription>) {
  return (
    <ShadcnCardDescription className={cn("text-base", className)} {...props} />
  );
}

export function CardContent(props: Props<typeof ShadcnCardContent>) {
  return <ShadcnCardContent {...props} />;
}

export function CardFooter({
  className,
  ...props
}: Props<typeof ShadcnCardFooter>) {
  return (
    <ShadcnCardFooter
      // The whole pale panel, not shadcn's half-faded one (bg-muted/50): the text pairs in
      // tokens.test.ts are checked on --muted itself.
      className={cn("rounded-b-lg bg-muted", className)}
      {...props}
    />
  );
}
