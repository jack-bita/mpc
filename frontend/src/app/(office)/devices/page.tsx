// page.tsx — /devices/: Vifaa, the shop's devices, an office screen (UI-3, 03 §7.1). The screen itself
// is features/devices/devices-screen.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { DevicesScreen } from "@/features/devices/devices-screen";

export default function DevicesPage() {
  return <DevicesScreen />;
}
