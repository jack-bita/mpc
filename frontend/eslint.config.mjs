// eslint.config.mjs — the lint rules for the frontend (`pnpm lint`).
//
// Lint finds likely bugs that type checks miss: a hook called inside an `if`, a missing
// `key` in a list, an <img> without alt text. We use Next.js's own rule sets, plus rules for
// our own boundaries.
//
// `pnpm lint` runs ESLint with --max-warnings=0: Next's sets make some rules (an unused
// variable) only warnings, and ESLint still exits 0 on warnings, so CI would stay green
// while warnings piled up. With it, a warning fails the check like an error.
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier/flat";

// The attributes that hold words a person reads or hears, for the text rule below. A selector: ESLint
// finds the parts of the code it names, as CSS finds the parts of a page.
const WORD_ATTRIBUTE =
  "JSXAttribute[name.name=/^(aria-label|aria-description|placeholder|title|alt)$/]";

// The browser's own ways to call the server, refused on counter screens with the message below.
const SERVER_CALLS = ["fetch", "XMLHttpRequest", "WebSocket", "EventSource"];

// What a counter screen is told when it reaches for the server (rule 5, ADR-0019): it reads Dexie and
// saves to the outbox, so a sale goes through with the network down.
const COUNTER_OFF_THE_SERVER =
  "Counter screens never call the server: read Dexie with live queries, save with saveDocument() (rule 5, ADR-0019).";

// Our fonts live in the repo, so builds and devices never depend on another company's server.
// next/font/google is one easy line away, and it would look harmless in a review (ADR-0039). A
// constant, as the counter screens' rule below must list it again (it says why).
const NO_GOOGLE_FONTS = {
  name: "next/font/google",
  message: "Fonts live inside the app, in src/fonts/ (ADR-0039).",
};

