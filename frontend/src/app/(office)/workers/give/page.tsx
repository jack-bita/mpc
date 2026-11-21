// page.tsx — /workers/give/?id=…: Ongeza kazi kwa Juma, a role or an extra key given on a page of its own, an office
// screen (UI-11). The screen itself is features/workers/give-screen.tsx; this page only reads the worker's id from the
// address, inside Suspense, as /workers/view/ does (its page.tsx says why).
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { GiveScreen } from "@/features/workers/give-screen";

export default function GivePage() {
  return (
    <Suspense>
      <WorkerFromTheAddress />
    </Suspense>
  );
}

function WorkerFromTheAddress() {
  // Null outside a running Next.js app, though its type says otherwise (/workers/view/'s page.tsx).
  const address: URLSearchParams | null = useSearchParams();
  // An address with no id, or an empty one, names no worker: the screen says so, and asks nothing.
  const id = address?.get("id") || null;
  return <GiveScreen id={id} />;
}
