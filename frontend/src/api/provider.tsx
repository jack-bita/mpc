// provider.tsx — hands every screen the store of server answers (UI-2, 03 §7.1). layout.tsx wraps the
// whole app in it, so an office screen can ask for an answer with TanStack Query's useQuery().
//
// It wraps the counter screens too, as the device's registration and PIN login screens need the server
// as well (UI-3, UI-4). Counter screens themselves never ask it: they read Dexie (rule 5, ADR-0019), and a
// lint rule refuses TanStack Query in app/(counter)/ (eslint.config.mjs).
//
// "use client": the store lives in the browser, and the build has none.
"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";

import { makeQueryClient } from "./query-client";

export function QueryProvider({ children }: { children: ReactNode }) {
  // Made once, on the first render, and kept for the page's life: a new store on each render would
  // forget every answer.
  const [client] = useState(makeQueryClient);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
