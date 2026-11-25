// page.tsx — /advances/view/?id=…: one advance's own page, an office screen (WAGE-8, 03 §5.10), opened from its line on
// Advansi. The screen itself is features/advances/advance-page.tsx; this page only reads the id from the address.
//
// A query string, not a [id] page: the app is plain files built ahead of time (ADR-0016). useSearchParams reads it,
// inside Suspense, as the build makes this page with no address.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AdvanceScreen } from "@/features/advances/advance-page";
import { ADVANCE_PARAM } from "@/features/advances/advances";

export default function AdvanceViewPage() {
  return (
    <Suspense>
      <AdvanceFromTheAddress />
    </Suspense>
  );
}

function AdvanceFromTheAddress() {
  // Null outside a running Next.js app, though its type says otherwise: a test renders the page with no router, as
  // the every-page-in-English test does (language.test.tsx).
  const address: URLSearchParams | null = useSearchParams();
  // An address with no id, or an empty one, names none: the screen says so, and asks nothing.
  return <AdvanceScreen id={address?.get(ADVANCE_PARAM) || null} />;
}
