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

export default defineConfig([
  // React, hooks, accessibility and Next.js rules, with the page-speed ones as errors.
  ...nextVitals,
  // The same for TypeScript files, plus typescript-eslint's recommended rules.
  ...nextTs,
  {
    rules: {
      // Our fonts live in the repo, so builds and devices never depend on another company's server.
      // next/font/google is one easy line away, and it would look harmless in a review (ADR-0039).
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "next/font/google",
              message: "Fonts live inside the app, in src/fonts/ (ADR-0039).",
            },
          ],
        },
      ],
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
          ],
        },
      ],
    },
  },
  {
    // No word typed straight into a screen: every word a person reads comes from the books in messages/,
    // so the English switch changes all of them (ADR-0032). text-rule.test.ts checks it.
    //
    // It catches text between tags, <p>Karibu</p>, and text put there as code, {"Karibu"} or
    // {`Toleo ${version}`}. ignoreProps: it leaves attributes alone, as nearly all of them are class
    // names, never words. That leaves a gap: a word typed into aria-label or placeholder passes here,
    // and only the English check on each page (src/i18n/language.test.tsx) finds it.
    //
    // Not tests, which write the words they expect to see, nor shadcn's parts, which we never edit.
    files: ["src/**/*.{js,jsx,mjs,ts,tsx,mts,cts}"],
    ignores: ["src/**/*.test.*", "src/components/ui/**"],
    rules: {
      "react/jsx-no-literals": [
        "error",
        { noStrings: true, ignoreProps: true },
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
