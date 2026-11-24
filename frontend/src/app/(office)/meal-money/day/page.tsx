// page.tsx — /meal-money/day/?date=…: one day's meal money, an office screen (WAGE-7, 03 §5.10). The screen itself is
// features/meals/meal-money-day.tsx; this page only reads the day from the address.
//
// A query string, not a [date] page: the app is plain files built ahead of time (ADR-0016). useSearchParams reads it,
// inside Suspense: the build makes this page with no address, and Next.js needs the boundary to leave the part that reads
// one to the browser.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { DAY_PARAM } from "@/features/meals/meal-money";
import { MealMoneyDayScreen } from "@/features/meals/meal-money-day";

export default function MealMoneyDayPage() {
  return (
    <Suspense>
      <DayFromTheAddress />
    </Suspense>
  );
}

function DayFromTheAddress() {
  // Null outside a running Next.js app, though its type says otherwise: a test renders the page with no router, as
  // the every-page-in-English test does (language.test.tsx).
  const address: URLSearchParams | null = useSearchParams();
  return <MealMoneyDayScreen date={address?.get(DAY_PARAM) || null} />;
}
