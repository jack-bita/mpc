// flag-filter.tsx — Chuja: Tofauti kept to one side, or to the whole shop's own, and to one kind, in a sheet over the list
// (CTRL-4), as nothing opens in place on the page (Jack, 24 Nov 2026):
//
//   ┌──────────────────────────────────┐
//   │ Chuja                            │
//   │ Upande                           │
//   │ (•) Pande zote                   │
//   │ ( ) Dawa                         │
//   │ ( ) Vyakula                      │
//   │ ( ) Duka zima                    │
//   │ Aina                             │
//   │ (•) Aina zote                    │
//   │ ( ) Saa yake haiaminiki  ...     │
//   │ [ Ghairi ]           [ Onyesha ] │
//   └──────────────────────────────────┘
//
// It offers only the sides whose flags the person may close; someone of one side alone, and not the whole shop, has none
// to choose between, so only the kinds show. The screen keeps the filter, in its address, and this sheet only picks one:
// Ghairi leaves the list as it was.
//
// "use client": it asks use-intl for words (use-client.test.ts), and keeps what is picked.
"use client";

import { useState } from "react";
import { useTranslations } from "use-intl";

import { Choice } from "@/components/design/choice";
import { Sheet } from "@/components/design/sheet";
import type { WhoIsHere } from "@/features/people/who-is-here";

import {
  type FlagFilter,
  RAISED_KINDS,
  type RaisedKind,
  sidesToFilter,
  useKindWords,
  WHOLE_SHOP,
} from "./flags";

/** The row for no filter at all: a radio's value, so never a side's id nor a kind's. */
const EVERY = "every";

export function FlagFilterSheet({
  me,
  filter,
  onShow,
  onClose,
}: {
  me: WhoIsHere;
  /** The filter now on, picked as the sheet opens. */
  filter: FlagFilter;
  /** Onyesha: the list kept to this. */
  onShow: (filter: FlagFilter) => void;
  onClose: () => void;
}) {
  const t = useTranslations("flags.filter");
  const flags = useTranslations("flags");
  const kindWords = useKindWords();
  const [side, setSide] = useState(filter.side ?? EVERY);
  const [kind, setKind] = useState<string>(filter.kind ?? EVERY);
  const { sides, wholeShop } = sidesToFilter(me);
  const choices = [
    ...sides.map((each) => ({ value: each.id, label: each.name })),
    ...(wholeShop ? [{ value: WHOLE_SHOP, label: flags("wholeShop") }] : []),
  ];

  return (
    <Sheet
      open
      onClose={onClose}
      title={t("title")}
      actionLabel={t("show")}
      onAction={() =>
        onShow({
          side: side === EVERY ? null : side,
          kind: kind === EVERY ? null : (kind as RaisedKind),
        })
      }
    >
      {choices.length > 1 ? (
        <Choice
          label={t("side")}
          options={[{ value: EVERY, label: t("everySide") }, ...choices]}
          value={side}
          onValueChange={setSide}
        />
      ) : null}
      <Choice
        label={t("kind")}
        options={[
          { value: EVERY, label: t("everyKind") },
          ...RAISED_KINDS.map((each) => ({
            value: each,
            label: kindWords(each),
          })),
        ]}
        value={kind}
        onValueChange={setKind}
      />
    </Sheet>
  );
}

/** What the filter keeps the list to, in words, "Dawa · Saa yake haiaminiki", or null for nothing. */
export function useFilterWords(me: WhoIsHere | undefined) {
  const t = useTranslations("flags");
  const kindWords = useKindWords();
  return (filter: FlagFilter): string | null => {
    const side =
      filter.side === WHOLE_SHOP
        ? t("wholeShop")
        : me?.permissions.sides.find((each) => each.id === filter.side)?.name;
    const kind = filter.kind === null ? undefined : kindWords(filter.kind);
    if (side === undefined) return kind ?? null;
    return kind === undefined ? side : t("filter.both", { side, kind });
  };
}
