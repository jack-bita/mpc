// closures-section.tsx — Siku duka limefungwa, on Mipangilio ya duka (ATT-9): the days the whole shop is closed, a
// public holiday or a family funeral, from today on, soonest first. Under the rules and above Pande (Jack's picture,
// 16 Nov 2026). Each closed day is off, and not paid, whatever the reason (02 §12, ATT-8).
//
// An office screen: it asks GET /api/v1/shops/closures/ through the store of server answers (rule 5), in a place of
// its own (closures.ts). Anyone who works on a side may read the closures, as a worker may know when the shop is
// closed (ATT-8's route asks only that the person sees a side).
//
// The server picks the closures and their order (coming_closures, apps/shops/selectors.py): each active one whose last
// day is today or later, soonest first, a funeral that began two days ago among them, as its last day can still move.
// The page keeps that order. A cancelled closure, or one already over, isn't sent: their days can't change any more,
// and the audit trail keeps them.
//
// The buttons are only for someone holding settings.manage on the whole shop, the owner's key (spec §6): a closure
// closes both sides, and changes everyone's pay, so ATT-8's routes ask the key there, and a manager given it on one
// side alone gets none. Everyone else sees the list without them. Ongeza opens the form that adds a closure
// (closure-form.tsx). Beside each closure, Ondoa takes it off with a reason (closure-cancel.tsx), only while its first
// day is today or later, as the server refuses one already begun (closure.started); and Badilisha siku ya mwisho moves
// its last day, earlier or later, with a reason (closure-last-day.tsx), begun or not. One form at a time on a line: its
// buttons step aside while one is open. The buttons only keep a door out of sight: the server checks the key itself on
// every change.
//
// Each change is said once in the section's status line, as a closure can leave the list, and its line with it: one
// removed, one whose last day moved to yesterday, one someone else cancelled meanwhile. The keyboard then goes to the
// section's heading, the nearest place still on the page; otherwise, back to the button that opened the form.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import type { WhoIsHere } from "@/features/people/who-is-here";
import { codeMessage, useCodeWords } from "@/i18n/codes";

import { ClosureCancel } from "./closure-cancel";
import { ClosureForm } from "./closure-form";
import { ClosureLastDay } from "./closure-last-day";
import { type Closure, CLOSURES, useClosures, useDaysOf } from "./closures";

/** The key that lets a person close the shop, on the whole shop: one of the owner's own four (spec §6). */
const CLOSES_THE_SHOP = "settings.manage";

/** Where the keyboard goes back to once a form under a button closes: the button, as the form and the box that had
 * focus are gone. Counted, so each close moves it (settings-screen.tsx). */
function useFocusBack<T extends HTMLElement>() {
  const target = useRef<T>(null);
  const [moves, setMoves] = useState(0);
  useEffect(() => {
    if (moves > 0) target.current?.focus();
  }, [moves]);
  // A pair, so each caller names its ref "…Ref", which the hooks lint knows is a ref.
  return [target, () => setMoves((count) => count + 1)] as const;
}

export function ClosuresSection({ me }: { me: WhoIsHere }) {
  const t = useTranslations("shopSettings.closures");
  const closures = useClosures();
  const daysOf = useDaysOf();
  // On the whole shop only: a key on a side is not enough (see the top of this file).
  const mayChange = me.permissions.whole_shop.includes(CLOSES_THE_SHOP);
  // The last change made here, said once in the status line (below).
  const [said, setSaid] = useState<string | null>(null);
  // Where the keyboard goes once a closure leaves the list: its line, and the button that had it, are gone.
  const [headingRef, focusHeading] = useFocusBack<HTMLHeadingElement>();

  return (
    <section aria-labelledby="area-closures" className="grid gap-4">
      <div className="grid gap-2">
        {/* tabIndex -1: the keyboard can be sent here, though Tab never stops on it (my-settings.tsx). */}
        <h2
          ref={headingRef}
          id="area-closures"
          tabIndex={-1}
          className="text-xl font-semibold outline-none"
        >
          {t("title")}
        </h2>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      {/* A failed read shows above the list, and keeps the last answer under it, as on the rules and Pande. */}
      <ApiErrorAlert error={closures.error} />
      {/* Always on the page, empty until a change: a role="status" line is read when its words change, and one that
          appears with its words already in it may not be read at all (offline-banner.tsx). */}
      <p role="status" className={said ? "font-medium" : "sr-only"}>
        {said}
      </p>
      {/* Once the list has come, as the form's date boxes start from the shop's today, which comes with it. */}
      {mayChange && closures.data ? (
        <AddClosure
          today={closures.data.today}
          onOpen={() => setSaid(null)}
          onSaved={(closure) =>
            setSaid(t("added", { name: closure.name, days: daysOf(closure) }))
          }
        />
      ) : null}
      {closures.data ? (
        closures.data.closures.length === 0 ? (
          // Said, not left blank: an empty space would read as a page still waiting.
          <p>{t("none")}</p>
        ) : (
          // role="list" written out, for Safari with VoiceOver (device-list.tsx).
          <ul role="list" className="grid gap-4">
            {closures.data.closures.map((closure) => (
              <li key={closure.id}>
                <ClosureLine
                  closure={closure}
                  today={closures.data.today}
                  mayChange={mayChange}
                  onOpen={() => setSaid(null)}
                  onChanged={(sentence, gone) => {
                    setSaid(sentence);
                    if (gone) focusHeading();
                  }}
                />
              </li>
            ))}
          </ul>
        )
      ) : null}
    </section>
  );
}

