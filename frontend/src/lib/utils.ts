// utils.ts — small helpers shared by our pieces in src/components/design/.
//
// cn() joins class names and settles Tailwind conflicts: cn("p-2", "p-4") gives "p-4",
// so a screen can override a component's default classes without both applying. It comes
// from shadcn's own `cn` package, which does the job of clsx + tailwind-merge in one.
// shadcn's parts in src/components/ui/ import the package directly; ours import it from here.
//
// cn() only knows Tailwind's own names, not ours: cn("h-8", "h-control-big") keeps both, and the
// CSS order decides which height wins. So our pieces write a height as h-(--control-big), a
// spelling cn knows is a height (UI-8).
//
// components.json, beside package.json, tells the shadcn CLI (`pnpm shadcn add button`)
// where to put components; it is JSON, so it holds no comments.
export { cn } from "cn";
