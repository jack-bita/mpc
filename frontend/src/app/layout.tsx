// layout.tsx — the root layout: the <html> and <body> that every page shares.
//
// This file stays a server component, but in a static export a server component runs
// once, at build time, and becomes plain HTML in out/ — no server runs it later
// (ADR-0016). That is also why it may export `metadata`, which only server components can.
// The app's providers wrap every page here: today the word books; later data, session and
// device (03 §7.2).
import type { Metadata } from "next";
import type { ReactNode } from "react";

// The tab's title is read once, at build time, where no language has been chosen yet. It is the
// shop's short name, the same in both books.
import sw from "../../messages/sw.json";

// Starts the service worker, which keeps the app's files on the device so every page opens offline,
// and shows the Toleo jipya bar when a new version is ready (SPIKE-1).
import { UpdatePrompt } from "@/components/update-prompt";
// The two fonts inside the app (ADR-0039).
import { atkinson, sourceSans } from "@/fonts/fonts";
// Hands every screen its words from the open book: Swahili, or English after the switch (ADR-0040).
import { LanguageProvider } from "@/i18n/provider";

// The one global stylesheet: Tailwind and the design tokens, loaded once for every page.
import "./globals.css";

export const metadata: Metadata = {
  title: sw.app.title,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // lang="sw": the app is Swahili first, so screen readers and spell checkers use Swahili.
    // After a switch to English, LanguageProvider changes it in the browser.
    // The two classes hand both fonts to the page under their names; globals.css picks which one
    // shows. Both are here because a person's choice changes the font with no new page (UI-9).
    <html lang="sw" className={`${sourceSans.variable} ${atkinson.variable}`}>
      <body>
        <LanguageProvider>
          {children}
          <UpdatePrompt />
        </LanguageProvider>
      </body>
    </html>
  );
}
