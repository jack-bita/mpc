// language.ts — the two word books, which one is open on this browser, and the switch between them
// (UI-1, ADR-0040).
//
// Every word a screen shows lives in messages/sw.json and messages/en.json, never in code. Two layers
// decide which book is open (UI-9):
//   the person logged in here     their own language, saved on them on the server, which follows them to
//                                 every device; the app's frames hand it in as they learn who is here
//                                 (features/people/follow-the-person.ts). Kept in memory only.
//   nobody                        this laptop's own: Swahili unless someone switched with the bar's
//                                 button, kept on this browser (localStorage), so it survives a reload and
//                                 works offline. The tiles and the login pages show it.
// The person's never becomes the laptop's: saved on the browser, Asha's English would greet whoever comes
// to the tiles after her.
//
// The words come through use-intl, next-intl's own core (03 §7.4). next-intl adds a server side and a
// language in the web address (/en/...), which a static app with no language in its address never uses.
import { useSyncExternalStore } from "react";

import en from "../../messages/en.json";
import sw from "../../messages/sw.json";

export const LANGUAGES = ["sw", "en"] as const;
export type Language = (typeof LANGUAGES)[number];

// Swahili first (spec principle 1): the shop works in Swahili, and the static HTML is built in it.
export const DEFAULT_LANGUAGE: Language = "sw";

// Each language's book. Typed as Swahili's shape, so a key that English lacks fails `pnpm typecheck`;
// messages.test.ts catches the other way round, a key only English has.
export const MESSAGES: Record<Language, typeof sw> = { sw, en };

// Teaches use-intl our two languages and the books' keys, so t("home.titel") or a language like "fr"
// fails `pnpm typecheck` instead of showing a key on a screen.
declare module "use-intl" {
  interface AppConfig {
    Locale: Language;
    Messages: typeof sw;
  }
}

export function isLanguage(value: unknown): value is Language {
  return LANGUAGES.some((language) => language === value);
}

// The browser's key for the choice. "mpc." keeps it apart from anything else on the same address.
export const STORAGE_KEY = "mpc.language";

/** The language saved on this browser: Swahili if nothing (or nothing we know) is saved. */
function savedLanguage(): Language {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return isLanguage(saved) ? saved : DEFAULT_LANGUAGE;
  } catch {
    // A browser set to block every site's storage refuses even to read it. The app still opens, in
    // Swahili. (Such a browser can't run the counter anyway: the device database needs storage too.)
    return DEFAULT_LANGUAGE;
  }
}

// Everything on screen that shows words, told when the language changes.
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // "storage" comes when another tab of the app saves a choice: this tab follows it.
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

/** Sets this laptop's own language, on every screen at once, and keeps it for the next visit: the bar's
 * button, while nobody is logged in. */
export function setLanguage(language: Language): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // Storage refused (see savedLanguage): the switch can't be kept, so nothing changes.
  }
  for (const listener of listeners) listener();
}

// The language of the person logged in here, while someone is; null while nobody is.
let personsLanguage: Language | null = null;

/** Opens the person's own language, on every screen at once, over the laptop's own; null goes back to the
 * laptop's. Never kept on the browser (see the top of this file). */
export function setPersonsLanguage(language: Language | null): void {
  if (personsLanguage === language) return;
  personsLanguage = language;
  for (const listener of listeners) listener();
}

/** The open book: the person's, or else the laptop's own. */
function openLanguage(): Language {
  return personsLanguage ?? savedLanguage();
}

/**
 * The open language, the person's or the laptop's. useSyncExternalStore is React's way to read something kept outside React. The
 * build has no browser, so the page is built in Swahili (the last argument). In the browser, React
 * first draws that same Swahili, to match the built page, then draws the saved language at once.
 */
export function useLanguage(): Language {
  return useSyncExternalStore(subscribe, openLanguage, () => DEFAULT_LANGUAGE);
}
