// page.tsx — the home page at "/": for now, only the Karibu welcome.
//
// "use client": every page in this app is a client component (ADR-0016), because pages
// will read the device's own data (Dexie) and must work with no server. Next.js still
// renders the page once at build time, so out/index.html already holds the first HTML.
"use client";

// The text lives in the message files, not here (ADR-0032). UI-1 swaps this direct import
// for next-intl's useTranslations().
import sw from "../../messages/sw.json";

export default function HomePage() {
  return (
    <main>
      <h1>{sw.home.title}</h1>
    </main>
  );
}
