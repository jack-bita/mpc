// shop-settings.spec.ts — the owner changes the late fine, end to end (SHOP-5): on the manager's phone, Mipangilio
// ya duka shows today's 500; Badilisha sets 2,000 from a day to come; the page then shows 500 today and 2,000 coming,
// and the history both. The card's first Done when, through the real server: its route, its rule that a value starts
// on the shop's today or later, and its get_setting, which decides the value today.
//
// The demo's Meneja holds settings.manage on the whole shop, given by the demo seed (SHOP-5), as the demo has no
// owner. The demo's late fine is the seed's made-up 500, set by the system from the day the demo is made: a shop's
// fines start at nothing, as this public repo names no real amount (ATT-2, DEMO_RULES). The tests share one
// database (the-shop.ts): this one only adds a row from a day to come, which no other test reads.
//
// The day is read from the page itself: the date box starts at the shop's today, as the server sends it, so the
// test never leans on the clock of the machine it runs on, nor on its zone. It is the day after tomorrow, not the card's
// tomorrow: a run that crosses midnight in Dar es Salaam (21:00 UTC) between reading the box and saving would make
// tomorrow the shop's today, and the 2,000 would be in force at once, so "500 today" would fail for no fault. Two
// days on is still a day to come after one midnight (SHOP-5's review). The page's own tests keep tomorrow
// (settings-screen.test.tsx).
import sw from "../messages/sw.json";

import {
  expect,
  MANAGER_EMAIL,
  MANAGER_PASSWORD,
  test,
  words,
} from "./the-shop";

const FINE = sw.shopSettings.rules.attendance.late_fine.name;

/** The day after `day`, both as the date box writes them: "2026-11-15" → "2026-11-16". Days only, in UTC, so no
 * zone moves it. */
function dayAfter(day: string): string {
  const next = new Date(`${day}T00:00:00Z`);
  next.setUTCDate(next.getUTCDate() + 1);
  return next.toISOString().slice(0, 10);
}

/** "2026-11-16" as the page writes a day: "16/11/2026" (formatDay, src/lib/format.ts). */
function asShown(day: string): string {
  const [year, month, date] = day.split("-");
  return `${date}/${month}/${year}`;
}

test("the owner sets the late fine to 2,000 from a day to come: 500 today, 2,000 coming", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();
  // The late fine's card, by its heading.
  const fine = phone
    .locator("[data-slot=card]")
    .filter({ has: phone.getByRole("heading", { name: FINE, level: 3 }) });

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
    // The office's home page, where a password's login lands, has the new button (SHOP-5).
    await phone
      .getByRole("link", { name: sw.shopSettings.title, exact: true })
      .click();
    await expect(
      phone.getByRole("heading", { name: sw.shopSettings.title, level: 1 }),
    ).toBeVisible();
  });

  await test.step("today's late fine is 500, with nothing coming", async () => {
    await expect(fine).toContainText("TSh 500");
    await expect(fine).not.toContainText(
      sw.shopSettings.coming.split("{")[0] ?? "",
    );
  });

  const { today, coming } =
    await test.step("Badilisha: 2,000 from the day after tomorrow, and Hifadhi", async () => {
      await fine
        .getByRole("button", {
          name: words(sw.shopSettings.changeOf, { rule: FINE }),
        })
        .click();
      const day = fine.getByLabel(sw.shopSettings.form.from);
      // The shop's today, as the server sent it, and two days on (see the top of this file).
      const shopToday = await day.inputValue();
      const next = dayAfter(dayAfter(shopToday));
      // As a person types it, with the comma people write; the page sends "2000".
      await fine.getByLabel(sw.shopSettings.form.newValue.money).fill("2,000");
      await day.fill(next);
      // No note: the demo keeps none (demo.no_note), as every visitor would read it (SHOP-5's second review).
      await fine
        .getByRole("button", { name: sw.shopSettings.form.save, exact: true })
        .click();
      await expect(
        fine.getByText(words(sw.shopSettings.saved, { date: asShown(next) })),
      ).toBeVisible();
      return { today: shopToday, coming: next };
    });

  await test.step("the page shows 500 today and 2,000 coming", async () => {
    // Today's value is still the seed's 500: the new row starts on its day, still to come.
    await expect(fine).toContainText("TSh 500");
    await expect(fine).toContainText(
      words(sw.shopSettings.coming, {
        date: asShown(coming),
        value: "TSh 2,000",
      }),
    );
  });

  await test.step("the history shows both: 2,000 coming, 500 in use", async () => {
    await fine
      .getByRole("button", {
        name: words(sw.shopSettings.changeOf, { rule: FINE }),
      })
      .click();
    const lines = fine.getByRole("listitem");
    // The new row, the seed's, and the registry's default last.
    await expect(lines).toHaveCount(3);
    await expect(lines.nth(0)).toContainText(
      words(sw.shopSettings.past.row, {
        value: "TSh 2,000",
        date: asShown(coming),
      }),
    );
    await expect(lines.nth(0)).toContainText(sw.shopSettings.past.coming);
    await expect(lines.nth(1)).toContainText(
      words(sw.shopSettings.past.row, {
        value: "TSh 500",
        date: asShown(today),
      }),
    );
    await expect(lines.nth(1)).toContainText(sw.shopSettings.past.inUse);
    // The seed's row is the system's: no person of the demo set it.
    await expect(lines.nth(1)).toContainText(
      sw.shopSettings.past.bySystem.split("{")[0] ?? "",
    );
    // The default, whatever the registry holds, is no longer in use.
    await expect(lines.nth(2)).toContainText(
      sw.shopSettings.past.default.replace("{value}", ""),
    );
    await expect(lines.nth(2)).not.toContainText(sw.shopSettings.past.inUse);
  });
});
