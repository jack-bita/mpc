// closed-days.spec.ts — the owner closes the shop for a funeral, end to end (ATT-9): on the manager's phone, Siku duka
// limefungwa lists the demo's coming public holidays; Ongeza closes the shop for five days; Badilisha siku ya mwisho
// moves the last day two days earlier; Ondoa takes the closure off. The card's Done when, through the real server:
// ATT-8's routes, their rules (a closure from today on, none sharing a day with another, a reason for each change),
// and the list the server picks.
//
// The demo's Meneja holds settings.manage on the whole shop, given by the demo seed (SHOP-5), as the demo has no owner.
// The seed closes the shop on the next three of Tanzania's fixed-date public holidays (ATT-8), so the list has rows.
// The tests share one database (the-shop.ts), and no other test reads the closures.
//
// The days are read from the page itself: the Kuanzia box offers nothing before the shop's today, as the server sends
// it, so the test never leans on the clock of the machine it runs on, nor on its zone. The funeral starts 400 days on:
// after the seed's three holidays, which all fall within the next six months, so no day clashes with one; and far
// past tomorrow, as on the demo a person's change touches only days from tomorrow on (demo.closures_from_tomorrow),
// even for a run that crosses midnight in Dar es Salaam (SHOP-5's review).
import type { Locator, Page } from "@playwright/test";

import sw from "../messages/sw.json";

import {
  expect,
  MANAGER_EMAIL,
  MANAGER_PASSWORD,
  test,
  words,
} from "./the-shop";

const CLOSURES = sw.shopSettings.closures;
const FUNERAL = "Msiba wa bibi";

/** `count` days after `day`, both as the date box writes them: "2026-11-15", 5 → "2026-11-20". Days only, in UTC, so
 * no zone moves it. */
function daysAfter(day: string, count: number): string {
  const next = new Date(`${day}T00:00:00Z`);
  next.setUTCDate(next.getUTCDate() + count);
  return next.toISOString().slice(0, 10);
}

/** "2026-11-16" as the page writes a day: "16/11/2026" (formatDay, src/lib/format.ts). */
function asShown(day: string): string {
  const [year, month, date] = day.split("-");
  return `${date}/${month}/${year}`;
}

/** A span of days as the page writes it: "20/11/2026 – 24/11/2026". */
function span(first: string, last: string): string {
  return words(CLOSURES.days, { first: asShown(first), last: asShown(last) });
}

/** The section, a region named by its heading. */
function closedDays(phone: Page): Locator {
  return phone.getByRole("region", { name: CLOSURES.title });
}

test("the owner closes the shop for a funeral, moves its last day, and takes it off", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();
  const section = closedDays(phone);
  const funeral = section.getByRole("listitem").filter({ hasText: FUNERAL });
  const said = section.getByRole("status");

  await test.step("Meneja logs in on the phone and opens Mipangilio ya duka", async () => {
    await phone.goto("/login/");
    await phone.getByLabel(sw.login.password.name).fill(MANAGER_EMAIL);
    // exact: the eye beside the box is labelled "Onyesha nenosiri", which holds the word too (the-shop.ts).
    await phone
      .getByLabel(sw.login.password.password, { exact: true })
      .fill(MANAGER_PASSWORD);
    await phone
      .getByRole("button", { name: sw.login.password.send, exact: true })
      .click();
    await phone
      .getByRole("link", { name: sw.shopSettings.title, exact: true })
      .click();
    await expect(
      phone.getByRole("heading", { name: CLOSURES.title, level: 2 }),
    ).toBeVisible();
  });

  await test.step("the demo's coming public holidays are listed", async () => {
    await expect(section.getByRole("listitem").first()).toBeVisible();
    await expect(funeral).toHaveCount(0);
  });

  const { first, last } =
    await test.step("Ongeza: Msiba wa bibi, five days, and Hifadhi", async () => {
      await section
        .getByRole("button", { name: CLOSURES.add, exact: true })
        .click();
      const from = section.getByLabel(CLOSURES.form.from, { exact: true });
      // The shop's today, as the server sent it: the box offers nothing before it (see the top of this file).
      const today = await from.getAttribute("min");
      if (today === null) throw new Error("Kuanzia offers no first day");
      const start = daysAfter(today, 400);
      const end = daysAfter(start, 4);
      await from.fill(start);
      await section.getByLabel(CLOSURES.form.to, { exact: true }).fill(end);
      await section
        .getByLabel(CLOSURES.form.name, { exact: true })
        .fill(FUNERAL);
      await section
        .getByRole("button", { name: sw.shopSettings.form.save, exact: true })
        .click();
      await expect(said).toHaveText(
        words(CLOSURES.added, { name: FUNERAL, days: span(start, end) }),
      );
      return { first: start, last: end };
    });

  await test.step("the funeral shows in the list, with its five days", async () => {
    await expect(funeral).toContainText(span(first, last));
  });

  const moved =
    await test.step("Badilisha siku ya mwisho: two days earlier, with a reason", async () => {
      const earlier = daysAfter(first, 2);
      await funeral
        .getByRole("button", {
          name: words(CLOSURES.changeLastDayOf, { name: FUNERAL }),
        })
        .click();
      await funeral
        .getByLabel(CLOSURES.newLastDay, { exact: true })
        .fill(earlier);
      await funeral
        .getByLabel(CLOSURES.reason, { exact: true })
        .fill("Familia imemaliza mapema");
      await funeral
        .getByRole("button", { name: sw.shopSettings.form.save, exact: true })
        .click();
      await expect(said).toHaveText(
        words(CLOSURES.moved, { name: FUNERAL, days: span(first, earlier) }),
      );
      await expect(funeral).toContainText(span(first, earlier));
      return earlier;
    });

  await test.step("Ondoa, with a reason: the funeral leaves the list", async () => {
    await funeral
      .getByRole("button", {
        name: words(CLOSURES.removeOf, { name: FUNERAL }),
      })
      .click();
    await funeral
      .getByLabel(CLOSURES.reason, { exact: true })
      .fill("Tumeamua kufungua");
    await funeral
      .getByRole("button", { name: CLOSURES.remove, exact: true })
      .click();
    await expect(said).toHaveText(
      words(CLOSURES.removed, { name: FUNERAL, days: span(first, moved) }),
    );
    await expect(funeral).toHaveCount(0);
    // The demo's holidays stay.
    await expect(section.getByRole("listitem").first()).toBeVisible();
  });
});
