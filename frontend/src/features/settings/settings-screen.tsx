// settings-screen.tsx — Mipangilio ya duka, the shop's rules on one page (SHOP-5, 03 §5.8): every rule of the
// registry, grouped by its area, with its value today and any value still to come. A side's rule has a line
// for each side, as it is set one side at a time (SHOP-3): Dawa's tolerance and Vyakula's are two values.
//
// An office screen: it asks the server through the store of server answers (rule 5), GET
// /api/v1/shops/settings/, and needs the internet, which the office area says while it is gone. Anyone who
// works on a side may read the rules: every one already travels to every laptop of the shop (SYNC-2), so the
// page hides nothing a counter doesn't hold. The server keeps the lines to the sides the person sees.
//
// One line per side, under the rule, not a column per side as the card first said: on the owner's phone two
// columns of values and buttons don't fit (Jack, 15 Nov 2026).
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/design/card";
import { useWhoIsHere, type WhoIsHere } from "@/features/people/who-is-here";
import { formatDay } from "@/lib/format";

import {
  type RuleLine,
  type RuleOnPage,
  rowsToCome,
  rulesByArea,
} from "./rules";
import { useRuleWords } from "./setting-words";

/** The rules' place in the store of server answers. */
export const SHOP_RULES = ["shops", "settings"] as const;

/** Every rule, with its value today and its rows, as the server answers. */
export function useShopRules() {
  return useQuery({
    queryKey: SHOP_RULES,
    queryFn: () => answerOf(api.GET("/api/v1/shops/settings/")),
  });
}

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
      {who.data ? <RulesByArea me={who.data} /> : null}
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
                <RuleCard rule={rule} today={today} sideNames={sideNames} />
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
  sideNames,
}: {
  rule: RuleOnPage;
  today: string;
  sideNames: ReadonlyMap<string, string>;
}) {
  const words = useRuleWords();
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
      <CardContent className="grid gap-4">
        {rule.lines.map((line) => (
          <LineOfRule
            key={line.side ?? "shop"}
            rule={rule}
            line={line}
            today={today}
            side={line.side === null ? null : (sideNames.get(line.side) ?? "")}
          />
        ))}
      </CardContent>
    </Card>
  );
}

/** One line of a rule: the whole shop's, or one side's, with its value today and every value still to come. */
function LineOfRule({
  rule,
  line,
  today,
  side,
}: {
  rule: RuleOnPage;
  line: RuleLine;
  today: string;
  /** The side's name, or null on a rule of the whole shop, which needs none. */
  side: string | null;
}) {
  const t = useTranslations("shopSettings");
  const words = useRuleWords();
  const shown = (value: string) => words.shown(rule.key, line.kind, value);
  return (
    <div className="grid gap-1">
      <p className="flex flex-wrap gap-x-4 text-lg">
        {side === null ? null : <span className="font-semibold">{side}</span>}
        {/* The value today is the server's, worked out by get_setting itself, so the page and the pay run
            never disagree (rules.ts). */}
        <span>{shown(line.value)}</span>
      </p>
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
    </div>
  );
}
