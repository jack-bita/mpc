// page.tsx — /flags/view/?id=…: one flag's own page, an office screen (CTRL-4, 03 §5.10). The screen itself is
// features/flags/flag-page.tsx; this page only reads the flag's id from the address.
//
// A query string, not a [id] page: the app is plain files built ahead of time (ADR-0016), and a flag raised today has no
// file of its own. useSearchParams reads it, inside Suspense: the build makes this page with no address, and Next.js
// needs the boundary to leave the part that reads one to the browser.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { FlagScreen } from "@/features/flags/flag-page";

export default function FlagPage() {
  return (
    <Suspense>
      <FlagFromTheAddress />
    </Suspense>
  );
}

function FlagFromTheAddress() {
  // Null outside a running Next.js app, though its type says otherwise: a test renders the page with no router, as
  // the every-page-in-English test does (language.test.tsx).
  const address: URLSearchParams | null = useSearchParams();
  // An address with no id, or an empty one, names no flag: the screen says so, and asks nothing.
  return <FlagScreen id={address?.get("id") || null} />;
}
