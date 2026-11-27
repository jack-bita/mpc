// corrections.spec.ts — Marekebisho on the demo, end to end (WAGE-10): Meneja, who approves pay there, opens Asha's pay
// of this month, adds + 9,000 with the demo's ready reason, finds it a line of her pay and her total 9,000 more; then taps
// the line, crosses it out with the ready reason, and finds it struck through under the lines, her total as it was.
// Through the real server: the routes of corrections, the pay's sum, the sheets and the page.
//
// Her total is read before and after, as the owner would compare them, and only the 9,000 is the test's own: other tests
// decide Asha's days and give her money. A correction goes in any month still open, so the test runs on any day; on a
// 1st that is a Sunday she has no line before it, and has one for it. It ends with her total as it found it, as the
// tests share one database (the-shop.ts). Her pay is opened from her id on Wafanyakazi, as on such a 1st Mishahara lists
// nobody yet.
import type { Page } from "@playwright/test";

import sw from "../messages/sw.json";
import { Decimal } from "../src/lib/decimal";

import {
  ASHA,
  expect,
  MANAGER_EMAIL,
  MANAGER_PASSWORD,
  test,
  words,
} from "./the-shop";

const PAY = sw.pay;
const CORRECTION = sw.pay.correction;

/** What the test adds to Asha's pay: money, so the shared Decimal, never a plain number (rule 3; the review). */
const ADDED = new Decimal("9000");

/** An amount as the page writes it, as the shared Decimal: "TSh 152,000" → 152000, "− 2,000" → −2000. */
function amount(text: string): InstanceType<typeof Decimal> {
  const figures = new Decimal(text.replace(/[^\d]/g, "") || "0");
  return /[−-]/.test(text) ? figures.neg() : figures;
}

/** Asha's total on her pay page, as text, "141000", or "0" when the page shows no lines yet: a Decimal's own writing,
 * which the test compares, never a number. Read after the page shows. */
async function total(phone: Page): Promise<string> {
  const footer = phone
    .getByRole("table", { name: PAY.linesCaption })
    .getByRole("row")
    .filter({
      has: phone.getByRole("rowheader", { name: PAY.totalToday, exact: true }),
    });
  return (await footer.count()) === 0
    ? "0"
    : amount(await footer.getByRole("cell").last().innerText()).toFixed();
}

test("Meneja adds a correction to Asha's pay on the demo, and crosses it out", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();
  const line = words(CORRECTION.line, {
    reason: CORRECTION.readyReason.dayNotCounted,
  });

  const before =
    await test.step("Meneja logs in on the phone and opens Asha's pay of this month", async () => {
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
        .getByRole("link", { name: sw.workers.title, exact: true })
        .click();
      // The list names each by nickname and full name: "Asha · Asha Mfano".
      const asha = phone.getByRole("link", {
        name: `${ASHA.name} · ${ASHA.fullName}`,
        exact: true,
      });
      const id = new URL(
        (await asha.getAttribute("href")) ?? "",
        "http://the-shop",
      ).searchParams.get("id");
      expect(id).not.toBeNull();
      await phone.goto(`/pay/worker/?staff=${id ?? ""}`);
      await expect(
        phone.getByRole("heading", { name: ASHA.name, level: 1 }),
      ).toBeVisible();
      await expect(
        phone.getByRole("button", { name: CORRECTION.button, exact: true }),
      ).toBeVisible();
      return total(phone);
    });

  await test.step("Ongeza marekebisho adds + 9,000 with the ready reason, a line of her pay", async () => {
    await phone
      .getByRole("button", { name: CORRECTION.button, exact: true })
      .click();
    const sheet = phone.getByRole("dialog", {
      name: words(CORRECTION.title, { name: ASHA.name }),
    });
    await expect(
      sheet.getByRole("radio", { name: CORRECTION.add, exact: true }),
    ).toBeChecked();
    await sheet.getByLabel(CORRECTION.amount, { exact: true }).fill("9,000");
    await sheet
      .getByRole("radio", {
        name: CORRECTION.readyReason.dayNotCounted,
        exact: true,
      })
      .click();
    await sheet
      .getByRole("button", { name: CORRECTION.save, exact: true })
      .click();
    await expect(sheet).toBeHidden();
    await expect(
      phone.getByText(/^Imeandikwa: marekebisho ya \+\s9,000\.$/),
    ).toBeVisible();
    await expect(
      phone.getByRole("button", { name: line, exact: true }),
    ).toHaveCount(1);
    await expect.poll(() => total(phone)).toBe(ADDED.plus(before).toFixed());
  });

  await test.step("its line crosses it out with the ready reason; it stays, struck through, and her pay is as it was", async () => {
    await phone.getByRole("button", { name: line, exact: true }).click();
    const sheet = phone.getByRole("dialog", {
      name: /^Marekebisho ya Asha · \+\s9,000$/,
    });
    await sheet
      .getByRole("radio", {
        name: CORRECTION.readyReason.wrongAmount,
        exact: true,
      })
      .click();
    await sheet
      .getByRole("button", { name: CORRECTION.void.action, exact: true })
      .click();
    await expect(sheet).toBeHidden();
    const crossed = phone.getByRole("region", {
      name: CORRECTION.crossedOut,
      exact: true,
    });
    await expect(crossed.getByText(line, { exact: true })).toBeVisible();
    await expect(
      crossed.getByText(new RegExp(`: ${CORRECTION.readyReason.wrongAmount}$`)),
    ).toBeVisible();
    // Never brought back: no line of it in the pay.
    await expect(
      phone.getByRole("button", { name: line, exact: true }),
    ).toHaveCount(0);
    await expect.poll(() => total(phone)).toBe(before);
  });
});
