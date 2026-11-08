// page.tsx — /design: every colour, both fonts and every piece of the shop's look, on one page (UI-8).
//
// It is where the look is checked by eye: jsdom paints nothing, so the tests can only do sums on class
// names, and this page shows what they mean. Each piece is shown at rest, switched off, and with an
// error where it can have one. Hover, press and focus are tried live, with the mouse, a click and Tab,
// as no page can hold a button "hovered" without code that only this page would use.
//
// Like /spike/slip, it is part of the built app, so the demo shows it too. It reads no data and sends
// nothing, so it is neither a counter nor an office screen (.claude/rules/frontend.md).
//
// "use client": every page in this app is a client component (ADR-0016), and this one reads each
// colour's value from the browser.
"use client";

import { type ReactNode, useState, useSyncExternalStore } from "react";
import { useTranslations } from "use-intl";

import { Alert, AlertDescription, AlertTitle } from "@/components/design/alert";
import {
  Button,
  BUTTON_SIZES,
  ButtonLink,
  SCREEN_BUTTON_KINDS,
} from "@/components/design/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/design/card";
import { Choice } from "@/components/design/choice";
import { Field } from "@/components/design/field";
import { PasswordField } from "@/components/design/password-field";
import { Input } from "@/components/design/input";
import { SIDE_BAND_LOOKS } from "@/components/design/side-band";
import { ON_GREEN, TopBar } from "@/components/design/top-bar";
import { LanguageButton } from "@/components/language-button";
import { OfflineBanner } from "@/components/offline-banner";
import { cn } from "@/lib/utils";

// Every colour token in globals.css, with the key of the words that say what it is for, in the
// book's design.colours part. page.test.tsx fails if a token there has no swatch here. The token's
// name is code, not screen text, so it isn't translated.
// Not exported: Next.js allows a page file only the exports it knows (the page, its metadata).
const COLOURS = [
  ["--primary", "primary"],
  ["--primary-foreground", "primaryForeground"],
  ["--secondary", "secondary"],
  ["--secondary-foreground", "secondaryForeground"],
  ["--ring", "ring"],
  ["--background", "background"],
  ["--foreground", "foreground"],
  ["--card", "card"],
  ["--card-foreground", "cardForeground"],
  ["--popover", "popover"],
  ["--popover-foreground", "popoverForeground"],
  ["--muted", "muted"],
  ["--muted-foreground", "mutedForeground"],
  ["--accent", "accent"],
  ["--accent-foreground", "accentForeground"],
  ["--destructive", "destructive"],
  ["--border", "border"],
  ["--input", "input"],
] as const;

/** A choice that keeps its pick, as a form does, so it can be tried here by hand: tap, arrows, Tab. */
function ChoiceSample(props: {
  hint?: string;
  error?: string;
  disabled?: boolean;
}) {
  const t = useTranslations("design");
  const [side, setSide] = useState<string | null>(null);
  return (
    <Choice
      label={t("choices.label")}
      // The sample sides the top bars name below.
      options={[
        { value: "blue", label: t("topBar.sampleSides.blue") },
        { value: "striped", label: t("topBar.sampleSides.striped") },
      ]}
      value={side}
      onValueChange={setSide}
      {...props}
    />
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-4">
      <h2 className="text-2xl font-semibold">{title}</h2>
      {children}
    </section>
  );
}

// A token's colour never changes while the page is open, so there is nothing to listen to.
const noChanges = () => () => {};

function Swatch({ token, use }: { token: string; use: string }) {
  // The value the browser really has: proof that the token reached it. useSyncExternalStore is React's
  // way to read something from outside React. The build has no browser, so the page is built with ""
  // (the last argument) and shows the value once it opens. jsdom applies no stylesheet: "" there too.
  const value = useSyncExternalStore(
    noChanges,
    () =>
      getComputedStyle(document.documentElement).getPropertyValue(token).trim(),
    () => "",
  );

  return (
    <li data-token={token} className="flex items-center gap-3">
      {/* A border on every swatch, as the white ones would vanish on the white screen. */}
      <span
        className="size-12 shrink-0 rounded-lg border border-input"
        style={{ background: `var(${token})` }}
      />
      <span className="grid">
        <code className="text-sm">{token}</code>
        <span>{use}</span>
        {value ? (
          <code className="text-sm text-muted-foreground">{value}</code>
        ) : null}
      </span>
    </li>
  );
}

