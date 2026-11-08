// page.tsx — /login/: Ingia, the password login of the owner and managers (UI-5). The form itself is
// features/login/password-login.tsx.
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { PasswordLogin } from "@/features/login/password-login";

export default function LoginPage() {
  return <PasswordLogin />;
}
