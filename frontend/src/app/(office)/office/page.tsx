// page.tsx — /office/: the office's home page, where a manager lands after logging in (UI-5). The page
// itself is features/office/office-home.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { OfficeHome } from "@/features/office/office-home";

export default function OfficeHomePage() {
  return <OfficeHome />;
}
