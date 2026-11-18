// page.tsx — /workers/view/?id=…: one worker's own page, an office screen (PPL-6, 03 §5.10). The screen itself is
// features/workers/worker-page.tsx; this page only reads the worker's id from the address.
//
// A query string, not a [id] page: the app is plain files built ahead of time (ADR-0016), and a worker added today has
// no file of their own. useSearchParams reads it, inside Suspense: the build makes this page with no address, and
// Next.js needs the boundary to leave the part that reads one to the browser.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { WorkerScreen } from "@/features/workers/worker-page";

export default function WorkerPage() {
  return (
    <Suspense>
      <WorkerFromTheAddress />
    </Suspense>
  );
}

function WorkerFromTheAddress() {
  // Null outside a running Next.js app, though its type says otherwise: a test renders the page with no router, as
  // the every-page-in-English test does (language.test.tsx).
  const address: URLSearchParams | null = useSearchParams();
  // An address with no id, or an empty one, names no worker: the screen says so, and asks nothing.
  const id = address?.get("id") || null;
  return <WorkerScreen id={id} />;
}