/** Ongeza, and the form it opens under it. */
function AddClosure({
  today,
  onOpen,
  onSaved,
}: {
  today: string;
  onOpen: () => void;
  onSaved: (closure: Closure) => void;
}) {
  const t = useTranslations("shopSettings.closures");
  const store = useQueryClient();
  const [open, setOpen] = useState(false);
  const [ongezaRef, focusOngeza] = useFocusBack<HTMLButtonElement>();
  function close() {
    setOpen(false);
    focusOngeza();
  }

  return (
    <div className="grid gap-3">
      {/* While the form is open its own Ghairi closes it, so Ongeza steps aside. */}
      {open ? (
        <div className="rounded-lg border border-input p-4">
          <ClosureForm
            today={today}
            onSaved={(closure) => {
              onSaved(closure);
              close();
            }}
            onCancel={() => {
              close();
              // Asked again here too: a send whose answer was lost may have saved the closure, and the owner who
              // gives up should still see it in the list (settings-screen.tsx).
              void store.invalidateQueries({ queryKey: CLOSURES });
            }}
          />
        </div>
      ) : (
        <div className="flex flex-wrap gap-3">
          <Button
            ref={ongezaRef}
            size="normal"
            onClick={() => {
              onOpen();
              setOpen(true);
            }}
          >
            {t("add")}
          </Button>
        </div>
      )}
    </div>
  );
}

/** One closure: its name and its days, and for whoever may, Ondoa while it hasn't begun and Badilisha siku ya mwisho,
 * each with its form under it. */
function ClosureLine({
  closure,
  today,
  mayChange,
  onOpen,
  onChanged,
}: {
  closure: Closure;
  /** The shop's today, from the server's answer: a closure whose first day is before it has begun. */
  today: string;
  /** Whether the person holds settings.manage on the whole shop. */
  mayChange: boolean;
  onOpen: () => void;
  /** Called after a change, with its sentence, and whether the closure has left the list (see the top of this file). */
  onChanged: (sentence: string, gone: boolean) => void;
}) {
  const t = useTranslations("shopSettings.closures");
  const codes = useCodeWords();
  const daysOf = useDaysOf();
  const store = useQueryClient();
  // The form open under the line, if any: one at a time.
  const [open, setOpen] = useState<"remove" | "lastDay" | null>(null);
  const [ondoaRef, focusOndoa] = useFocusBack<HTMLButtonElement>();
  const [lastDayRef, focusLastDay] = useFocusBack<HTMLButtonElement>();
  // Up to and on its first day: days as text sort as days do ("2026-11-20"). Once one of its days has passed, that
  // day stays closed, and only its last day can move (closure.started).
  const mayRemove = mayChange && closure.first_day >= today;

  function giveUp(focusTheButton: () => void) {
    setOpen(null);
    focusTheButton();
    // Asked again: a send whose answer was lost may have changed the closure, and the owner who gives up should still
    // see it as it is (settings-screen.tsx).
    void store.invalidateQueries({ queryKey: CLOSURES });
  }

  return (
    <div className="grid gap-3 rounded-lg border border-input p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="grid gap-1 text-lg">
          <span className="font-semibold">{closure.name}</span>
          <span>{daysOf(closure)}</span>
        </p>
        {/* While a form is open its own Ghairi closes it, so the buttons step aside. */}
        {mayChange && open === null ? (
          <div className="flex flex-wrap gap-3">
            {mayRemove ? (
              <Button
                ref={ondoaRef}
                kind="second"
                size="normal"
                // Each starts with the word on it, and names the closure, as a list of the same words reads to a screen
                // reader as nothing.
                aria-label={t("removeOf", { name: closure.name })}
                onClick={() => {
                  onOpen();
                  setOpen("remove");
                }}
              >
                {t("remove")}
              </Button>
            ) : null}
            <Button
              ref={lastDayRef}
              kind="second"
              size="normal"
              aria-label={t("changeLastDayOf", { name: closure.name })}
              onClick={() => {
                onOpen();
                setOpen("lastDay");
              }}
            >
              {t("changeLastDay")}
            </Button>
          </div>
        ) : null}
      </div>
      {open === "remove" ? (
        <ClosureCancel
          closure={closure}
          // The line leaves the list once it is read again: the section says so, and takes the keyboard. The form closes
          // now, so a list that is slow to come back never shows an open Ondoa for a closure already cancelled.
          onCancelled={() => {
            setOpen(null);
            onChanged(
              t("removed", { name: closure.name, days: daysOf(closure) }),
              true,
            );
          }}
          onCancel={() => giveUp(focusOndoa)}
        />
      ) : null}
      {open === "lastDay" ? (
        <ClosureLastDay
          closure={closure}
          today={today}
          onMoved={(saved) => {
            setOpen(null);
            // A last day now before today ends the closure: it leaves the list (coming_closures).
            const gone = saved.last_day < today;
            onChanged(
              t("moved", { name: saved.name, days: daysOf(saved) }),
              gone,
            );
            if (!gone) focusLastDay();
          }}
          // Someone else cancelled it meanwhile: the section says so in the server's sentence, as the line leaves.
          onGone={() => {
            setOpen(null);
            onChanged(codeMessage(codes, "closure.not_active"), true);
          }}
          onCancel={() => giveUp(focusLastDay)}
        />
      ) : null}
    </div>
  );
}
