// page.tsx — /workers/: Wafanyakazi, the shop's workers, an office screen (PPL-6, 03 §5.10). The screen itself is
// features/workers/workers-screen.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { WorkersScreen } from "@/features/workers/workers-screen";

export default function WorkersPage() {
  return <WorkersScreen />;
}
