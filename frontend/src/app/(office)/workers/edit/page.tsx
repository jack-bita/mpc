// page.tsx — /workers/edit/?id=…: Badilisha taarifa za Juma, a worker's details fixed on a page of their own, an office
// screen (UI-11). The screen itself is features/workers/edit-worker-screen.tsx; this page only reads the worker's id
// from the address, inside Suspense, as /workers/view/ does (its page.tsx says why).
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { EditWorkerScreen } from "@/features/workers/edit-worker-screen";

export default function EditWorkerPage() {
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
  return <EditWorkerScreen id={id} />;
}
