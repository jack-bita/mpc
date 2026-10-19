// layout.tsx — the root layout: the <html> and <body> that every page shares.
//
// This file stays a server component, but in a static export a server component runs
// once, at build time, and becomes plain HTML in out/ — no server runs it later
// (ADR-0016). That is also why it may export `metadata`, which only server components can.
// UI-1 adds the app's providers here: translations, data, session, device (03 §7.2).
import type { Metadata } from "next";
import type { ReactNode } from "react";

// Screen text comes from the message files, never from code (ADR-0032). UI-1 replaces this
// direct import with next-intl, which also handles the English switch.
import sw from "../../messages/sw.json";

export const metadata: Metadata = {
  title: sw.app.title,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // lang="sw": the app is Swahili first, so screen readers and spell checkers use Swahili.
    <html lang="sw">
      <body>{children}</body>
    </html>
  );
}
