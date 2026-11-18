// page.tsx — /login/: Ingia, the password login of the owner and managers (UI-5). The form itself is
// features/login/password-login.tsx; this page only reads `?as=` from the address, the staff id the demo
// manager's tile sends (OPS-13), for the form to start filled with the login this laptop kept for him.
//
// useSearchParams reads it inside Suspense: the build makes this page with no address, and Next.js needs
// the boundary to leave the part that reads one to the browser (as /workers/view/ does).
//
// "use client": every page in this app is a client component (ADR-0016).
"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { PasswordLogin } from "@/features/login/password-login";

export default function LoginPage() {
  return (
    <Suspense>
      <LoginFromTheAddress />
    </Suspense>
  );
}

function LoginFromTheAddress() {
  // Null outside a running Next.js app, though its type says otherwise: a test renders the page with no
  // router, as the every-page-in-English test does (language.test.tsx).
  const address: URLSearchParams | null = useSearchParams();
  // No id, or an empty one: the form as it always is.
  const forStaff = address?.get("as") || null;
  return <PasswordLogin forStaff={forStaff} />;
}
