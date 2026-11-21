// sheet.tsx — a short task that slides up over the screen it belongs to, with Ghairi and its main button at the bottom
// (ADR-0039). Jack chose it for short actions (20 Nov 2026, ATT-6): pick an option, type why, save, without leaving
// the page behind it. Deciding a day under a worker's calendar is the first to wear it; fixing a tap (ATT-13) next.
//
//   ┌──────────────────────────────────┐
//   │ Amua siku ya Juma                │  the title, which a screen reader says as the sheet opens
//   │ Alhamisi 12/11 · Ingia 07:50     │  what it is about, in the pale grey
//   │ ( ) Siku kamili  ...             │  the form, which the screen gives
//   │ [ Ghairi ]     [ Hifadhi uamuzi ]│  always the two, side by side, the main one on the right
//   └──────────────────────────────────┘
//
// shadcn's sheet (components/ui/sheet.tsx) gives the behaviour, through Base UI's dialog: the page behind it is shut
// off while it is open (a modal, so Tab stays inside it and a screen reader reads only it), the focus moves into it as
// it opens and back to the button that opened it as it closes, and Esc closes it, as Ghairi does. This piece sets the
// look and the two buttons:
//   - always from the bottom, as on a phone, where a thumb reaches it; on a laptop's wide screen its contents keep a
//     phone's width in the middle, so a line of the form is never a metre long;
//   - no ✕ in the corner, which shadcn draws in English: Ghairi is the one way to close it in words, beside the main
//     button, where every sheet has it (Jack: "Sheet with cancel and CTA");
//   - the two buttons are a form's: Enter in a box sends it, as the main button does. The browser's own checks of a
//     box are off (noValidate): a last day past its `max` would stop the send with the browser's bubble, in the
//     browser's language, where the screen says it beside the box in the shop's (UI-10);
//   - the main button is green, or red (`actionKind: "danger"`) for an action that is for good, as Ameondoka (UI-10);
//   - a tap on the dimmed page closes nothing (Jack, UI-10): every sheet holds a form, and a thumb that lands beside
//     it would throw away a half-typed reason. Ghairi and Esc close it, both on purpose;
//   - while the main action is on its way (`busy`), both buttons are held and nothing closes it, Esc included: a
//     decision being saved can't be left half-seen, and the screen shows its answer, or why it failed, inside the
//     sheet;
//   - as it closes, the keyboard goes back to the button that opened it, Base UI's own way, unless the screen names
//     another place (`finalFocus`): once a change is done, the button may be gone (Simamisha becomes Rudisha) or the
//     news is elsewhere, so the screen names its done line (UI-10). Base UI moves it a moment after the sheet goes
//     (a microtask), so a screen that moves the keyboard itself would see it taken back to the button.
//
// A screen gives the words: the title, what it's about, the main button's words, and the form. Ghairi's word is the
// sheet's own (sheet.cancel).
//
// "use client": Base UI's dialog keeps state and listens to the keyboard, in the browser's React; and it asks
// use-intl for a word.
"use client";

import type { FormEvent, ReactNode } from "react";
import { useTranslations } from "use-intl";

import {
  Sheet as ShadcnSheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

import { Button } from "./button";

/** The popup: from the bottom edge, rounded at its top corners, never taller than most of the screen, so the page
 * behind still shows above it and a long form scrolls inside. shadcn's sheet gives no padding of its own to its
 * popup: the room is here, and at the bottom the phone's own bar's (safe-area) too. */
export const SHEET_LOOK = [
  "max-h-[90dvh] rounded-t-xl px-4 pt-2",
  "pb-[max(1rem,env(safe-area-inset-bottom))]",
].join(" ");

export function Sheet({
  open,
  onClose,
  title,
  description,
  actionLabel,
  onAction,
  busy = false,
  actionDisabled = false,
  actionKind = "main",
  finalFocus,
  children,
}: {
  /** Whether it is on the screen: the screen keeps this, opening it from its own button. */
  open: boolean;
  /** Ghairi or Esc: the screen closes it, forgetting what was typed. */
  onClose: () => void;
  title: string;
  description?: ReactNode;
  /** The main button's words: *Hifadhi uamuzi*. */
  actionLabel: string;
  /** The main button, or Enter in a box: the screen checks and sends its form. */
  onAction: () => void;
  /** The main action is on its way: both buttons held, and nothing closes it. */
  busy?: boolean;
  /** The main button alone held, Ghairi still free: with no network, so nothing waits unsent while it looks done. */
  actionDisabled?: boolean;
  /** Red for an action that is for good (Ameondoka); else the main green. */
  actionKind?: "main" | "danger";
  /** Where the keyboard goes as it closes, asked at that moment: an element, or null for the button that opened it. */
  finalFocus?: () => HTMLElement | null;
  /** The form's boxes and choices, and a failure to show inside the sheet. */
  children: ReactNode;
}) {
  const t = useTranslations("sheet");

  function send(event: FormEvent<HTMLFormElement>) {
    // The browser's own sending of a form would load the page again: this one is sent by the screen.
    event.preventDefault();
    if (!busy && !actionDisabled) onAction();
  }

  return (
    <ShadcnSheet
      open={open}
      // A tap on the dimmed page is no way to close it (Jack, UI-10): it would throw away what was typed.
      disablePointerDismissal
      // Base UI asks to close on Esc. Never while the main action is on its way.
      onOpenChange={(next) => {
        if (!next && !busy) onClose();
      }}
    >
      <SheetContent
        side="bottom"
        showCloseButton={false}
        className={SHEET_LOOK}
        // Base UI's own, back to the button, unless the screen names a place; its null means the same default.
        finalFocus={finalFocus ?? true}
      >
        {/* min-h-0 and the scrolling middle: a form taller than the sheet scrolls under its title, while the two
            buttons stay in sight at the bottom. */}
        <form
          noValidate
          onSubmit={send}
          className="mx-auto flex min-h-0 w-full max-w-lg flex-col"
        >
          <SheetHeader className="px-0">
            <SheetTitle className="text-xl font-semibold">{title}</SheetTitle>
            {description ? (
              <SheetDescription className="text-base text-muted-foreground">
                {description}
              </SheetDescription>
            ) : null}
          </SheetHeader>
          <div className="grid min-h-0 gap-4 overflow-y-auto py-1">
            {children}
          </div>
          {/* Ghairi first, the main button last, on the right, where the thumb ends: as on every screen's pair. */}
          <SheetFooter className="flex-row gap-3 px-0 pb-0">
            <Button
              kind="second"
              className="flex-1"
              disabled={busy}
              onClick={onClose}
            >
              {t("cancel")}
            </Button>
            <Button
              kind={actionKind}
              type="submit"
              className="flex-1"
              disabled={busy || actionDisabled}
            >
              {actionLabel}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </ShadcnSheet>
  );
}
