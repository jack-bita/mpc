// page.tsx — /settings/: Mipangilio ya duka, the shop's rules, an office screen (SHOP-5, 03 §5.8). The screen
// itself is features/settings/settings-screen.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { SettingsScreen } from "@/features/settings/settings-screen";

export default function SettingsPage() {
  return <SettingsScreen />;
}
