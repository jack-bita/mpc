// text-link.tsx — a link in words, not a button: a worker's name on Wafanyakazi, which opens the worker's own page
// (PPL-6, ADR-0039).
//
// ButtonLink is the big button's look on a link, for a step to another page; this is the plain one, for a name in a
// list that opens what it names. Next.js's Link, so the move stays in the app and the in-app note (in-app-moves.tsx)
// lets the back arrow go back; a real <a>, so a screen reader says "link" and Enter follows it.
//
// The look: the text's own colour, bold and underlined, so it reads as a link without a colour of its own, and passes
// on a white screen and a pale panel as the text around it does (tokens.test.ts checks --foreground on both). The
// focus ring at full strength (ring-ring, never ring-ring/50, UI-1), drawn around the words.
import Link from "next/link";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export function TextLink({ className, ...props }: ComponentProps<typeof Link>) {
  return (
    <Link
      className={cn(
        "rounded-sm font-semibold text-foreground underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring",
        className,
      )}
      {...props}
    />
  );
}
