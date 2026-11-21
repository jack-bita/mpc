// page.tsx — /workers/new/: Mfanyakazi mpya, Ongeza's form on a page of its own, and, with `?again=…`, Mwajiri tena
// Baraka, the same form for a worker who left and comes back, an office screen (UI-11). The screen itself is
// features/workers/new-worker-screen.tsx; this page only reads the old job's id from the address, inside Suspense, as
// /workers/view/ does (its page.tsx says why).
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { NewWorkerScreen } from "@/features/workers/new-worker-screen";

export default function NewWorkerPage() {
  return (
    <Suspense>
      <OldJobFromTheAddress />
    </Suspense>
  );
}

function OldJobFromTheAddress() {
  // Null outside a running Next.js app, though its type says otherwise (/workers/view/'s page.tsx).
  const address: URLSearchParams | null = useSearchParams();
  // No old job, or an empty one: a new worker.
  const again = address?.get("again") || null;
  return <NewWorkerScreen again={again} />;
}
