// page.tsx — /device-health/: Hali ya vifaa, how each of the shop's devices syncs, an office screen
// (SYNC-14, 03 §5.17). The screen itself is features/devices/device-health.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { DeviceHealthScreen } from "@/features/devices/device-health";

export default function DeviceHealthPage() {
  return <DeviceHealthScreen />;
}
