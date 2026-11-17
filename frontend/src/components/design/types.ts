// types.ts — the one helper type our pieces share (UI-8).
import type { ComponentProps, ElementType } from "react";

/**
 * A shadcn part's props, with className only as a string. Base UI also takes a function there (the
 * part's state in, classes out), but our pieces join their classes with cn(), which needs a string.
 */
export type PieceProps<T extends ElementType> = Omit<
  ComponentProps<T>,
  "className"
> & { className?: string };
