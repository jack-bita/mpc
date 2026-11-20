// page.tsx — /attendance-month/worker/?staff=…&month=…: a worker's month as a calendar, an office screen (ATT-12,
// 03 §5.10), opened from the worker's name on Mahudhurio ya mwezi. The screen itself is
// features/attendance/worker-month-screen.tsx; this page only reads the worker and the month from the address.
//
// A query string, not a [id] page, as the worker's own page (workers/view/page.tsx): the app is plain files built
// ahead of time (ADR-0016). useSearchParams reads it, inside Suspense, as the build makes this page with no address.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { MONTH_PARAM } from "@/features/attendance/attendance-month";
import { STAFF_PARAM } from "@/features/attendance/worker-month";
import { WorkerMonthScreen } from "@/features/attendance/worker-month-screen";

export default function WorkerMonthPage() {
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
    <WorkerMonthScreen
      staff={address?.get(STAFF_PARAM) || null}
      asked={address?.get(MONTH_PARAM) || null}
    />
  );
}
