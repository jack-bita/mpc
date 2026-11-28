// meal-money.spec.ts — Hela ya chakula on the demo, end to end (WAGE-7): Meneja opens it on his phone, chooses the three
// weeks before today in Chagua siku's sheet and reads their whole total; opens the day nobody typed, types its money, and
// sees it split among the three who came; then crosses it out with the demo's ready reason, and the day is as it was, its
// row struck through. Through the real server: the demo seed's meal money, its routes, the book of days, the sheets and
// the pages.
//
// The seed types 3,000 for each working day before today, from the 1st of last month, but one, forgotten, the fifth
// latest (backend/apps/demo/services.py, DATA-2). The three weeks before today hold 18 of them, the forgotten one
// among them, so the whole is 51,000 whatever day the test runs, and one line says Haijaandikwa. On that day all three
// came, whatever other tests decided: theirs are Asha's latest. The test ends with the total as it found it, as the
// tests share one database (the-shop.ts). No other file reads the meal money.
import sw from "../messages/sw.json";

import {
  daysAfter,
  expect,
  MANAGER_EMAIL,
  MANAGER_PASSWORD,
  test,
  words,
} from "./the-shop";

const MEALS = sw.mealMoney;

/** An amount as the page writes it: Intl puts a hard space after TSh, which a regex's \s matches. */
const money = (amount: string) => `TSh\\s${amount}`;

test("Meneja types a forgotten day's meal money on the demo, and crosses it out", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();
  const forgotten = phone
    .getByRole("listitem")
    .filter({ hasText: MEALS.notTyped });

  await test.step("Meneja logs in on the phone and opens Hela ya chakula", async () => {
    await phone.goto("/login/");
    await phone.getByLabel(sw.login.password.name).fill(MANAGER_EMAIL);
    // exact: the eye beside the box is labelled "Onyesha nenosiri", which holds the word too (the-shop.ts).
    await phone
      .getByLabel(sw.login.password.password, { exact: true })
      .fill(MANAGER_PASSWORD);
    await phone
      .getByRole("button", { name: sw.login.password.send, exact: true })
      .click();
    await phone.getByRole("link", { name: MEALS.title, exact: true }).click();
    await expect(
      phone.getByRole("heading", { name: MEALS.title, level: 1 }),
    ).toBeVisible();
  });

  await test.step("Chagua siku shows the three weeks before today, and the whole of them", async () => {
    await phone
      .getByRole("button", { name: MEALS.choose.title, exact: true })
      .click();
    const sheet = phone.getByRole("dialog", { name: MEALS.choose.title });
    // The shop's own today, which the box says is its last day: the days are counted from it, never from this machine.
    const last = sheet.getByLabel(MEALS.choose.last, { exact: true });
    const today = (await last.getAttribute("max")) ?? "";
    await sheet
      .getByLabel(MEALS.choose.first, { exact: true })
      .fill(daysAfter(today, -21));
    await last.fill(daysAfter(today, -1));
    await sheet
      .getByRole("button", { name: MEALS.choose.show, exact: true })
      .click();
    await expect(sheet).toBeHidden();
    await expect(
      phone.getByText(new RegExp(`^${MEALS.total} ${money("51,000")}$`)),
    ).toBeVisible();
    await expect(forgotten).toHaveCount(1);
  });

  await test.step("the forgotten day's own page takes its money, split among the three who came", async () => {
    await forgotten.getByRole("link").click();
    await expect(
      phone.getByText(MEALS.notTyped, { exact: true }),
    ).toBeVisible();
    await phone
      .getByRole("button", { name: MEALS.record.title, exact: true })
      .click();
    const sheet = phone.getByRole("dialog", { name: MEALS.record.title });
    await sheet.getByLabel(MEALS.record.amount, { exact: true }).fill("2,700");
    await sheet
      .getByRole("button", { name: MEALS.record.save, exact: true })
      .click();
    await expect(sheet).toBeHidden();
    await expect(
      phone.getByText(
        new RegExp(
          `^${words(MEALS.dayPage.total, { amount: money("2,700") })}$`,
        ),
      ),
    ).toBeVisible();
    await expect(
      phone.getByText(new RegExp(`^Watu 3 · ${money("900")} kila mmoja$`)),
    ).toBeVisible();
  });

  await test.step("Meneja crosses it out with the ready reason, and it stays, struck through", async () => {
    const crossOut = new RegExp(
      `^${words(MEALS.void.title, { amount: money("2,700") })}$`,
    );
    await phone.getByRole("button", { name: crossOut }).click();
    const sheet = phone.getByRole("dialog", { name: crossOut });
    await sheet
      .getByRole("radio", { name: MEALS.readyReason.wrong_amount, exact: true })
      .click();
    await sheet
      .getByRole("button", { name: MEALS.void.action, exact: true })
      .click();
    await expect(sheet).toBeHidden();
    await expect(
      phone.getByText(MEALS.notTyped, { exact: true }),
    ).toBeVisible();
    await expect(
      phone.getByText(
        words(MEALS.dayPage.reason, {
          reason: MEALS.readyReason.wrong_amount,
        }),
        { exact: true },
      ),
    ).toBeVisible();
    // Never brought back: no button is left on it.
    await expect(phone.getByRole("button", { name: crossOut })).toHaveCount(0);
  });

  await test.step("the list is as he left it, its days chosen and its total as before", async () => {
    await phone.getByRole("button", { name: sw.pageHeader.back }).click();
    await expect(
      phone.getByText(new RegExp(`^${MEALS.total} ${money("51,000")}$`)),
    ).toBeVisible();
    await expect(
      phone.getByRole("button", { name: MEALS.wholeMonth, exact: true }),
    ).toBeVisible();
    await expect(forgotten).toHaveCount(1);
  });
});
