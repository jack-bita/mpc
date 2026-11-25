// advances.spec.ts — Advansi on the demo, end to end (WAGE-8): Meneja reads Asha's pay of this month on Mishahara, types
// 5,000 given to her today in the sheet, and finds her pay 5,000 less, with Advansi among its lines; then crosses it out
// on its own page with the demo's ready reason, where it stays, struck through, and her pay is as it was. Through the real
// server: the routes of advances, the pay's sum, the sheets and the pages.
//
// Each amount is read before and after, as the owner would compare them, and only the 5,000 is the test's own: the seed's
// two advances (backend/apps/demo/services.py) may fall in this month or the last, and other tests decide Asha's days.
// An advance is taken on any day, Sundays too, so the test runs on any day; on a 1st that is a Sunday Asha isn't on
// Mishahara before it, and is for it. It ends with the totals as it found them, as the tests share one database
// (the-shop.ts).
import type { Page } from "@playwright/test";

import sw from "../messages/sw.json";

import {
  ASHA,
  expect,
  MANAGER_EMAIL,
  MANAGER_PASSWORD,
  test,
  words,
} from "./the-shop";

const ADVANCES = sw.advances;
const PAY = sw.pay;

/** What the test gives Asha. Whole shillings, so a plain number is exact here, in a test's own sum. */
const GIVEN = 5_000;

/** An amount as the page writes it, as a number: "TSh 152,000" → 152000, "− 2,000" → −2000. */
function amount(text: string): number {
  const figures = Number(text.replace(/[^\d]/g, ""));
  return /[−-]/.test(text) ? -figures : figures;
}

/** Asha's total on Mishahara, or none when she isn't listed. Read after the month shows. */
async function ashasPay(phone: Page): Promise<number> {
  const line = phone
    .getByRole("list", { name: PAY.workersLabel })
    .getByRole("listitem")
    .filter({
      has: phone.getByRole("link", { name: ASHA.name, exact: true }),
    });
  return (await line.count()) === 0
    ? 0
    : amount(await line.locator("p").nth(1).innerText());
}

/** The month's total on Advansi, or none when it has no advance. Read after the month shows. */
async function given(phone: Page): Promise<number> {
  const total = phone
    .locator("p")
    .filter({ hasText: new RegExp(`^${ADVANCES.total} `) });
  return (await total.count()) === 0 ? 0 : amount(await total.innerText());
}

test("Meneja types an advance on the demo, and Asha's pay drops until it is crossed out", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();
  const payList = phone.getByRole("list", { name: PAY.workersLabel });
  const advances = phone.getByRole("list", { name: ADVANCES.rowsLabel });
  const back = () =>
    phone.getByRole("button", { name: sw.pageHeader.back }).click();

  /** One of the office home's pages, from the home, once its month shows. */
  const open = async (title: string, shown: string) => {
    await phone.getByRole("link", { name: title, exact: true }).click();
    await expect(
      phone.getByRole("heading", { name: title, level: 1 }),
    ).toBeVisible();
    await expect(
      (title === PAY.title ? payList : advances)
        .or(phone.getByText(shown, { exact: true }))
        .first(),
    ).toBeVisible();
  };

  const before =
    await test.step("Meneja logs in on the phone and reads Asha's pay on Mishahara", async () => {
      await phone.goto("/login/");
      await phone.getByLabel(sw.login.password.name).fill(MANAGER_EMAIL);
      // exact: the eye beside the box is labelled "Onyesha nenosiri", which holds the word too (the-shop.ts).
      await phone
        .getByLabel(sw.login.password.password, { exact: true })
        .fill(MANAGER_PASSWORD);
      await phone
        .getByRole("button", { name: sw.login.password.send, exact: true })
        .click();
      await open(PAY.title, PAY.nothingOverYet);
      const pay = await ashasPay(phone);
      await back();
      return pay;
    });

  const givenBefore =
    await test.step("Andika advansi types 5,000 given to her today", async () => {
      await open(ADVANCES.title, ADVANCES.none);
      const total = await given(phone);
      await phone
        .getByRole("button", { name: ADVANCES.record.title, exact: true })
        .click();
      const sheet = phone.getByRole("dialog", { name: ADVANCES.record.title });
      // Meneja himself isn't on the list: nobody types their own (Jack: A).
      await expect(sheet.getByRole("radio", { name: "Meneja" })).toHaveCount(0);
      await sheet.getByRole("radio", { name: ASHA.name, exact: true }).click();
      await sheet
        .getByLabel(ADVANCES.record.amount, { exact: true })
        .fill("5,000");
      await sheet
        .getByRole("button", { name: ADVANCES.record.save, exact: true })
        .click();
      await expect(sheet).toBeHidden();
      await expect(
        phone.getByText(/^Imeandikwa: TSh\s5,000, Asha, /),
      ).toBeVisible();
      await expect.poll(() => given(phone)).toBe(total + GIVEN);
      return total;
    });

  await test.step("her pay on Mishahara is 5,000 less, with Advansi among its lines", async () => {
    await back();
    await open(PAY.title, PAY.nothingOverYet);
    await expect.poll(() => ashasPay(phone)).toBe(before - GIVEN);
    await payList.getByRole("link", { name: ASHA.name, exact: true }).click();
    const line = phone
      .getByRole("table", { name: PAY.linesCaption })
      .getByRole("row")
      .filter({
        has: phone.getByRole("rowheader", { name: PAY.advances, exact: true }),
      });
    await expect(line).toHaveCount(1);
    // What this month gave her, the test's own among it.
    expect(
      amount(await line.getByRole("cell").last().innerText()),
    ).toBeLessThanOrEqual(-GIVEN);
    await back();
    await back();
  });

  await test.step("its own page crosses it out with the ready reason, and it stays, struck through", async () => {
    await open(ADVANCES.title, ADVANCES.none);
    // Newest first: today's, typed last.
    await advances.getByRole("listitem").first().getByRole("link").click();
    await expect(
      phone.getByRole("heading", {
        name: words(ADVANCES.page.title, { name: ASHA.name }),
        level: 1,
      }),
    ).toBeVisible();
    await phone
      .getByRole("button", { name: ADVANCES.void.action, exact: true })
      .click();
    const sheet = phone.getByRole("dialog", { name: /^Batilisha TSh\s5,000$/ });
    await sheet
      .getByRole("radio", {
        name: ADVANCES.readyReason.wrong_amount,
        exact: true,
      })
      .click();
    await sheet
      .getByRole("button", { name: ADVANCES.void.action, exact: true })
      .click();
    await expect(sheet).toBeHidden();
    await expect(
      phone.getByText(
        words(ADVANCES.page.reason, {
          reason: ADVANCES.readyReason.wrong_amount,
        }),
        { exact: true },
      ),
    ).toBeVisible();
    // Never brought back: no button is left on it.
    await expect(
      phone.getByRole("button", { name: ADVANCES.void.action, exact: true }),
    ).toHaveCount(0);
  });

  await test.step("the list and her pay are as they were, the crossed-out one still there", async () => {
    await back();
    await expect.poll(() => given(phone)).toBe(givenBefore);
    await expect(
      advances.getByRole("listitem").first().getByText(ADVANCES.voided, {
        exact: true,
      }),
    ).toBeVisible();
    await back();
    await open(PAY.title, PAY.nothingOverYet);
    await expect.poll(() => ashasPay(phone)).toBe(before);
  });
});
