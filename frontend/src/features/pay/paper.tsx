// paper.tsx — a page made to be printed on A4 (WAGE-5): the month's sheet, for NSSF and the owner's file, and the
// payslips, one page each. Both are printed from Chrome on any A4 printer, or saved as a PDF and printed elsewhere
// (Jack: A, never the shop's 8 cm receipt printer, whose paper fades in months). This part owns what both share:
//
//   on the screen                             on paper
//   ‹ Orodha ya malipo        [ Chapisha ]     (nothing of the screen: no arrow, no button, no top bar)
//   ┌─────────────────────────┐               ┌─────────────────────────┐
//   │  the paper, A4 wide     │               │  the paper, edge to     │
//   │                         │               │  edge of the A4 sheet   │
//   └─────────────────────────┘               └─────────────────────────┘
//
// The page's size is A4, with no margin of its own: the paper pads itself inside. SPIKE-2 saw Chrome print its own
// date, title and address into a page's margin; with none, there is no room for them (docs/spikes, 03 §5.15).
// Chapisha waits until every picture on the paper, each worker's signature, has come or failed, or a sheet prints with
// empty boxes where the signatures go: they load one by one from the attachments' route (photoAddress).
//
// The ink is the app's own dark text on its white (globals.css): the app is light only, so the paper prints dark on
// white; on paper every word and line inside a sheet takes that ink, never the pale greys a screen uses for quiet
// words, which print faint (PaperSheet).
//
// "use client": it asks use-intl for words (use-client.test.ts), and watches the paper's pictures.
"use client";

import {
  type ReactNode,
  type RefObject,
  useEffect,
  useRef,
  useState,
} from "react";
import { useTranslations } from "use-intl";

import { Button } from "@/components/design/button";
import { PageHeader } from "@/components/design/page-header";

/** A4, with no margin of the page's own: the paper's padding stands in for it, and leaves Chrome no room to print its
 * header and footer. Only while a paper is on the page, so no other page prints at a size of ours. */
const A4 = "@page { size: A4; margin: 0; }";

export function Paper({
  title,
  intro,
  fallback,
  printable,
  children,
}: {
  /** The page's title on the screen, its one <h1>, as every page's (PageHeader); the paper names itself inside. */
  title: string;
  intro?: string;
  /** Where the arrow goes when the page before isn't the app's own: the page the paper was opened from. */
  fallback?: string;
  /** Whether a paper is drawn to print: false while its read is on its way, after a refusal, or of a month still open,
   * when the page says why in words that never print, so Chapisha would print a blank page (WAGE-5's review). */
  printable: boolean;
  /** The paper itself: one A4 page or more, each a <PaperSheet>. */
  children: ReactNode;
}) {
  const t = useTranslations("pay.paper");
  const paper = useRef<HTMLDivElement>(null);
  const ready = usePicturesLoaded(paper);

  return (
    <div className="grid gap-4 print:block">
      <style>{A4}</style>
      {/* The screen's parts, never on paper. */}
      <div className="grid gap-2 print:hidden">
        <PageHeader
          title={title}
          intro={intro}
          fallback={fallback}
          action={
            <Button
              kind="main"
              size="normal"
              disabled={!printable || !ready}
              onClick={() => window.print()}
            >
              {t("print")}
            </Button>
          }
        />
        {/* Why Chapisha waits for the pictures, said while it does; a screen reader hears it as it changes. With nothing
            to print, the screen's own lines say why. */}
        <p role="status" className="text-muted-foreground">
          {printable && !ready ? t("picturesLoading") : ""}
        </p>
      </div>
      <div ref={paper} className="grid gap-4 print:block">
        {children}
      </div>
    </div>
  );
}

/** The top of every paper: the shop, by its code and its name ("MPC · Mabatini Pumba Center"), or its name alone when the
 * two are one; then the paper's own title, the sheet's one heading, under the page's <h1> (PageHeader). */
export function PaperHeading({
  shop,
  title,
}: {
  shop: { code: string; name: string };
  title: string;
}) {
  const t = useTranslations("pay.paper");
  return (
    <header className="grid gap-1">
      <p className="text-lg font-semibold">
        {shop.code === shop.name ? shop.name : t("shop", shop)}
      </p>
      <h2 className="text-xl font-semibold">{title}</h2>
    </header>
  );
}

/** One A4 page of a paper: on the screen a white page with an edge, A4 wide at most; on paper the whole sheet, with
 * the page's own padding, and the next sheet starting on a new page (break-after). On paper every word and line inside
 * it is the dark ink, the quiet grey of a screen's notes (Aliondoka…, the demo's signature line) and the pale edge of a
 * signature's box among them, as they print faint (print:**:, WAGE-5's review). A sheet longer than a page, a month's
 * of twenty workers or more, gets its padding again on each page it runs onto (box-decoration-clone), or page 2's rows
 * would start at the paper's very edge, which a printer can't reach (WAGE-5's review). Checked by printing a 60-row
 * table to PDF in Playwright's Chromium: with it, page 1's last row ends 34 pt (12 mm) higher. */
export function PaperSheet({ children }: { children: ReactNode }) {
  return (
    <section className="bg-background text-foreground mx-auto w-full max-w-[210mm] break-after-page border border-border p-[12mm] box-decoration-clone print:max-w-none print:border-0 print:**:border-foreground print:**:text-foreground last:break-after-auto">
      {children}
    </section>
  );
}

/** Whether every picture in the box has come or failed: a picture still on its way says `complete` false. Asked again
 * as each one loads or fails (load and error don't bubble, so they are heard on their way down, capture), and as the
 * box's contents change, as a paper's rows come once its read answers. */
export function usePicturesLoaded(box: RefObject<HTMLElement | null>): boolean {
  const [loaded, setLoaded] = useState(true);
  useEffect(() => {
    const element = box.current;
    if (element === null) return;
    const check = () =>
      setLoaded(
        Array.from(element.querySelectorAll("img")).every(
          (picture) => picture.complete,
        ),
      );
    check();
    element.addEventListener("load", check, true);
    element.addEventListener("error", check, true);
    const watch = new MutationObserver(check);
    watch.observe(element, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["src"],
    });
    return () => {
      element.removeEventListener("load", check, true);
      element.removeEventListener("error", check, true);
      watch.disconnect();
    };
  }, [box]);
  return loaded;
}
