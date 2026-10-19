// vitest.config.mts — how `pnpm test` runs the frontend's unit and component tests.
//
// Tests run in Node, inside jsdom: a fake browser (document, window, events) that is fast
// and needs no real browser. Real browsers and offline mode come with Playwright (03 §11).
// Tests sit next to the code they test, as *.test.ts(x).
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // Compiles our JSX the same way Next.js does (React's automatic runtime).
  plugins: [react()],
  resolve: {
    // The same "@/…" → src/… shortcut as tsconfig.json, so imports work alike in both.
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
