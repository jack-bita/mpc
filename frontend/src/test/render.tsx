// render.tsx — Testing Library's render, inside the app's word books (UI-1). Tests only.
//
// Every screen asks use-intl for its words, and use-intl finds them through LanguageProvider, which
// layout.tsx puts around the whole app. A screen rendered alone in a test has no layout, so this render
// puts the same provider around it. A test that wants English calls setLanguage("en") before it renders.
import {
  render as renderAlone,
  type RenderOptions,
} from "@testing-library/react";
import type { ReactElement } from "react";

import { LanguageProvider } from "@/i18n/provider";

export function render(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">,
) {
  // wrapper: Testing Library keeps it around the screen on rerender() too.
  return renderAlone(ui, { wrapper: LanguageProvider, ...options });
}
