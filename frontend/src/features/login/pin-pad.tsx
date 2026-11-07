// pin-pad.tsx — the big PIN pad on a shared device's login screen: ten digit keys and Futa, the laptop's
// number keys too, and four dots that fill as the PIN is typed (UI-4, 03 §5.9).
//
// It only collects the digits. The 4th one hands the PIN at once, with no OK key, to the screen that drew
// the pad (onPin); the login screen sends it to the server and shows what the server said. The pad never
// calls the server itself, so its tests need no network. It then starts empty again, ready for the next try.
//
// The digits typed are never shown, only how many: the next person at the counter could read them.
//
// "use client": it keeps what is typed in React's state and listens to the keyboard, both in the browser only.
"use client";

import { Delete } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/design/button";
import { cn } from "@/lib/utils";

/** A PIN's length: 4 digits (03 §5.9). */
export const PIN_LENGTH = 4;

// The digit keys, in the order they sit: 1 to 9, then 0. In a list, not typed between tags: the lint rule
// takes any text between tags for a word that belongs in the books.
const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];

export function PinPad({
  onPin,
  disabled = false,
}: {
  /** Called with the whole PIN, the moment its last digit is typed. */
  onPin: (pin: string) => void;
  /** True while a PIN is on its way to the server: no key takes anything. */
  disabled?: boolean;
}) {
  const t = useTranslations("login.pinPad");
  // What has been typed so far: "" at first, then "1", "19"… (lesson 1).
  const [digits, setDigits] = useState("");

  // One digit more. The 4th sends the whole PIN, and the pad starts empty again for the next try:
  // after a wrong PIN, it is typed again from the start.
  function press(digit: string) {
    // The keys are switched off too, but the laptop's keyboard isn't a key of ours: this guards it.
    if (disabled) return;
    const typed = digits + digit;
    if (typed.length === PIN_LENGTH) {
      setDigits("");
      onPin(typed);
    } else {
      setDigits(typed);
    }
  }

  // The last digit taken back. With nothing typed, slice gives "" again: nothing breaks.
  function erase() {
    if (disabled) return;
    setDigits(digits.slice(0, -1));
  }

  // The laptop's keyboard (03 §7: laptops are keyboard first): a number key types its digit, Backspace
  // takes one back. Not a key held down, which repeats by itself, nor one pressed with Ctrl, Alt or
  // Cmd: Ctrl+1 is the browser's own, for its first tab.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.repeat || event.ctrlKey || event.altKey || event.metaKey)
        return;
      if (/^[0-9]$/.test(event.key)) press(event.key);
      else if (event.key === "Backspace") erase();
    }
    window.addEventListener("keydown", onKey);
    // Taken off as the pad leaves the screen, and before each new draw puts on a fresh one.
    return () => window.removeEventListener("keydown", onKey);
    // No list of what it depends on, on purpose: it runs again after every draw, so the listener always
    // reads today's digits. One kept from the first draw would still see nothing typed.
  });

  return (
    <div className="flex flex-col items-center gap-6">
      {/* The dots, one per digit, filled as each is typed. Hidden from a screen reader, which hears the
          line under them instead. */}
      <div aria-hidden="true" className="flex gap-4">
        {Array.from({ length: PIN_LENGTH }, (_, place) => (
          <span
            key={place}
            className={cn(
              "size-5 rounded-full border-2 border-foreground",
              place < digits.length && "bg-foreground",
            )}
          />
        ))}
      </div>
      {/* Hidden from the eye, which has the dots, not from a screen reader. role="status": it is said
          each time it changes, "Umeandika tarakimu 2 kati ya 4". */}
      <p role="status" className="sr-only">
        {t("typed", { count: digits.length, length: PIN_LENGTH })}
      </p>
      {/* Three across, as on a phone: 1 2 3 on top, and 0 in the middle of the last row, Futa beside it.
          The second kind, the blue outline: ten green keys would each shout like a screen's main action.
          Big, the button's own default height, for a finger at the counter. */}
      <div className="grid grid-cols-3 gap-3">
        {KEYS.map((digit) => (
          <Button
            key={digit}
            kind="second"
            className={cn("w-20 text-2xl", digit === "0" && "col-start-2")}
            disabled={disabled}
            onClick={() => press(digit)}
          >
            {digit}
          </Button>
        ))}
        {/* Only the icon shows, so its name comes from the books, for a screen reader and for the tests. */}
        <Button
          kind="second"
          className="w-20"
          aria-label={t("erase")}
          disabled={disabled}
          onClick={erase}
        >
          <Delete aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}
