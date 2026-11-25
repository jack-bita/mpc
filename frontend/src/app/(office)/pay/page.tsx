// page.tsx — /pay/: Mishahara, the month's pay of everyone the shop pays by the day, an office screen (WAGE-2,
// 03 §5.10). The screen itself is features/pay/pay-screen.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { PayScreen } from "@/features/pay/pay-screen";

export default function PayPage() {
  return <PayScreen />;
}
