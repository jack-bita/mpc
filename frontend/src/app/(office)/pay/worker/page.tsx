// page.tsx — /pay/worker/?staff=…&month=…: one worker's pay of a month, line by line, an office screen (WAGE-2,
// 03 §5.10), opened from their name on Mishahara. The screen itself is features/pay/worker-pay-screen.tsx; this page only
// reads the worker and the month from the address.
//
// A query string, not a [id] page: the app is plain files built ahead of time (ADR-0016). useSearchParams reads it,
// inside Suspense, as the build makes this page with no address.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { MONTH_PARAM } from "@/features/attendance/attendance-month";
import { STAFF_PARAM } from "@/features/pay/pay";
import { WorkerPayScreen } from "@/features/pay/worker-pay-screen";

export default function WorkerPayPage() {
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
  // No worker, or an empty one, names nobody; no month, the screen opens this month.
  return (
    <WorkerPayScreen
      staff={address?.get(STAFF_PARAM) || null}
      asked={address?.get(MONTH_PARAM) || null}
    />
  );
}
