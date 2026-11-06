// language-button.tsx — the button on the top bar that switches the app between Swahili and English
// (UI-1, ADR-0040).
//
// It names the other language, in that language: "English" while Swahili is open, "Kiswahili" while
// English is. Someone who can't read the open language still finds their own, as bank apps and
// government sites do. Each book holds that name (language.switch). This browser keeps the choice
// until UI-9 keeps it on the person.
"use client";

import { useTranslations } from "use-intl";

import { Button } from "@/components/design/button";
import { type Language, setLanguage, useLanguage } from "@/i18n/language";

// The language the button switches to, from the one that is open.
const OTHER: Record<Language, Language> = { sw: "en", en: "sw" };

export function LanguageButton() {
  const t = useTranslations("language");
  const other = OTHER[useLanguage()];

  return (
    // The bar kind: the only kind that can sit on the green (button.tsx). Normal height: it is not the
    // screen's main action, and the bar stays slim.
    <Button kind="bar" size="normal" onClick={() => setLanguage(other)}>
      {/* lang: the word is in the other language, so a screen reader says "English" as English. */}
      <span lang={other}>{t("switch")}</span>
    </Button>
  );
}
