// choice.tsx — pick one of a few, with a big row for each: a new device's home side, a person's own
// language and font (UI-9), later a way to pay (UI-3, ADR-0039).
//
// shadcn's radio group (components/ui/radio-group.tsx) gives the behaviour, through Base UI: one choice
// at a time, the arrow keys move between them, and a screen reader says "radio button, 1 of 2,
// selected". This piece sets the look, and ties the group to its name, hint and error, as Field ties a
// box (field.tsx):
//   the name names the group     <p id=id-label>               → role="radiogroup" aria-labelledby
//   the hint and error explain   <p id=id-hint>, <p id=id-error> → aria-describedby
// A <p>, not a <label>: a label names one box, and a group is named by aria-labelledby instead.
//
// Each choice is a whole row, as tall as a big button (52 px), wrapped in its <label>: a tap anywhere
// on the row picks it, where shadcn's dot alone is 16 px, too small for a finger. The row's own words
// name the dot for a screen reader. The order on screen is Field's: name, hint, error, then the rows.
//
// A row may be written in a language or a font of its own (UI-9): "English" among Swahili words is said
// as English, and a font's row shows that font, so a person sees what they pick before they pick it.
import { useId } from "react";

import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { cn } from "@/lib/utils";

/** One choice: what the screen gets back when it is picked, and the words on its row. */
export interface ChoiceOption {
  value: string;
  label: string;
  /** The words' language, when it isn't the page's: "en" for "English" on a Swahili page. */
  lang?: string;
  /** The font the words are shown in, by its role (ADR-0039), when it isn't the page's. */
  font?: "default" | "second";
}

/** The row around a dot and its words. Its edge is the box's dark edge (--input, 3:1), and green once
 * picked (--primary, 5.02:1 on white), so the picked row shows by more than the dot. */
export const ROW_LOOK = [
  "flex min-h-(--control-big) cursor-pointer items-center gap-3 rounded-lg border border-input bg-background px-4",
  "text-lg has-data-checked:border-primary",
  // Switched off, like the button: faded to half, which WCAG allows for what can't be used.
  "has-data-disabled:cursor-not-allowed has-data-disabled:opacity-50",
].join(" ");

/** The dot: 24 px, not shadcn's 16, so it is seen at arm's length. Picked, it fills with green, with
 * shadcn's white centre of 8 px, which stays in the middle of the bigger dot (it is placed from the
 * dot's own centre). */
export const DOT_LOOK = [
  "size-6",
  // Full strength: shadcn fades the ring to half (ring-ring/50), which reads at only 2.57:1 on white,
  // under the 3:1 someone on a keyboard needs to see where they are (UI-7).
  "focus-visible:ring-ring",
].join(" ");

export function Choice({
  label,
  hint,
  error,
  options,
  value,
  onValueChange,
  disabled,
  className,
}: {
  label: string;
  hint?: string;
  error?: string;
  options: ChoiceOption[];
  /** The picked value, or null for none yet. */
  value: string | null;
  onValueChange: (value: string) => void;
  disabled?: boolean;
  /** Styles the whole choice, name to rows, as Field's className does. */
  className?: string;
}) {
  const id = useId();
  const labelId = `${id}-label`;
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  // Only the ids that are on the page, as in Field.
  const describedBy =
    [hint ? hintId : null, error ? errorId : null]
      .filter((part) => part !== null)
      .join(" ") || undefined;

  return (
    <div className={cn("grid gap-2", className)}>
      {/* The Label piece's look, on a <p> (see the top of this file). */}
      <p id={labelId} className="text-base leading-snug font-semibold">
        {label}
      </p>
      {hint ? (
        <p id={hintId} className="text-base text-muted-foreground">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-base font-medium text-destructive">
          {error}
        </p>
      ) : null}
      <RadioGroup
        aria-labelledby={labelId}
        aria-describedby={describedBy}
        // undefined, not false, when all is well, as in Field.
        aria-invalid={error ? true : undefined}
        value={value}
        onValueChange={(picked) => onValueChange(String(picked))}
        disabled={disabled}
      >
        {options.map((option) => (
          <label key={option.value} className={ROW_LOOK}>
            <RadioGroupItem value={option.value} className={DOT_LOOK} />
            {/* data-font changes the font only where font-sans is on the same element (globals.css). */}
            <span
              lang={option.lang}
              data-font={option.font}
              className={option.font ? "font-sans" : undefined}
            >
              {option.label}
            </span>
          </label>
        ))}
      </RadioGroup>
    </div>
  );
}
