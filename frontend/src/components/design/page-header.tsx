// page-header.tsx — the top of a page under the green bar: a back arrow on the far left, the page's title
// beside it, and the page's few words of explanation under the title (Jack, 17 Nov 2026). Mipangilio ya
// duka wears it first; every page that is reached from another, as each office screen is from the office's
// home, wears the same, so the way back is always in the same place.
//
// The arrow goes back to where the person was, as the browser's own back does (router.back()), not to a
// page fixed in advance: a manager who came to the settings from the office's home returns there, and one
// who came from another screen returns to that one. A page opened with nothing before it in the tab, from
// a bookmark or a link in a new tab, has nowhere to go back to: the browser's back would do nothing, so
// the arrow goes to `fallback` instead, the office's home unless the page says otherwise.
//
// The trade-off: the browser's history can't say whether the page before was the app's own. Someone who
// typed the address after another website goes back to that website, as the browser's own back would.
//
// "use client": it asks use-intl for the arrow's name, and moves to another page in the browser.
"use client";

import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import type { Ref } from "react";
import { useTranslations } from "use-intl";

import { Button } from "./button";

/** Where the arrow goes when the tab has no page before this one: the office's home (UI-5). */
export const BACK_FALLBACK = "/office/";

export function PageHeader({
  title,
  intro,
  fallback = BACK_FALLBACK,
  headingRef,
}: {
  /** The page's title, its one <h1>. */
  title: string;
  /** The words under the title that say what the page is for. */
  intro?: string;
  /** Where the arrow goes when there is no page to go back to. */
  fallback?: string;
  /** For a page that moves focus to its title as it opens, so a screen reader says where the person is
   * (my-settings.tsx). Given, the title takes focus from code only (tabIndex -1), never from Tab. */
  headingRef?: Ref<HTMLHeadingElement>;
}) {
  const t = useTranslations("pageHeader");
  const router = useRouter();

  function goBack() {
    // A history of one is this page alone: a fresh tab, or a bookmark opened in one.
    if (window.history.length > 1) router.back();
    else router.push(fallback);
  }

  return (
    <div className="grid gap-2">
      {/* The arrow before the title, both on one line, at the page's top left, where a phone's own back
          arrow sits. */}
      <div className="flex items-center gap-3">
        {/* A square button, as tall as a normal one (44 px), so a finger finds it. Its name is a word,
            as a screen reader can't read an arrow; the arrow itself is hidden from it. */}
        <Button
          kind="second"
          size="normal"
          aria-label={t("back")}
          className="w-(--control-normal) shrink-0 px-0"
          onClick={goBack}
        >
          <ArrowLeft aria-hidden className="size-6" />
        </Button>
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
