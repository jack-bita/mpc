// blanks.ts — the names a sentence fills in, read as use-intl reads its messages (UI-2, ADR-0040).
//
// "Toleo {version}" fills in `version`. A sentence that counts, "{count, plural, one {mfuko} other
// {mifuko}}", fills in only `count`: its branches, {mfuko} and {mifuko}, hold words, not values. A plain
// pattern can't tell them apart, so this counts braces. An argument opens at an even depth, and a
// branch at an odd one, inside its argument; a branch may hold arguments of its own, deeper again.
//
// Two readers: codes.ts, which checks the server sent every value a code's sentence needs, and
// messages.test.ts, which checks both books fill in the same names. One copy, so they can't disagree.
// Not read: ICU's quoting with an apostrophe before a brace ('{'), which no sentence of ours uses.

/** Each name a sentence fills in, once, in the order it first appears. */
export function blanks(sentence: string): string[] {
  const names = new Set<string>();
  let depth = 0;
  for (let at = 0; at < sentence.length; at += 1) {
    const char = sentence[at];
    if (char === "{") {
      if (depth % 2 === 0) {
        // An argument opens: its name comes first, spaces allowed around it, as use-intl allows them.
        const name = /^\{\s*(\w+)/.exec(sentence.slice(at))?.[1];
        if (name) names.add(name);
      }
      depth += 1;
    } else if (char === "}") {
      depth = Math.max(0, depth - 1);
    }
  }
  return [...names];
}
