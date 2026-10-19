// eslint.config.mjs — the lint rules for the frontend (`pnpm lint`).
//
// Lint finds likely bugs that type checks miss: a hook called inside an `if`, a missing
// `key` in a list, an <img> without alt text. We use Next.js's own rule sets and add none
// of our own yet; later cards add rules for our own boundaries.
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
  // Last, so it wins: switch off every rule about layout. Prettier owns layout, and two
  // tools with opinions on spacing would only fight.
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
