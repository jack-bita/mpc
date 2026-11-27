// page.tsx — /my-days-and-pay/: Siku na malipo yangu, a worker's own days and pay, an office screen opened from the PIN's
// welcome and the office's home (WAGE-4, 03 §5.10). The screen itself is features/mine/my-days-and-pay-screen.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { MyDaysAndPayScreen } from "@/features/mine/my-days-and-pay-screen";

export default function MyDaysAndPayPage() {
  return <MyDaysAndPayScreen />;
}
