// render.tsx — Testing Library's render, inside the app's word books and a store of server answers of
// its own (UI-1, UI-3). Tests only.
//
// Every screen asks use-intl for its words, and use-intl finds them through LanguageProvider, which
// layout.tsx puts around the whole app. A screen rendered alone in a test has no layout, so this render
// puts the same provider around it. A test that wants English calls setLanguage("en") before it renders.
//
// Screens that call the server ask TanStack Query, which layout.tsx's QueryProvider gives them; this
// gives each render a new store, so no test sees another's answers. A test that puts its own
// QueryProvider inside gets that one: the nearest provider wins.
import { QueryClientProvider } from "@tanstack/react-query";
import {
  render as renderAlone,
  type RenderOptions,
} from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

import { makeQueryClient } from "@/api/query-client";
import { LanguageProvider } from "@/i18n/provider";

export function render(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">,
) {
  const store = makeQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <LanguageProvider>
        <QueryClientProvider client={store}>{children}</QueryClientProvider>
      </LanguageProvider>
    );
  }
  // wrapper: Testing Library keeps it around the screen on rerender() too.
  return renderAlone(ui, { wrapper: Wrapper, ...options });
}
