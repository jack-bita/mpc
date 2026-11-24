// flags-screen.tsx — Tofauti, the list of what the system found and a person must look into (CTRL-4, 02 §13), as Jack
// pictured it (24 Nov 2026): what waits and what is closed, each behind its tab, "Zinasubiri (5)" and "Zilizofungwa",
// newest found first, a line per flag: its kind, then who it names, where, and the day. A line opens the flag's own
// page. A long list comes 50 at a time, with Onyesha zaidi. Chuja keeps it to a side and a kind.
//
// Nothing opens in place on it (Jack, CTRL-4): a flag is a page of its own (flag-page.tsx), and Chuja a sheet
// (flag-filter.tsx). The open tab and the filter are in the address, so coming back finds the list as it was left.
//
// An office screen: it asks the server through the store of server answers (rule 5), and needs the internet, which the
// office area says while it is gone. The server keeps the flags to those the person may close; someone who may close
// none has no button on the office home, and opening the address shows the server's refusal.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Card } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import { Tabs } from "@/components/design/tabs";
import { TextLink } from "@/components/design/text-link";
import { useTabInAddress, useWordInAddress } from "@/components/tab-in-address";
import { useWhoIsHere } from "@/features/people/who-is-here";

import { FlagFilterSheet, useFilterWords } from "./flag-filter";
import {
  filterFrom,
  FLAG_STATES,
  type FlagFilter,
  type FlagLine,
  flagPage,
  type FlagState,
  useDayWords,
  useFlags,
  useKindWords,
  useNames,
} from "./flags";

/** The address's names for Chuja's two choices: /flags/?side=…&kind=device_gap. */
export const SIDE_PARAM = "side";
export const KIND_PARAM = "kind";

const NO_FILTER: FlagFilter = { side: null, kind: null };

export function FlagsScreen() {
  const t = useTranslations("flags");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  const [asked, choose] = useTabInAddress();
  const open: FlagState = asked === "closed" ? "closed" : "waiting";
  // The filter, in the address beside the tab, so going to a flag and back finds the list as it was left.
  const [sideAsked, chooseSide] = useWordInAddress(SIDE_PARAM);
  const [kindAsked, chooseKind] = useWordInAddress(KIND_PARAM);
  const filter = who.data
    ? filterFrom(who.data, sideAsked, kindAsked)
    : NO_FILTER;
  const [filtering, setFiltering] = useState(false);
  // Chuja's button: Onyesha zote goes with the filter it clears, so the keyboard goes back to where filtering starts.
  const filterButton = useRef<HTMLButtonElement>(null);
  const filterWords = useFilterWords(who.data)(filter);
  const keepTo = (next: FlagFilter) => {
    chooseSide(next.side);
    chooseKind(next.kind);
  };
  // Both lists asked here, in the part always on the page, and handed down as values: never by the part that shows one,
  // which would ask again at each mount on a failed read (frontend rules). What waits is asked whatever tab is open, as
  // its tab counts it; what is closed, once its tab is.
  const here = who.data !== undefined;
  const waiting = useFlags("waiting", filter, here);
  const closed = useFlags("closed", filter, here && open === "closed");
  const lists = { waiting, closed };
  // Until the open tab's first answer: "Subiri kidogo…", never a title with nothing under it. The line is on the page
  // from the start and only its words change, as one that comes with its words in it often goes unsaid
  // (offline-banner.tsx). A list is asked only once the page knows who is here, so it is waited for only then.
  const isWaiting = who.isPending || (here && lists[open].isPending);
  const count = waiting.data?.pages[0]?.waiting;

  const label = {
    waiting:
      count === undefined
        ? t("tabs.waiting")
        : t("tabs.waitingCount", { count }),
    closed: t("tabs.closed"),
  };

  return (
    <div className="grid max-w-2xl gap-6">
      <PageHeader
        title={t("title")}
        intro={t("intro")}
        // As soon as the page knows who is here, as it says which sides may be chosen. The second kind: the list is the
        // page's work, and this only narrows it.
        action={
          who.data ? (
            <Button
              ref={filterButton}
              kind="second"
              size="normal"
              onClick={() => setFiltering(true)}
            >
              {t("filter.title")}
            </Button>
          ) : undefined
        }
      />
      <p role="status" className={isWaiting ? "text-lg" : "sr-only"}>
        {isWaiting ? loginWords("waiting") : null}
      </p>
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {/* What the list is kept to, so a short list, or an empty one, is never read as the whole of it; and the one way
          back to all of it, a tap away. */}
      {filterWords === null ? null : (
        <div className="flex flex-wrap items-center gap-3">
          <p>{t("filter.on", { what: filterWords })}</p>
          <Button
            kind="second"
            size="normal"
            onClick={() => {
              keepTo(NO_FILTER);
              filterButton.current?.focus();
            }}
          >
            {t("filter.clear")}
          </Button>
        </div>
      )}
      {who.data && filtering ? (
        <FlagFilterSheet
          me={who.data}
          filter={filter}
          onShow={(next) => {
            keepTo(next);
            setFiltering(false);
          }}
          onClose={() => setFiltering(false)}
        />
      ) : null}
      {who.data ? (
        <Tabs
          label={t("title")}
          value={open}
          onChange={choose}
          sections={FLAG_STATES.map((state) => ({
            value: state,
            label: label[state],
            content: (
              <FlagList
                none={t(
                  filterWords === null ? `none.${state}` : "none.filtered",
                )}
                timezone={who.data.shop.timezone}
                flags={lists[state].data?.pages.flatMap((page) => page.results)}
                error={
                  lists[state].isFetchNextPageError ? null : lists[state].error
                }
                moreError={
                  lists[state].isFetchNextPageError ? lists[state].error : null
                }
                hasMore={lists[state].hasNextPage}
                loadingMore={lists[state].isFetchingNextPage}
                showMore={() => void lists[state].fetchNextPage()}
              />
            ),
          }))}
        />
      ) : null}
    </div>
  );
}

