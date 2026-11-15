// rule-history.tsx — one line of a rule's history, newest first, under its form or on its own (SHOP-5): every
// row ever set, who set it and when, its note, and at the end the rule's default. The row in use now is marked
// Inatumika sasa, and any set to start later Inakuja, by the same rule as the server's get_setting (rules.ts).
//
// Nothing here is ever changed or taken away: a rule's rows are only added to (ADR-0013), so the history is the
// whole story of the rule, and a fix shows as a newer row, as the owner made it.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

import { formatDate, formatDay } from "@/lib/format";
import { cn } from "@/lib/utils";

import { type RuleLine, rowInForce, rowsToCome } from "./rules";
import { type SettingKey, useRuleWords } from "./setting-words";

export function RuleHistory({
  ruleKey,
  line,
  today,
  timezone,
}: {
  ruleKey: SettingKey;
  line: RuleLine;
  today: string;
  /** The shop's zone, for the day each row was written on. */
  timezone: string;
}) {
  const t = useTranslations("shopSettings.past");
  const words = useRuleWords();
  const shown = (value: string) => words.shown(ruleKey, line.kind, value);
  const inForce = rowInForce(line, today);
  const coming = new Set(rowsToCome(line, today).map((row) => row.id));

  return (
    <div className="grid gap-3">
      {/* Under the card's title (a level 3 heading), so a screen reader finds it the same way. */}
      <h4 className="text-lg font-semibold">{t("title")}</h4>
      <ul role="list" className="grid gap-3">
        {/* Newest first, as the server sends them. */}
        {line.rows.map((row) => (
          <li key={row.id} className="grid gap-1">
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span>
                {t("row", {
                  value: shown(row.value),
                  date: formatDay(row.effective_from),
                })}
              </span>
              {row.id === inForce?.id ? (
                <Mark>{t("inUse")}</Mark>
              ) : coming.has(row.id) ? (
                <Mark coming>{t("coming")}</Mark>
              ) : null}
            </p>
            <p className="text-muted-foreground">
              {row.set_by === null
                ? t("bySystem", { date: formatDate(row.created_at, timezone) })
                : t("by", {
                    name: row.set_by,
                    date: formatDate(row.created_at, timezone),
                  })}
            </p>
            {/* A side's line may hold a row of the whole shop, which only code that skips the form could
                write: it says so, so the page never hides why a value is so (SHOP-3). */}
            {line.side !== null && row.side === null ? (
              <p className="text-muted-foreground">{t("wholeShop")}</p>
            ) : null}
            {row.note === "" ? null : (
              <p className="text-muted-foreground">
                {t("note", { note: row.note })}
              </p>
            )}
          </li>
        ))}
        {/* The default last, as it is older than any row: in use until the first row's day comes. */}
        <li className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span>{t("default", { value: shown(line.default) })}</span>
          {inForce === null ? <Mark>{t("inUse")}</Mark> : null}
        </li>
      </ul>
    </div>
  );
}

/** A small mark beside a row: filled green for the one in use now, outlined for one still to come. In words
 * too, so it doesn't lean on the colour alone. */
function Mark({
  coming = false,
  children,
}: {
  coming?: boolean;
  children: string;
}) {
  return (
    <span
      className={cn(
        "rounded-md border border-primary px-2 text-sm font-semibold",
        coming ? "text-primary" : "bg-primary text-primary-foreground",
      )}
    >
      {children}
    </span>
  );
}
