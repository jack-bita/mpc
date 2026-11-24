// page.tsx — /flags/: Tofauti, what the system found and a person must look into, an office screen (CTRL-4, 03 §5.10).
// The screen itself is features/flags/flags-screen.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { FlagsScreen } from "@/features/flags/flags-screen";

export default function FlagsPage() {
  return <FlagsScreen />;
}
