// utils.ts — small helpers shared by the shadcn components in src/components/ui/.
//
// cn() joins class names and settles Tailwind conflicts: cn("p-2", "p-4") gives "p-4",
// so a screen can override a component's default classes without both applying. It comes
// from shadcn's own `cn` package, which does the job of clsx + tailwind-merge in one.
//
// components.json, beside package.json, tells the shadcn CLI (`pnpm shadcn add button`)
// where to put components and which helper to import; it is JSON, so it holds no comments.
export { cn } from "cn";