/** One tab's flags: a line each, and Onyesha zaidi while there are more. */
function FlagList({
  none,
  timezone,
  flags,
  error,
  moreError,
  hasMore,
  loadingMore,
  showMore,
}: {
  /** What an empty list says: of everything, or, under a filter, only of what was asked for. */
  none: string;
  timezone: string;
  flags: FlagLine[] | undefined;
  error: Error | null;
  /** Why Onyesha zaidi brought nothing: said beside the button, where the person is, not above fifty lines. */
  moreError: Error | null;
  hasMore: boolean;
  loadingMore: boolean;
  showMore: () => void;
}) {
  const t = useTranslations("flags");
  const list = useRef<HTMLUListElement>(null);
  // The line to move to once more lines come: the first new one. The button that asked may be gone by then, with the
  // keyboard's place, and a screen reader would be left at the top of the page.
  const firstNew = useRef<number | null>(null);
  const shown = flags?.length ?? 0;
  useEffect(() => {
    if (firstNew.current === null) return;
    if (shown > firstNew.current) {
      list.current?.querySelectorAll("a")[firstNew.current]?.focus();
      firstNew.current = null;
    } else if (moreError !== null) {
      // Refused: no line of that press will come. Kept, the keyboard would jump to a line the next time the list grew by
      // itself, wherever the person had gone by then (CTRL-4's review).
      firstNew.current = null;
    }
  }, [shown, moreError]);

  return (
    <div className="grid gap-4">
      {/* A failed read shows above the lines, not in their place: a refresh that fails keeps those last read, with the
          reason above them, as on Wafanyakazi. A first read refused shows the reason alone. */}
      <ApiErrorAlert error={error} />
      {flags === undefined ? null : flags.length === 0 ? (
        <p>{none}</p>
      ) : (
        <Card className="py-0">
          {/* A list, so a screen reader says how many lines there are. role="list" written out: Safari with VoiceOver
              stops calling a <ul> a list once its bullets are styled away, as Tailwind does. */}
          <ul ref={list} role="list" className="divide-y divide-border">
            {flags.map((flag) => (
              // relative: the kind's link stretches over its whole line.
              <li key={flag.id} className="relative grid gap-1 px-4 py-3">
                <Line flag={flag} timezone={timezone} />
              </li>
            ))}
          </ul>
        </Card>
      )}
      {hasMore ? (
        <div>
          <Button
            kind="second"
            size="normal"
            disabled={loadingMore}
            onClick={() => {
              firstNew.current = shown;
              showMore();
            }}
          >
            {t("more")}
          </Button>
        </div>
      ) : null}
      <ApiErrorAlert error={moreError} />
    </div>
  );
}

/** "Saa yake haiaminiki", then "Neema · Duka zima · Jumatatu 23/11". */
function Line({ flag, timezone }: { flag: FlagLine; timezone: string }) {
  const t = useTranslations("flags");
  const kindWords = useKindWords();
  const names = useNames();
  const day = useDayWords(timezone);
  const id = useId();
  const where = flag.side ?? t("wholeShop");
  // The day its record was made, as the flag's own page says it; for one about something no laptop made, the day the
  // server found it.
  const when = day(flag.made_at ?? flag.raised_at);
  // Who it names; naming nobody, as a laptop's missing records do, the laptop.
  const who = flag.people.length > 0 ? names(flag.people) : flag.device;
  return (
    <>
      <p id={`${id}kind`}>
        {/* The whole line opens the flag, an empty box laid over it (after:absolute), so a finger anywhere on it works.
            Named by both rows: many flags share a kind, and a screen reader's list of links would say the same words
            again and again. */}
        <TextLink
          href={flagPage(flag.id)}
          aria-labelledby={`${id}kind ${id}details`}
          className="after:absolute after:inset-0"
        >
          {kindWords(flag.kind)}
        </TextLink>
      </p>
      <p id={`${id}details`}>
        {who === null
          ? t("detailsNobody", { where, when })
          : t("details", { who, where, when })}
      </p>
      {/* What became of it, once something did: explained but waiting, or how it was closed. */}
      {flag.status === "open" ? null : (
        <p className="text-muted-foreground">{t(`status.${flag.status}`)}</p>
      )}
    </>
  );
}
