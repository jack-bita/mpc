// page.tsx — /attendance/, the Mahudhurio screen, in the counter area (SYNC-11): clocking in and out at a
// shop laptop. The screen itself is attendance.tsx; the counter's frame around it names who is here and
// sends anyone else to the name tiles (counter-frame.tsx).
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { AttendanceScreen } from "./attendance";

export default function AttendancePage() {
  return <AttendanceScreen />;
}
