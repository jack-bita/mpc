// page.tsx — /forgot-password/: Umesahau nenosiri?, the two ways back in after a forgotten password
// (UI-5). The page itself is features/login/forgot-password.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { ForgotPassword } from "@/features/login/forgot-password";

export default function ForgotPasswordPage() {
  return <ForgotPassword />;
}
