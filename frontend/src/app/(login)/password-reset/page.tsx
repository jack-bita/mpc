// page.tsx — /password-reset/: Weka nenosiri jipya, the page an email's reset link opens, with its key
// after the # (UI-5). The page itself is features/login/password-reset.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { PasswordReset } from "@/features/login/password-reset";

export default function PasswordResetPage() {
  return <PasswordReset />;
}
