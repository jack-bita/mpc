// postcss.config.mjs — the CSS build steps Next.js runs on every stylesheet.
//
// One step only: Tailwind v4. It reads the classes used in our files and writes just the
// CSS those classes need, so the app ships no unused styles (which matters on 3G, 03 §14).
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
