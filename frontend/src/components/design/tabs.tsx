// tabs.tsx — a page cut into sections, one open at a time, with a row of tabs on top (ADR-0039). Mipangilio
// ya duka is the first to wear it: its areas, closed days and sides were one long page to scroll on a phone.
//
// shadcn's tabs (components/ui/tabs.tsx) give the behaviour, through Base UI: role="tablist", "tab" and
// "tabpanel", tied together, so a screen reader says "Pesa, tab, 2 of 6, selected"; the arrow keys move
// between the tabs, Home and End jump to the ends, and Enter or Space opens one. This piece sets the look:
//   - the row scrolls sideways when the tabs don't fit, as on a phone, never wrapping onto two lines,
//     and the open tab is scrolled into sight, as one opened from the address may start off the edge;
//   - the row stays at the top of the screen while a long section scrolls under it (sticky), so another
//     section is always one tap away;
//   - the open tab is green, with a green line under it, so it shows by more than its colour alone.
//
// A screen gives the sections as a list, not as parts it puts together: a new section is one more item,
// and every page with tabs looks and behaves the same (Jack, 17 Nov 2026).
//
// Every section stays on the page, only hidden while another is open (Base UI's keepMounted): a form half
// filled in one section is still there when the person comes back to it, and nothing has to load again.
//
// "use client": Base UI's tabs keep state and listen to the keyboard, in the browser's React.
"use client";

import { type ReactNode, useEffect, useRef } from "react";

import {
  Tabs as ShadcnTabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

/** One section: what the screen gets back when its tab is opened, its tab's words, and what it shows. */
export interface TabSection {
  value: string;
  label: string;
  content: ReactNode;
}

/** The row: as wide as the page, scrolling sideways, sticky at the top, with a pale line along its foot.
 * shadcn's row is a grey pill as wide as its tabs and 32 px tall; cn() lets each class here replace its
 * twin there (h-auto for h-8, w-full for w-fit, justify-start for justify-center). */
export const LIST_LOOK = [
  "sticky top-0 z-10 w-full justify-start gap-1 overflow-x-auto overflow-y-hidden",
  "rounded-none border-b border-border bg-background p-0",
  "group-data-horizontal/tabs:h-auto",
  // A thin bar, where the browser can: a phone's own disappears when idle, and a laptop's thick one
  // would sit on the tabs' line.
  "[scrollbar-width:thin]",
].join(" ");

/** One tab: as tall as a normal button (44 px), so a finger finds it, and never squeezed (flex-none), so a
 * long name, "Siku duka limefungwa", stays on one line and the row scrolls instead. */
export const TAB_LOOK = [
  "h-auto min-h-(--control-normal) flex-none rounded-none px-4 text-base font-semibold",
  // At rest the pale text (--muted-foreground reads at 6.0:1 on white); shadcn's 60% black reads at only
  // about 3.9:1, under the 4.5:1 words need.
  // Hover darkens a closed tab; the open one stays green under the mouse. shadcn's hover:text-foreground
  // stays in its classes, so the open tab's own hover rule says green again: [data-active]:hover is more
  // specific than :hover, so it wins whatever the order in the CSS.
  "text-muted-foreground hover:text-foreground data-active:hover:text-primary",
  // Open: green words (5.02:1 on white) and a 3 px green line under them, at the row's foot.
  "data-active:text-primary",
  "after:bg-primary group-data-horizontal/tabs:after:bottom-0 group-data-horizontal/tabs:after:h-[3px]",
  // Full strength, drawn inside the tab: shadcn fades the ring to half (2.57:1 on white, under the 3:1 a
  // keyboard user needs, UI-7), and a ring drawn outside would be cut off by the scrolling row.
  "focus-visible:border-transparent focus-visible:ring-ring focus-visible:ring-inset focus-visible:outline-none",
].join(" ");

export function Tabs({
  label,
  sections,
  value,
  onChange,
}: {
  /** The row's name for a screen reader, as the page's title: "Mipangilio ya duka". */
  label: string;
  sections: readonly TabSection[];
  /** The open section's value. The screen holds it, so it can keep it in the address too. */
  value: string;
  onChange: (value: string) => void;
}) {
  const list = useRef<HTMLDivElement>(null);
  // Brings the open tab into sight inside the row, by scrolling the row alone, sideways. Not scrollIntoView:
  // it may scroll the page up or down too, as when the page comes back to a place half way down after the
  // browser's back. The row is sticky, so the tabs' offsetLeft counts from the row's own edge.
  useEffect(() => {
    const row = list.current;
    const tab = row?.querySelector<HTMLElement>("[data-active]");
    if (!row || !tab) return;
    const start = tab.offsetLeft;
    const end = start + tab.offsetWidth;
    if (start < row.scrollLeft) row.scrollLeft = start;
    else if (end > row.scrollLeft + row.clientWidth)
      row.scrollLeft = end - row.clientWidth;
  }, [value]);

  return (
    <ShadcnTabs
      value={value}
      onValueChange={(next) => onChange(String(next))}
      // min-w-0: inside a page's grid or flex column, a box is never narrower than its content by default,
      // so the row of tabs, as wide as all its tabs together, would widen the whole page and the phone
      // would scroll the page sideways. With it, the row is as wide as the page, and scrolls itself.
      className="min-w-0 gap-4"
    >
      <TabsList
        ref={list}
        variant="line"
        aria-label={label}
        className={LIST_LOOK}
      >
        {sections.map((section) => (
          <TabsTrigger
            key={section.value}
            value={section.value}
            className={TAB_LOOK}
          >
            {section.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {sections.map((section) => (
        // text-base: shadcn's panel makes everything in it small (text-sm), and the screens are sized for
        // reading at arm's length. Base UI lets Tab stop on the open panel, so a keyboard reaches the section
        // straight from its tab; once there, the tab no longer shows focus, so the panel shows its own ring,
        // at full strength (UI-7), where shadcn's outline-none would show nothing (WCAG 2.4.7).
        <TabsContent
          key={section.value}
          value={section.value}
          keepMounted
          className="rounded-lg text-base focus-visible:ring-[3px] focus-visible:ring-ring"
        >
          {section.content}
        </TabsContent>
      ))}
    </ShadcnTabs>
  );
}
