// language.ts — finds Swahili left on a screen that should be in English (UI-1, ADR-0032). Tests only.
//
// "Switching to English changes every visible string" (the UI-1 card) is checked by showing a screen
// in English and looking for any sentence from the Swahili book on it. Only sentences that English says
// differently count: the shop's name (MPC) or "@" are the same in both books.
import en from "../../messages/en.json";
import sw from "../../messages/sw.json";

/** Every sentence in a book, by its key: "home.version" -> "Toleo {version}". */
export function sentences(book: unknown, prefix = ""): Map<string, string> {
  const found = new Map<string, string>();
  if (typeof book === "string") found.set(prefix, book);
  else if (book !== null && typeof book === "object")
    for (const [key, inner] of Object.entries(book))
      for (const entry of sentences(inner, prefix ? `${prefix}.${key}` : key))
        found.set(...entry);
  return found;
}

/**
 * A sentence as a pattern for a whole piece of text. A part to fill in matches anything:
 * "Toleo {version}" matches "Toleo dev" and "Toleo 3fd5a70".
 */
function asPattern(sentence: string): RegExp {
  const fixed = sentence
    .split(/\{\w+\}/)
    .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return new RegExp(`^${fixed.join(".+")}$`);
}

const english = sentences(en);

/** Whether a sentence has words of its own, outside its parts to fill in: "{unit} {count}" has none. */
const hasWords = (sentence: string) =>
  /\p{L}/u.test(sentence.replace(/\{\w+\}/g, ""));

// The Swahili sentences that English says differently, as patterns. Only those with words of their
// own: "{unit} {count}" differs from English only in its order, and as a pattern it would match any
// two words on a screen.
const SWAHILI_ONLY = [...sentences(sw)]
  .filter(([key, sentence]) => english.get(key) !== sentence)
  .filter(([, sentence]) => hasWords(sentence))
  .map(([, sentence]) => asPattern(sentence));

// Attributes a person sees (placeholder, title, alt) or hears from a screen reader (aria-label).
const SPOKEN_ATTRIBUTES = ["aria-label", "placeholder", "title", "alt"];

/** Every piece of text under `root` that a person can see or hear. */
function textsIn(root: Element): string[] {
  const texts: string[] = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode())
    texts.push(node.textContent ?? "");
  for (const element of root.querySelectorAll("*"))
    for (const name of SPOKEN_ATTRIBUTES) {
      const value = element.getAttribute(name);
      if (value !== null) texts.push(value);
    }
  return texts.map((text) => text.trim()).filter(Boolean);
}

/** The pieces of text under `root` that are a Swahili sentence English says differently. */
export function swahiliIn(root: Element): string[] {
  return textsIn(root).filter((text) =>
    SWAHILI_ONLY.some((pattern) => pattern.test(text)),
  );
}
