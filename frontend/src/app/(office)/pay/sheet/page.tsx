// page.tsx — /pay/sheet/?month=…: the month's sheet, every payment of an approved month on one A4 page, with each
// signature and a space to sign by pen, for NSSF and the owner's file (WAGE-5, 03 §5.15), opened from Mishahara. The
// screen itself is features/pay/month-sheet.tsx; this page only reads the month from the address.
//
// A query string, not a [month] page: the app is plain files built ahead of time (ADR-0016). useSearchParams reads it,
// inside Suspense, as the build makes this page with no address.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { MONTH_PARAM } from "@/features/attendance/attendance-month";
import { MonthSheetScreen } from "@/features/pay/month-sheet";

export default function MonthSheetPage() {
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
  return <MonthSheetScreen asked={address?.get(MONTH_PARAM) || null} />;
}
