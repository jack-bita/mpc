// page.tsx — /my-settings/: Mipangilio yangu, a person's own language and font, an office screen (UI-9,
// 03 §7.1). The screen itself is features/people/my-settings.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { MySettings } from "@/features/people/my-settings";

export default function MySettingsPage() {
  return <MySettings />;
}