export default function DesignPage() {
  // The words come from the open book, Swahili or English (ADR-0040).
  const t = useTranslations("design");

  return (
    <main className="mx-auto grid max-w-4xl gap-12 p-6">
      <header className="grid gap-2">
        <h1 className="text-4xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </header>

      <Section title={t("colours.title")}>
        <ul className="grid gap-4 sm:grid-cols-2">
          {COLOURS.map(([token, use]) => (
            <Swatch key={token} token={token} use={t(`colours.${use}`)} />
          ))}
        </ul>
      </Section>

      <Section title={t("fonts.title")}>
        {/* data-font changes the font only where font-sans is on the same element: <html> works out
            the font once and passes the result down (UI-7). So each sample has both. */}
        {(["default", "second"] as const).map((font) => (
          <div
            key={font}
            data-font={font}
            className="grid gap-1 rounded-lg border p-4 font-sans"
          >
            <p className="text-sm text-muted-foreground">
              {t(`fonts.${font}`)}
            </p>
            <p className="text-2xl">{t("fonts.sample")}</p>
            {/* Same-width digits: the two amounts line up, digit under digit. */}
            <p className="text-2xl">{t("fonts.digits")}</p>
          </div>
        ))}
      </Section>

      <Section title={t("buttons.title")}>
        {BUTTON_SIZES.map((size) => (
          <div key={size} className="grid gap-2">
            <p className="text-sm text-muted-foreground">
              {t(`buttons.${size}`)}
            </p>
            <div className="flex flex-wrap gap-3">
              {SCREEN_BUTTON_KINDS.map((kind) => (
                <Button key={kind} kind={kind} size={size}>
                  {t(`buttons.${kind}`)}
                </Button>
              ))}
            </div>
          </div>
        ))}
        <div className="grid gap-2">
          <p className="text-sm text-muted-foreground">
            {t("buttons.disabled")}
          </p>
          <div className="flex flex-wrap gap-3">
            {SCREEN_BUTTON_KINDS.map((kind) => (
              <Button key={kind} kind={kind} disabled>
                {t(`buttons.${kind}`)}
              </Button>
            ))}
          </div>
        </div>
        {/* The same buttons on a pale panel, where the hover tints were the hardest to keep readable. */}
        <div className="flex flex-wrap gap-3 rounded-lg bg-muted p-4">
          {SCREEN_BUTTON_KINDS.map((kind) => (
            <Button key={kind} kind={kind}>
              {t(`buttons.${kind}`)}
            </Button>
          ))}
        </div>
        {/* The link that looks like a button (ButtonLink), in each screen kind: a step to another page,
            like Sajili kifaa hiki on the home page (UI-3). These lead back here, as a sample has nowhere
            else to go. */}
        <div className="grid gap-2">
          <p className="text-sm text-muted-foreground">{t("buttons.links")}</p>
          <div className="flex flex-wrap gap-3">
            {SCREEN_BUTTON_KINDS.map((kind) => (
              <ButtonLink key={kind} kind={kind} href="/design/">
                {t("buttons.link")}
              </ButtonLink>
            ))}
          </div>
        </div>
        {/* The bar kind, on a strip of the top bar's green, in both sizes and switched off. ON_GREEN
            sets --ring to white, as on the top bar, so Tab shows a white ring here too. */}
        <div className="grid gap-2">
          <p className="text-sm text-muted-foreground">{t("buttons.onBar")}</p>
          <div
            className={cn(
              "flex flex-wrap items-center gap-3 rounded-lg p-4",
              ON_GREEN,
            )}
          >
            {BUTTON_SIZES.map((size) => (
              <Button key={size} kind="bar" size={size}>
                {t("buttons.bar")}
              </Button>
            ))}
            <Button kind="bar" size="normal" disabled>
              {t("buttons.bar")}
            </Button>
          </div>
        </div>
      </Section>

      <Section title={t("fields.title")}>
        <div className="grid max-w-md gap-6">
          <Field label={t("fields.name")} hint={t("fields.nameHint")} />
          <Field
            label={t("fields.phone")}
            error={t("fields.phoneError")}
            inputMode="tel"
          />
          <Field
            label={t("fields.kilo")}
            hint={t("fields.disabled")}
            disabled
          />
          <Field label={t("fields.normal")} size="normal" />
          {/* A password box: its eye shows and hides what is typed (UI-5). */}
          <PasswordField label={t("fields.password")} />
          {/* A box with no visible label, like a search box: it still has a name for screen readers. */}
          <Input
            aria-label={t("fields.search")}
            placeholder={t("fields.search")}
            type="search"
          />
        </div>
      </Section>

      <Section title={t("choices.title")}>
        <div className="grid max-w-md gap-6">
          <ChoiceSample hint={t("choices.hint")} />
          <ChoiceSample error={t("choices.error")} />
          <ChoiceSample hint={t("choices.disabled")} disabled />
        </div>
      </Section>

      <Section title={t("cards.title")}>
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle>{t("cards.cardTitle")}</CardTitle>
            <CardDescription>{t("cards.cardDescription")}</CardDescription>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">
            {t("cards.cardContent")}
          </CardContent>
          <CardFooter>{t("cards.cardFooter")}</CardFooter>
        </Card>
      </Section>

      <Section title={t("alerts.title")}>
        <div className="grid max-w-xl gap-4">
          <Alert kind="info">
            <AlertTitle>{t("alerts.infoTitle")}</AlertTitle>
            <AlertDescription>{t("alerts.infoDescription")}</AlertDescription>
          </Alert>
          <Alert kind="danger">
            <AlertTitle>{t("alerts.dangerTitle")}</AlertTitle>
            <AlertDescription>{t("alerts.dangerDescription")}</AlertDescription>
          </Alert>
          {/* The office screens' real banner, following this browser's network: switch the network
              off in the browser's tools and it appears here, as on an office screen (UI-1). */}
          <p className="text-sm text-muted-foreground">{t("alerts.live")}</p>
          <OfflineBanner />
        </div>
      </Section>

      <Section title={t("topBar.title")}>
        {/* The top bar as every counter and office screen shows it, with each look of the side band
            under it. The shop and side names are samples: which side gets which look is still open
            (04 §20, item 19). The language button is the real one: pressing it switches the app. */}
        {SIDE_BAND_LOOKS.map((look) => (
          <div key={look} className="grid gap-2">
            <p className="text-sm text-muted-foreground">
              {t(`sideBands.${look}`)}
            </p>
            <div className="overflow-hidden rounded-lg border">
              <TopBar
                shop={t("topBar.sampleShop")}
                side={{ name: t(`topBar.sampleSides.${look}`), band: look }}
                actions={<LanguageButton />}
              />
              <div className="h-10" />
            </div>
          </div>
        ))}
      </Section>
    </main>
  );
}
