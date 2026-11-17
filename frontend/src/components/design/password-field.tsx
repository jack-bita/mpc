// password-field.tsx — a password box with an eye at its end: pressed, it shows what is typed; pressed
// again, it hides it (UI-5, ADR-0039). Every password box in the app uses it: the login, the temporary
// password, and the new one typed twice (Jack, 8 Nov 2026).
//
// It is Field (field.tsx), with the box's type switched between password and text, and the eye in Field's
// `end` slot. One name for the eye, pressed or not ("Onyesha nenosiri"), with aria-pressed saying which:
// a screen reader then says "Onyesha nenosiri, pressed", where a name that changed with each press would
// leave the person guessing what the button does now.
//
// Shown, the box is plain text, which a browser may spell-check, sometimes on a server, and a phone may
// correct or capitalise: all three stay off, shown or not.
//
// "use client": it keeps whether the password shows, and asks use-intl for the eye's name.
"use client";

import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { useTranslations } from "use-intl";

import { cn } from "@/lib/utils";

import { Field, type FieldProps } from "./field";

export type PasswordFieldProps = Omit<
  FieldProps,
  "type" | "end" | "spellCheck" | "autoCorrect" | "autoCapitalize"
>;

export function PasswordField({ size = "big", ...field }: PasswordFieldProps) {
  const t = useTranslations("passwordField");
  const [shown, setShown] = useState(false);

  return (
    <Field
      {...field}
      size={size}
      type={shown ? "text" : "password"}
      spellCheck={false}
      autoCorrect="off"
      autoCapitalize="none"
      end={
        <button
          // "button": pressed inside a form, it shows the password; it never sends the form.
          type="button"
          aria-label={t("show")}
          aria-pressed={shown}
          onClick={() => setShown((now) => !now)}
          className={cn(
            // A square over the box's end, as high as the box: a finger finds it at once (52 px big).
            "absolute inset-y-0 right-0 flex items-center justify-center rounded-lg",
            size === "normal" ? "w-(--control-normal)" : "w-(--control-big)",
            // The hint's colour, darker under the mouse: it says how to use the box, not what it holds.
            "text-muted-foreground hover:text-foreground",
            // The full-strength ring every control has (UI-7), in place of the browser's own outline.
            "outline-none focus-visible:ring-3 focus-visible:ring-ring",
            "[&_svg]:size-5",
          )}
        >
          {/* The icon says what the name says, so a screen reader skips it. Crossed out while shown: the
              next press hides it again. */}
          {shown ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
        </button>
      }
    />
  );
}
