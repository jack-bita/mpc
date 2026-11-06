// field.tsx — a box with its label, a hint and its error, tied together (UI-8, ADR-0039).
//
// The tie is what a screen reader needs. Without it, it reads "edit text" with no name, and a refused
// value with no reason. With it, moving to the box reads its label, then its hint and error:
//   the label names the box      <label htmlFor=id>      → <input id=id>
//   the hint and error explain   <p id=id-hint>, <p id=id-error> → <input aria-describedby="…">
//   the box says it was refused  <input aria-invalid="true">, which also paints the red edge
// useId gives every field its own id, so two fields on one screen never share one.
//
// The order on screen is the one GOV.UK's design system tested with real people: label, hint, error,
// then the box. The error sits above the box, so a phone's keyboard, which opens under the box,
// never hides it.
//
// The error and the hint arrive as text already in the person's language: a screen turns the API's
// error code into words (ADR-0032), and Field only shows them.
import { useId } from "react";

import { cn } from "@/lib/utils";

import { Input, type InputProps } from "./input";
import { Label } from "./label";

export type FieldProps = Omit<
  InputProps,
  "id" | "aria-invalid" | "aria-describedby"
> & {
  label: string;
  hint?: string;
  error?: string;
};

export function Field({ label, hint, error, className, ...input }: FieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  // Only the ids that are on the page: a name in aria-describedby with no element is read as nothing,
  // and checkers flag it.
  const describedBy =
    [hint ? hintId : null, error ? errorId : null]
      .filter((part) => part !== null)
      .join(" ") || undefined;

  return (
    <div className={cn("grid gap-2", className)}>
      <Label htmlFor={id}>{label}</Label>
      {hint ? (
        <p id={hintId} className="text-sm text-muted-foreground">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-base font-medium text-destructive">
          {error}
        </p>
      ) : null}
      <Input
        id={id}
        // undefined, not false, when all is well: aria-invalid="false" is noise for a screen reader.
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...input}
      />
    </div>
  );
}