export default defineConfig([
  // React, hooks, accessibility and Next.js rules, with the page-speed ones as errors.
  ...nextVitals,
  // The same for TypeScript files, plus typescript-eslint's recommended rules.
  ...nextTs,
  {
    rules: {
      "no-restricted-imports": ["error", { paths: [NO_GOOGLE_FONTS] }],
    },
  },
  {
    // Screens use our pieces in components/design/, never shadcn's raw parts in components/ui/, so no
    // screen can skip the shop's look (ADR-0039). Only our pieces wrap the parts, and the parts may use
    // each other, so both folders are left out here. import-rule.test.ts checks it.
    //
    // eslint-plugin-import comes with Next's rule sets, which also teach it the "@/" path. Its rule
    // follows the file an import really points to, so every spelling is caught: "@/components/ui/button"
    // and "../../components/ui/button" alike. A rule that only read the import's text would miss some.
    // Every kind of file a screen can be written in: tsconfig.json allows JavaScript, and Next.js routes
    // a page.jsx as readily as a page.tsx. The same list as Next's rule sets, which load the import plugin
    // only for these: .cjs isn't in it, and a CommonJS file can't be a Next.js page anyway.
    //
    // A second zone keeps the counter screens off the server (rule 5, ADR-0019): they read Dexie and save
    // to the outbox, so a sale goes through with the network down. A counter screen that called the API
    // client would work in testing, with the network up, and fail at the shop the day it drops. The same
    // rule, so the same care: every spelling of the import is caught (import-rule.test.ts).
    files: ["src/**/*.{js,jsx,mjs,ts,tsx,mts,cts}"],
    ignores: ["src/components/design/**", "src/components/ui/**"],
    rules: {
      "import/no-restricted-paths": [
        "error",
        {
          // Paths below are from this folder, wherever ESLint is started from.
          basePath: import.meta.dirname,
          zones: [
            {
              target: "./src",
              from: "./src/components/ui",
              message:
                "Use our piece in @/components/design/: it gives shadcn's part the shop's look (ADR-0039).",
            },
            {
              target: "./src/app/(counter)",
              from: "./src/api",
              message: COUNTER_OFF_THE_SERVER,
            },
          ],
        },
      ],
    },
  },
  {
    // The rest of the counter screens' lock, for what the import rule above can't see (UI-2, rule 5).
    // - TanStack Query, the office screens' store of server answers, and openapi-fetch, from which a
    //   screen could build a typed client of its own: packages, not files of ours, and pnpm keeps
    //   packages under paths of its own. This rule reads the import's text, and a package has one name.
    // - The browser's own ways to call the server: fetch, XMLHttpRequest, WebSocket and EventSource,
    //   also through window., globalThis. or self., and navigator.sendBeacon.
    // Honest limit: a dynamic import("@tanstack/react-query") passes, as no-restricted-imports reads
    // only import lines, and the rule that could catch it, no-restricted-syntax, is set again for every
    // file by the text rule below, which would replace it here. Review catches that.
    //
    // ESLint keeps only the last settings of a rule for a file, and no-restricted-imports is the font
    // ban's rule too: listed again here, or counter screens would lose it (import-rule.test.ts).
    files: ["src/app/(counter)/**/*.{js,jsx,mjs,ts,tsx,mts,cts}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            NO_GOOGLE_FONTS,
            { name: "openapi-fetch", message: COUNTER_OFF_THE_SERVER },
          ],
          patterns: [
            { group: ["@tanstack/*"], message: COUNTER_OFF_THE_SERVER },
          ],
        },
      ],
      "no-restricted-globals": [
        "error",
        ...SERVER_CALLS.map((name) => ({
          name,
          message: COUNTER_OFF_THE_SERVER,
        })),
      ],
      "no-restricted-properties": [
        "error",
        ...["window", "globalThis", "self"].flatMap((object) =>
          SERVER_CALLS.map((property) => ({
            object,
            property,
            message: COUNTER_OFF_THE_SERVER,
          })),
        ),
        {
          object: "navigator",
          property: "sendBeacon",
          message: COUNTER_OFF_THE_SERVER,
        },
      ],
    },
  },
  {
    // No word typed straight into a screen: every word a person reads comes from the books in messages/,
    // so the English switch changes all of them (ADR-0040). text-rule.test.ts checks both rules here.
    //
    // jsx-no-literals catches text between tags, <p>Karibu</p>, and text put there as code, {"Karibu"}
    // or {`Toleo ${version}`}. ignoreProps: it leaves attributes alone, as nearly all of them are class
    // names, never words.
    //
    // The attributes that do hold words are caught by name: what a person reads (placeholder, title,
    // alt) or hears from a screen reader (aria-label, aria-description). A word typed into one, as text,
    // code or a template, is refused. An empty one, alt="" on a picture that only decorates, is fine.
    //
    // Not tests, which write the words they expect to see, nor shadcn's parts, which we never edit.
    files: ["src/**/*.{js,jsx,mjs,ts,tsx,mts,cts}"],
    ignores: ["src/**/*.test.*", "src/components/ui/**"],
    rules: {
      "react/jsx-no-literals": [
        "error",
        { noStrings: true, ignoreProps: true },
      ],
      "no-restricted-syntax": [
        "error",
        ...[
          `${WORD_ATTRIBUTE} > Literal[value=/\\S/]`,
          `${WORD_ATTRIBUTE} > JSXExpressionContainer > Literal[value=/\\S/]`,
          `${WORD_ATTRIBUTE} > JSXExpressionContainer > TemplateLiteral`,
        ].map((selector) => ({
          selector,
          message:
            'Words come from the books in messages/: use t("…") (ADR-0040).',
        })),
      ],
    },
  },
  // Last of the rule sets, so it wins: switch off every rule about layout. Prettier owns layout,
  // and two tools with opinions on spacing would only fight.
  prettier,
  // Built or generated files: nobody writes them by hand, so nobody lints them. ESLint
  // doesn't read .gitignore, so this list repeats .prettierignore's on purpose.
  globalIgnores([
    ".next/**",
    "out/**",
    "coverage/**",
    "next-env.d.ts",
    "src/api/schema.d.ts",
  ]),
]);
