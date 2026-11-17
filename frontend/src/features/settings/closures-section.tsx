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
// Ongeza, which opens the form (closure-form.tsx), is only for someone holding settings.manage on the whole shop, the
// owner's key (spec §6): a closure closes both sides, and changes everyone's pay, so ATT-8's routes ask the key there,
// and a manager given it on one side alone gets no button. Everyone else sees the list without it. The button only
// keeps a door out of sight: the server checks the key itself on every change.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import type { WhoIsHere } from "@/features/people/who-is-here";
import { formatDay } from "@/lib/format";

import { ClosureForm } from "./closure-form";
import { type Closure, CLOSURES, useClosures } from "./closures";

/** The key that lets a person close the shop, on the whole shop: one of the owner's own four (spec §6). */
const CLOSES_THE_SHOP = "settings.manage";

export function ClosuresSection({ me }: { me: WhoIsHere }) {
  const t = useTranslations("shopSettings.closures");
  const closures = useClosures();
  // On the whole shop only: a key on a side is not enough (see the top of this file).
  const mayChange = me.permissions.whole_shop.includes(CLOSES_THE_SHOP);

  return (
    <section aria-labelledby="area-closures" className="grid gap-4">
      <div className="grid gap-2">
        <h2 id="area-closures" className="text-xl font-semibold">
          {t("title")}
        </h2>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      {/* A failed read shows above the list, and keeps the last answer under it, as on the rules and Pande. */}
      <ApiErrorAlert error={closures.error} />
      {/* Once the list has come, as the form's date boxes start from the shop's today, which comes with it. */}
      {mayChange && closures.data ? (
        <AddClosure today={closures.data.today} />
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
                <ClosureLine closure={closure} />
              </li>
            ))}
          </ul>
        )
      ) : null}
    </section>
  );
}

/** A closure's days as the page writes them: one day as one date, "09/12/2026"; a span as its first and last day,
 * "20/11/2026 – 24/11/2026", both closed. */
function useDaysOf(): (closure: Closure) => string {
  const t = useTranslations("shopSettings.closures");
  return (closure) =>
    closure.first_day === closure.last_day
      ? formatDay(closure.first_day)
      : t("days", {
          first: formatDay(closure.first_day),
          last: formatDay(closure.last_day),
        });
}

/** Ongeza, the form it opens under it, and the line that says a closure was saved. */
function AddClosure({ today }: { today: string }) {
  const t = useTranslations("shopSettings.closures");
  const daysOf = useDaysOf();
  const store = useQueryClient();
  const [open, setOpen] = useState(false);
  // The last closure saved, said once in the status line (below).
  const [saved, setSaved] = useState<Closure | null>(null);
  // Where the keyboard goes when the form closes: back to Ongeza, as the form and the box that had focus are gone.
  // Counted, so each close moves it (settings-screen.tsx).
  const opener = useRef<HTMLButtonElement>(null);
  const [closes, setCloses] = useState(0);
  useEffect(() => {
    if (closes > 0) opener.current?.focus();
  }, [closes]);
  function close() {
    setOpen(false);
    setCloses((count) => count + 1);
  }

  return (
    <div className="grid gap-3">
      {/* While the form is open its own Ghairi closes it, so Ongeza steps aside. */}
      {open ? null : (
        <div className="flex flex-wrap gap-3">
          <Button
            ref={opener}
            size="normal"
            onClick={() => {
              setSaved(null);
              setOpen(true);
            }}
          >
            {t("add")}
          </Button>
        </div>
      )}
      {/* Always on the page, empty until a save: a role="status" line is read when its words change, and one that
          appears with its words already in it may not be read at all (offline-banner.tsx). */}
      <p role="status" className={saved ? "font-medium" : "sr-only"}>
        {saved ? t("added", { name: saved.name, days: daysOf(saved) }) : null}
      </p>
      {open ? (
        <div className="rounded-lg border border-input p-4">
          <ClosureForm
            today={today}
            onSaved={(closure) => {
              setSaved(closure);
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
      ) : null}
    </div>
  );
}

/** One closure: its name, and its days. */
function ClosureLine({ closure }: { closure: Closure }) {
  const daysOf = useDaysOf();
  return (
    <div className="grid gap-3 rounded-lg border border-input p-4">
      <p className="grid gap-1 text-lg">
        <span className="font-semibold">{closure.name}</span>
        <span>{daysOf(closure)}</span>
      </p>
    </div>
  );
}
