// page.tsx — /advances/: Advansi, the money given to workers before payday, a month at a time, an office screen (WAGE-8,
// 03 §5.10). The screen itself is features/advances/advances-screen.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { AdvancesScreen } from "@/features/advances/advances-screen";

export default function AdvancesPage() {
  return <AdvancesScreen />;
}
