// page.tsx — /register-device/: Sajili kifaa hiki, where a new device asks to join the shop (UI-3,
// 03 §5.9). The screen itself is features/devices/register-this-device.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { RegisterThisDevice } from "@/features/devices/register-this-device";

export default function RegisterDevicePage() {
  return <RegisterThisDevice />;
}
