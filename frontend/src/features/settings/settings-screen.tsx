// settings-screen.tsx — Mipangilio ya duka, the shop's rules on one page (SHOP-5, 03 §5.8): every rule of the
// registry, grouped by its area, with its value today and any value still to come. A side's rule has a line
// for each side, as it is set one side at a time (SHOP-3): Dawa's tolerance and Vyakula's are two values.
//
// An office screen: it asks the server through the store of server answers (rule 5), GET
// /api/v1/shops/settings/, and needs the internet, which the office area says while it is gone. Anyone who
// works on a side may read the rules: every one already travels to every laptop of the shop (SYNC-2), so the
// page hides nothing a counter doesn't hold. The server keeps the lines to the sides the person sees.
//
// Each line has one button. Badilisha, for someone holding settings.manage where the line's value is set (the
// whole shop for a shop's rule, the side for a side's), opens the form (setting-form.tsx) with the line's
// history under it. Everyone else gets Historia, which opens the history alone: they read the rules, and
// change none. The button only keeps a door out of sight: the server checks the key itself on every save.
//
// At the bottom, Pande: each side with its on/off switch (side-switch.tsx).
//
// One line per side, under the rule, not a column per side as the card first said: on the owner's phone two
// columns of values and buttons don't fit (Jack, 15 Nov 2026).
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/design/card";
import {
  sidesWhere,
  useWhoIsHere,
  type WhoIsHere,
} from "@/features/people/who-is-here";
import { formatDay } from "@/lib/format";

import { RuleHistory } from "./rule-history";
import {
  type RuleLine,
  type RuleOnPage,
  type RuleRow,
  rowsToCome,
  rulesByArea,
} from "./rules";
import { SettingForm } from "./setting-form";
import { useRuleWords } from "./setting-words";
import { SHOP_RULES, useShopRules } from "./shop-rules";
import { SideSwitches } from "./side-switch";

/** The key that lets a person give a rule a new value: one of the owner's own four (spec §6). */
const CHANGES_RULES = "settings.manage";

export function SettingsScreen() {
  const t = useTranslations("shopSettings");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  const rules = useShopRules();
  // Until both answer the first time: "Subiri kidogo…", never a page with a title and nothing under it. The
  // line is on the page from the start and only its words change, as one that comes with its words in it
  // often goes unsaid (offline-banner.tsx).
  const waiting =
    (who.isPending && who.failureCount === 0) ||
    (rules.isPending && rules.failureCount === 0);

  return (
    <div className="grid max-w-2xl gap-6">
      <div className="grid gap-2">
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {who.data ? (
        <>
          <RulesByArea me={who.data} />
          <SideSwitches me={who.data} />
        </>
      ) : null}
    </div>
  );
}

