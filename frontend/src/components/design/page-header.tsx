// page-header.tsx — the top of a page under the green bar: a back arrow on the far left, the page's title
// beside it, and the page's few words of explanation under the title (Jack, 17 Nov 2026). Mipangilio ya
// duka wears it first; every page that is reached from another, as each office screen is from the office's
// home, wears the same, so the way back is always in the same place.
//
// The arrow goes back to where the person was, as the browser's own back does (router.back()), not to a
// page fixed in advance: a manager who came to the settings from the office's home returns there, and one
// who came from another screen returns to that one. It goes back only when the tab's note says the person
// moved between the app's own pages (in-app-moves.tsx). With no such note, as on a page opened from a
// bookmark, a typed address or another website, going back would leave the app, or do nothing, so the arrow
// goes to `fallback` instead: the office's home unless the page says otherwise.
//
// The browser's history alone can't tell: it doesn't say whose its pages are, and Chrome leaves its new-tab
// page in a tab's history, so a bookmark opened from it has a page before it that isn't ours (the branch's
// review, 17 Nov 2026).
//
// A step inside one page, as the PIN pad inside `/` (pin-login.tsx), has no page before it to go back to:
// it gives `onBack`, which takes the person to the step before, the tiles, as its old *Rudi* did. And while
// a step must not be left, as while a PIN is on its way, it holds the arrow (`backDisabled`). Every page
// and step reached from another wears this arrow, and no *Rudi* button of its own (Jack, OPS-13). A page
// that is on its way out by itself leaves it out for that moment (`arrow={false}`), its title kept: the
// clock-out's goodbye, which logs the seller out (attendance.tsx).
//
// "use client": it asks use-intl for the arrow's name, and moves to another page in the browser.
"use client";

import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import type { Ref } from "react";
import { useTranslations } from "use-intl";

import { movedInApp } from "@/components/in-app-moves";

import { Button } from "./button";

/** Where the arrow goes when going back would leave the app, or do nothing: the office's home (UI-5). */
export const BACK_FALLBACK = "/office/";

export function PageHeader({
  title,
  intro,
  fallback = BACK_FALLBACK,
  headingRef,
  onBack,
  backDisabled = false,
  arrow = true,
}: {
  /** The page's title, its one <h1>. */
  title: string;
  /** The words under the title that say what the page is for. */
  intro?: string;
  /** Where the arrow goes when the page before isn't the app's own, or there is none. */
  fallback?: string;
  /** For a page that moves focus to its title as it opens, so a screen reader says where the person is
   * (my-settings.tsx). Given, the title takes focus from code only (tabIndex -1), never from Tab. */
  headingRef?: Ref<HTMLHeadingElement>;
  /** For a step inside one page: the arrow goes back to the step before, and never moves to a page. */
  onBack?: () => void;
  /** Holds the arrow, while the step mustn't be left (a PIN on its way). */
  backDisabled?: boolean;
  /** False leaves the arrow out, the title kept: a page on its way out by itself (the goodbye). */
  arrow?: boolean;
}) {
  const t = useTranslations("pageHeader");
  const router = useRouter();

  function goBack() {
    if (onBack) return onBack();
    // Both: the note says the page before is ours; a history of more than this page says there is one.
    if (movedInApp() && window.history.length > 1) router.back();
    else router.push(fallback);
  }

  return (
    <div className="grid gap-2">
      {/* The arrow before the title, both on one line, at the page's top left, where a phone's own back
          arrow sits. */}
      <div className="flex items-center gap-3">
        {/* A square button, as tall as a normal one (44 px), so a finger finds it. Its name is a word,
            as a screen reader can't read an arrow; the arrow itself is hidden from it. */}
        {arrow && (
          <Button
            kind="second"
            size="normal"
            aria-label={t("back")}
            className="w-(--control-normal) shrink-0 px-0"
            onClick={goBack}
            disabled={backDisabled}
          >
            <ArrowLeft aria-hidden className="size-6" />
          </Button>
        )}
        {/* No ring on the title when code focuses it: it isn't something to press, and the ring would
            look like a button that does nothing. */}
        <h1
          ref={headingRef}
          tabIndex={headingRef ? -1 : undefined}
          className="text-2xl font-semibold outline-none"
        >
          {title}
        </h1>
      </div>
      {intro ? <p className="text-muted-foreground">{intro}</p> : null}
    </div>
  );
}
