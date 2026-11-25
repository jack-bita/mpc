// pay.spec.ts — the month's pay on the demo, end to end (WAGE-2): Meneja opens Mishahara on his phone, sees a total for
// each worker paid by the day and the total of all; taps his own name and reads his pay line by line, each line
// multiplying to what it shows and all of them adding up to the total; and finds Asha's same total on her own page.
// Through the real server: the demo seed's three weeks of taps (DATA-8), rates and meal money, worked out by the book of
// days, the sum, its routes and the pages.
//
// The sums are checked here as the owner would with a calculator, on whatever days the seed made: the test types no
// amount of its own, as the weeks may fall across two months, and other tests decide Asha's days (attendance-worker.spec.ts)
// and clock her in today. The page opens on this month, counted up to yesterday; on a month's first days it says none is
// over yet, and the test goes back one month, as a person would, so it never reads the clock of the machine it runs on.
//
// Meneja holds the two keys of pay on the demo (PEOPLE, backend/apps/demo/services.py), and a daily rate of 15,000, which
// no visitor may change. Nothing here is saved, so it leaves the shop as it found it.
import sw from "../messages/sw.json";

import {
  ASHA,
  expect,
  MANAGER_EMAIL,
  MANAGER_PASSWORD,
  test,
  words,
} from "./the-shop";

const PAY = sw.pay;
const MONTH = sw.attendanceMonth;

/** An amount as the page writes it, as a number: "TSh 152,000" → 152000, "− 2,000" → −2000. Whole shillings, so a plain
 * number is exact here, in a test's own sum. */
function amount(text: string): number {
  const figures = Number(text.replace(/[^\d]/g, ""));
  return /[−-]/.test(text) ? -figures : figures;
}

test("Meneja reads the month's pay on the demo, line by line", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();
  const list = phone.getByRole("list", { name: PAY.workersLabel });
  /** A worker's total on Mishahara. */
  const totalOf = async (name: string) =>
    amount(
      await list
        .getByRole("listitem")
        .filter({ has: phone.getByRole("link", { name, exact: true }) })
        .locator("p")
        .nth(1)
        .innerText(),
    );
  // Whether the test had to go back a month, for the card on Asha's page, which opens on this one.
  let wentBack = false;

  await test.step("Meneja logs in on the phone and opens Mishahara", async () => {
    await phone.goto("/login/");
    await phone.getByLabel(sw.login.password.name).fill(MANAGER_EMAIL);
    // exact: the eye beside the box is labelled "Onyesha nenosiri", which holds the word too (the-shop.ts).
    await phone
      .getByLabel(sw.login.password.password, { exact: true })
      .fill(MANAGER_PASSWORD);
    await phone
      .getByRole("button", { name: sw.login.password.send, exact: true })
      .click();
    await phone.getByRole("link", { name: PAY.title, exact: true }).click();
    await expect(
      phone.getByRole("heading", { name: PAY.title, level: 1 }),
    ).toBeVisible();
    await expect(list).toBeVisible();
    if (
      await phone.getByText(PAY.nothingOverYet, { exact: true }).isVisible()
    ) {
      wentBack = true;
      await phone
        .getByRole("button", { name: MONTH.before, exact: true })
        .click();
      await expect(
        phone.getByText(PAY.nothingOverYet, { exact: true }),
      ).toBeHidden();
      await expect(list).toBeVisible();
    }
  });

  const totals =
    await test.step("a total for each worker paid by the day, and the total of all", async () => {
      await expect(list.getByRole("link")).toHaveText([
        "Asha",
        "Baraka",
        "Meneja",
      ]);
      const asha = await totalOf("Asha");
      const baraka = await totalOf("Baraka");
      const meneja = await totalOf("Meneja");
      // Meneja came each working day of the seed's weeks: there is something to pay.
      expect(meneja).toBeGreaterThan(0);
      const all = await phone
        .locator("p")
        .filter({ hasText: PAY.totalOfAll })
        .innerText();
      expect(amount(all)).toBe(asha + baraka + meneja);
      return { asha, meneja };
    });

  await test.step("Meneja's name opens his pay, whose lines multiply and add up to the total", async () => {
    await list.getByRole("link", { name: "Meneja", exact: true }).click();
    await expect(
      phone.getByRole("heading", { name: "Meneja", level: 1 }),
    ).toBeVisible();
    const table = phone.getByRole("table", { name: PAY.linesCaption });
    const full = table.getByRole("row").filter({
      has: phone.getByRole("rowheader", { name: PAY.line.full, exact: true }),
    });
    await expect(full).toHaveCount(1);
    const [days, each] = (await full.getByRole("cell").nth(0).innerText())
      .split("×")
      .map(amount) as [number, number];
    expect(each).toBe(15_000);
    expect(amount(await full.getByRole("cell").nth(1).innerText())).toBe(
      days * each,
    );
    // Every line's last part, the total's too: the lines add up to it.
    const amounts: number[] = [];
    for (const row of await table.getByRole("row").all())
      amounts.push(amount(await row.getByRole("cell").last().innerText()));
    const total = amounts.pop();
    expect(total).toBe(totals.meneja);
    expect(amounts.reduce((sum, part) => sum + part, 0)).toBe(total);
  });

  await test.step("the arrow comes back to Mishahara on the same month", async () => {
    await phone.getByRole("button", { name: sw.pageHeader.back }).click();
    await expect(
      phone.getByRole("heading", { name: PAY.title, level: 1 }),
    ).toBeVisible();
    await expect(list).toBeVisible();
    expect(await totalOf("Meneja")).toBe(totals.meneja);
  });

  await test.step("Asha's own page shows the same total, in Malipo ya mwezi", async () => {
    await phone.getByRole("button", { name: sw.pageHeader.back }).click();
    await phone
      .getByRole("link", { name: sw.workers.title, exact: true })
      .click();
    // Named by both her names on that list: "Asha · Asha Mfano".
    await phone
      .getByRole("link", {
        name: words(sw.workers.names, {
          nickname: ASHA.name,
          fullName: ASHA.fullName,
        }),
        exact: true,
      })
      .click();
    const card = phone.getByRole("region", {
      name: PAY.cardTitle,
      exact: true,
    });
    await expect(card).toBeVisible();
    if (wentBack)
      await card
        .getByRole("button", { name: MONTH.before, exact: true })
        .click();
    const total = card.getByRole("row").last().getByRole("cell").last();
    await expect(total).toBeVisible();
    expect(amount(await total.innerText())).toBe(totals.asha);
  });
});