function RulesByArea({ me }: { me: WhoIsHere }) {
  const rules = useShopRules();
  const words = useRuleWords();
  // The sides' names, from `me`, as on Hali ya vifaa: the server sends only the lines of the sides the person
  // sees, and `me` names every one of those.
  const sideNames = new Map(
    me.permissions.sides.map((side) => [side.id, side.name]),
  );

  // A failed read shows above the rules, not in their place: a refresh that fails keeps the last answer on
  // the screen, with the reason above it, as on Vifaa.
  const failure = <ApiErrorAlert error={rules.error} />;
  if (!rules.data) return failure;
  const { today } = rules.data;
  return (
    <>
      {failure}
      {rulesByArea(rules.data.rules).map((area) => (
        // Each area a section with its own heading, so a screen reader can jump from area to area.
        <section
          key={area.area}
          aria-labelledby={`area-${area.area}`}
          className="grid gap-4"
        >
          <h2 id={`area-${area.area}`} className="text-xl font-semibold">
            {words.area(area.area)}
          </h2>
          {/* role="list" written out: Safari with VoiceOver stops calling a <ul> a list once its bullets
              are styled away, as Tailwind does (device-list.tsx). */}
          <ul role="list" className="grid gap-4">
            {area.rules.map((rule) => (
              <li key={rule.key}>
                <RuleCard
                  rule={rule}
                  today={today}
                  me={me}
                  sideNames={sideNames}
                />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </>
  );
}

function RuleCard({
  rule,
  today,
  me,
  sideNames,
}: {
  rule: RuleOnPage;
  today: string;
  me: WhoIsHere;
  sideNames: ReadonlyMap<string, string>;
}) {
  const words = useRuleWords();
  // Where the person may set a value: on the whole shop, or on each side where they hold the key. A key on the
  // whole shop counts on every side too (sidesWhere).
  const onTheShop = me.permissions.whole_shop.includes(CHANGES_RULES);
  const onSides = new Set(sidesWhere(me, CHANGES_RULES).map((side) => side.id));
  return (
    <Card>
      <CardHeader>
        {/* A heading under its area's, so a screen reader can jump from rule to rule. The card's title is
            a <div> (shadcn's), so the role says it. */}
        <CardTitle role="heading" aria-level={3}>
          {words.name(rule.key)}
        </CardTitle>
        <CardDescription>{words.help(rule.key)}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        {rule.lines.map((line) => (
          <LineOfRule
            key={line.side ?? "shop"}
            rule={rule}
            line={line}
            today={today}
            timezone={me.shop.timezone}
            side={line.side === null ? null : (sideNames.get(line.side) ?? "")}
            mayChange={line.side === null ? onTheShop : onSides.has(line.side)}
          />
        ))}
      </CardContent>
    </Card>
  );
}

/** One line of a rule: the whole shop's, or one side's, with its value today, every value still to come, and
 * its button, which opens its form and history, or its history alone, under it. */
function LineOfRule({
  rule,
  line,
  today,
  timezone,
  side,
  mayChange,
}: {
  rule: RuleOnPage;
  line: RuleLine;
  today: string;
  timezone: string;
  /** The side's name, or null on a rule of the whole shop, which needs none. */
  side: string | null;
  /** Whether the person holds settings.manage where this line's value is set. */
  mayChange: boolean;
}) {
  const t = useTranslations("shopSettings");
  const words = useRuleWords();
  const store = useQueryClient();
  const shown = (value: string) => words.shown(rule.key, line.kind, value);
  const name = words.name(rule.key);

  const [open, setOpen] = useState(false);
  // The last value this line saved, said once in its status line (below).
  const [saved, setSaved] = useState<RuleRow | null>(null);
  // Where the keyboard goes when the form closes: back to the button that opened it, as the form and the box
  // that had focus are gone. Counted, so each close moves it (devices-screen.tsx).
  const opener = useRef<HTMLButtonElement>(null);
  const [closes, setCloses] = useState(0);
  useEffect(() => {
    if (closes > 0) opener.current?.focus();
  }, [closes]);
  function close() {
    setOpen(false);
    setCloses((count) => count + 1);
  }

  // The button's name says which rule and which side, as a page of Badilisha buttons is a list of the same word
  // to a screen reader. It starts with the word on the button, so speaking "Badilisha" to a phone finds it.
  const label = mayChange
    ? side === null
      ? t("changeOf", { rule: name })
      : t("changeOfSide", { rule: name, side })
    : side === null
      ? t("historyOf", { rule: name })
      : t("historyOfSide", { rule: name, side });

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex flex-wrap gap-x-4 text-lg">
          {side === null ? null : <span className="font-semibold">{side}</span>}
          {/* The value today is the server's, worked out by get_setting itself, so the page and the pay run
              never disagree (rules.ts). */}
          <span>{shown(line.value)}</span>
        </p>
        {/* While the form is open its own Ghairi closes it, so the button steps aside; the history alone has
            nothing to cancel, so its button stays, as Funga. */}
        {open && mayChange ? null : (
          <Button
            ref={opener}
            kind="second"
            size="normal"
            aria-label={open ? undefined : label}
            aria-expanded={open}
            onClick={() => {
              if (open) close();
              else {
                setSaved(null);
                setOpen(true);
              }
            }}
          >
            {open ? t("close") : mayChange ? t("change") : t("history")}
          </Button>
        )}
      </div>
      {/* "Kuanzia 01/12/2026: TSh 2,000": a value set to start later, soonest first, so the owner sees the
          change he made is waiting for its day, not lost. */}
      {rowsToCome(line, today).map((row) => (
        <p key={row.id} className="font-medium text-primary">
          {t("coming", {
            date: formatDay(row.effective_from),
            value: shown(row.value),
          })}
        </p>
      ))}
      {/* Always on the page, empty until a save: a role="status" line is read when its words change, and one
          that appears with its words already in it may not be read at all (offline-banner.tsx). */}
      <p role="status" className={saved ? "font-medium" : "sr-only"}>
        {saved ? t("saved", { date: formatDay(saved.effective_from) }) : null}
      </p>
      {open ? (
        <div className="grid gap-6 rounded-lg border border-input p-4">
          {mayChange ? (
            <SettingForm
              ruleKey={rule.key}
              line={line}
              today={today}
              onSaved={(row) => {
                setSaved(row);
                close();
              }}
              onCancel={() => {
                close();
                // Asked again here too: a send whose answer was lost may have saved the value, and the owner
                // who gives up should still see it on the page (devices-screen.tsx).
                void store.invalidateQueries({ queryKey: SHOP_RULES });
              }}
            />
          ) : null}
          <RuleHistory
            ruleKey={rule.key}
            line={line}
            today={today}
            timezone={timezone}
          />
        </div>
      ) : null}
    </div>
  );
}
