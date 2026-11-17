// provider.tsx — hands every screen the open word book (UI-1, ADR-0040). layout.tsx wraps the whole app
// in it, so any screen can ask for its words with use-intl's useTranslations().
//
// "use client": it reads the choice kept on this browser, and the build has no browser. The page is
// still built once, in Swahili (language.ts says how).
"use client";

import { type ReactNode, useEffect } from "react";
import { IntlProvider } from "use-intl";

import { MESSAGES, useLanguage } from "./language";

// Dates and times are shown in the shop's time, whatever the device's own clock is set to (03 §6.6).
const SHOP_TIME_ZONE = "Africa/Dar_es_Salaam";

/**
 * What happens when a word is missing or can't be filled in. While building and testing it stops the
 * screen with the reason, so a mistake can't pass unseen. In the shop it only logs it: the screen shows
 * the key (like "home.title") and the sale goes on. pnpm typecheck and messages.test.ts make that rare.
 */
function onError(error: Error): void {
  if (process.env.NODE_ENV !== "production") throw error;
  console.error(error);
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const language = useLanguage();

  // <html lang> follows the book, so a screen reader speaks English words as English, not as Swahili.
  // layout.tsx builds the page with lang="sw"; this keeps it true after a switch.
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  return (
    <IntlProvider
      locale={language}
      messages={MESSAGES[language]}
      timeZone={SHOP_TIME_ZONE}
      onError={onError}
    >
      {children}
    </IntlProvider>
  );
}
