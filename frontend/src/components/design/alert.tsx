// alert.tsx — the shop's message box, for news a screen must tell (UI-8, ADR-0039).
//
// shadcn's alert (components/ui/alert.tsx) is plain <div>s; this piece sets the look, and how loudly a
// screen reader says it. Two kinds:
//   info    a blue edge. Something to know, like Inahitaji mtandao (UI-1). role="status": when its
//           text changes, a screen reader says it once it has finished what it was saying. A box that
//           appears with its text already in it may not be said at all (NVDA with Chrome, VoiceOver),
//           so news that comes and goes needs its status area on the page first, and its text later.
//   danger  faded red. Something went wrong, like a sale that was refused. role="alert": a screen
//           reader stops and says it at once, also when the box appears with its text in it. The
//           faded red is for warnings only (ADR-0039).
// Its parts: Alert > (an icon, AlertTitle, AlertDescription).
import { cva } from "class-variance-authority";

import {
  Alert as ShadcnAlert,
  AlertDescription as ShadcnAlertDescription,
  AlertTitle as ShadcnAlertTitle,
} from "@/components/ui/alert";
import { cn } from "@/lib/utils";

import type { PieceProps as Props } from "./types";

export const ALERT_KINDS = ["info", "danger"] as const;
export type AlertKind = (typeof ALERT_KINDS)[number];

const look = cva(
  // 16 px text with room around it, and an icon of 20 px.
  "gap-1 rounded-lg bg-background px-4 py-3 text-base *:[svg:not([class*='size-'])]:size-5",
  {
    variants: {
      kind: {
        info: "border-secondary text-foreground *:[svg]:text-secondary",
        // Every line in the faded red at full strength: shadcn fades the description to 90%
        // (text-destructive/90), which no contrast check covers.
        danger:
          "border-destructive text-destructive *:data-[slot=alert-description]:text-destructive",
      },
    },
  },
);

const ROLE: Record<AlertKind, "status" | "alert"> = {
  info: "status",
  danger: "alert",
};

export function Alert({
  kind = "info",
  className,
  ...props
}: Omit<Props<typeof ShadcnAlert>, "variant" | "role"> & { kind?: AlertKind }) {
  return (
    <ShadcnAlert
      // shadcn's own "destructive" would fade the description; ours sets every colour itself.
      variant="default"
      role={ROLE[kind]}
      className={cn(look({ kind }), className)}
      {...props}
    />
  );
}

export function AlertTitle({
  className,
  ...props
}: Props<typeof ShadcnAlertTitle>) {
  return (
    <ShadcnAlertTitle className={cn("font-semibold", className)} {...props} />
  );
}

export function AlertDescription({
  className,
  ...props
}: Props<typeof ShadcnAlertDescription>) {
  return (
    <ShadcnAlertDescription
      // The normal text colour, not shadcn's quiet one: a message is there to be read.
      className={cn("text-base text-foreground", className)}
      {...props}
    />
  );
}
