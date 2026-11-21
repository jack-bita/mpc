// page.tsx — /workers/new/: Mfanyakazi mpya, Ongeza's form on a page of its own, an office screen (UI-11). The screen
// itself is features/workers/new-worker-screen.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { NewWorkerScreen } from "@/features/workers/new-worker-screen";

export default function NewWorkerPage() {
  return <NewWorkerScreen />;
}
