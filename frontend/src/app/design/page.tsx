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

import { type ReactNode, useSyncExternalStore } from "react";
import { useTranslations } from "use-intl";

import { Alert, AlertDescription, AlertTitle } from "@/components/design/alert";
import { Button, BUTTON_KINDS, BUTTON_SIZES } from "@/components/design/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/design/card";
import { Field } from "@/components/design/field";
import { Input } from "@/components/design/input";
import { SIDE_BAND_LOOKS, SideBand } from "@/components/design/side-band";

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
  // The words come from the open book, Swahili or English (ADR-0032).
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
              {BUTTON_KINDS.map((kind) => (
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
            {BUTTON_KINDS.map((kind) => (
              <Button key={kind} kind={kind} disabled>
                {t(`buttons.${kind}`)}
              </Button>
            ))}
          </div>
        </div>
        {/* The same buttons on a pale panel, where the hover tints were the hardest to keep readable. */}
        <div className="flex flex-wrap gap-3 rounded-lg bg-muted p-4">
          {BUTTON_KINDS.map((kind) => (
            <Button key={kind} kind={kind}>
              {t(`buttons.${kind}`)}
            </Button>
          ))}
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
          {/* A box with no visible label, like a search box: it still has a name for screen readers. */}
          <Input
            aria-label={t("fields.search")}
            placeholder={t("fields.search")}
            type="search"
          />
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
        </div>
      </Section>

      <Section title={t("sideBands.title")}>
        {SIDE_BAND_LOOKS.map((look) => (
          <div key={look} className="grid gap-2">
            <p className="text-sm text-muted-foreground">
              {t(`sideBands.${look}`)}
            </p>
            {/* Under a strip of the top bar's green, as it will sit in UI-1. */}
            <div className="overflow-hidden rounded-lg border">
              <div className="h-10 bg-primary" />
              <SideBand look={look} />
              <div className="h-10" />
            </div>
          </div>
        ))}
      </Section>
    </main>
  );
}
