// page.tsx — /attendance-month/?month=…: Mahudhurio ya mwezi, the month's attendance, an office screen (ATT-5,
// 03 §5.10). The screen itself is features/attendance/month-screen.tsx; this page only reads the month from the address.
//
// A query string, as the worker's page reads its id (workers/view/page.tsx): useSearchParams reads it, inside
// Suspense, as the build makes this page with no address, and Next.js needs the boundary to leave the part that reads
// one to the browser.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { MONTH_PARAM } from "@/features/attendance/attendance-month";
import { MonthScreen } from "@/features/attendance/month-screen";

export default function AttendanceMonthPage() {
  return (
    <Suspense>
      <MonthFromTheAddress />
    </Suspense>
  );
}

function MonthFromTheAddress() {
  // Null outside a running Next.js app, though its type says otherwise: a test renders the page with no router, as
  // the every-page-in-English test does (language.test.tsx).
  const address: URLSearchParams | null = useSearchParams();
  // No month, or an empty one: the screen opens this month.
  return <MonthScreen asked={address?.get(MONTH_PARAM) || null} />;
}
