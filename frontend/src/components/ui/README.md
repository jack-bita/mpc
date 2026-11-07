# components/ui/ — shadcn's parts, as shadcn wrote them

Every file here comes from `pnpm shadcn add <name>`, in the `base-nova` style of `components.json`.
They give the behaviour: Base UI (`@base-ui/react`) handles focus, the keyboard and screen readers.
They are not the shop's look, and screens never import them (ADR-0039).

- **Never edit shadcn's files here.** Only this README changes, when a part is added. Our look lives
  in `components/design/`, where one piece of ours wraps each part and sets its colours, sizes and
  focus ring. To change a part, change our piece.
- **This README is the folder's header.** shadcn's files carry no header comment of their own, and
  adding one would be an edit.
- **Prettier skips this folder** (`.prettierignore`), so the files stay byte for byte as shadcn wrote
  them, and `pnpm shadcn add <name> --diff` shows only shadcn's own changes. ESLint still checks them.
- **After any `shadcn add`**, read every new file, and the diff of `globals.css` and `package.json`.
  If it writes grey `oklch()` colours or chart and sidebar tokens back, `tokens.test.ts` fails:
  remove them (UI-7).
- shadcn's files import `cn` from the `cn` package itself, not from `src/lib/utils.ts`.

Added in UI-8: `button`, `input`, `label`, `card`, `alert`. In UI-3: `radio-group`, worn by `Choice`.
