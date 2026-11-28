// page.tsx — /pay/payslips/?month=…[&staff=…]: the payslips of an approved month, printed on A4, one page each, or one
// worker's alone (WAGE-5, 03 §5.15), opened from Mishahara or from a worker's pay page. The screen itself is
// features/pay/printed-payslips.tsx; this page only reads the month and the worker from the address.
//
// A query string, not a [month] page: the app is plain files built ahead of time (ADR-0016). useSearchParams reads it,
// inside Suspense, as the build makes this page with no address.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { MONTH_PARAM } from "@/features/attendance/attendance-month";
import { STAFF_PARAM } from "@/features/pay/pay";
import { PrintedPayslipsScreen } from "@/features/pay/printed-payslips";

export default function PrintedPayslipsPage() {
  return (
    <Suspense>
      <PayslipsFromTheAddress />
    </Suspense>
  );
}

function PayslipsFromTheAddress() {
  // Null outside a running Next.js app, though its type says otherwise: a test renders the page with no router, as
  // the every-page-in-English test does (language.test.tsx).
  const address: URLSearchParams | null = useSearchParams();
  // No worker, or an empty one, is everyone's.
  return (
    <PrintedPayslipsScreen
      asked={address?.get(MONTH_PARAM) || null}
      staff={address?.get(STAFF_PARAM) || null}
    />
  );
}
