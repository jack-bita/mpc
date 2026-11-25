// payslip.spec.ts — one who left is approved alone on the demo, end to end (WAGE-3): Meneja adds Neema on his phone, with
// a pay of 10,000 a day and no meals, adds the Ingia and Toka of her one day, and marks her left on it; opens her pay from
// Mishahara, which says TSh 10,000, and approves it alone, Idhinisha malipo ya Neema. The page then says who approved it
// and offers no approval; her day says it can't change any more and offers no button; and an advance typed for her, in
// the sheet that still lists her, is refused by the server beside its day. Through the real server: PPL-4's workers,
// WAGE-1's rate, ATT-13's taps, the book that counts the day, the sum, the approval (approve_leaver) and the lock in
// each service.
//
// Neema is the visitor's own worker, as a seed person can't be marked left on the demo (demo.people_fixed). A month of
// everyone is approved by no browser test: it needs a month that is over, which the demo has only on a month's first
// days, and nothing may be decided, typed or crossed out in it after, so every other test of it would fail.
//
// Her day is the last working day before today, counted from the day the first-day box starts on, the shop's today: the
// test never reads the clock of the machine it runs on. On a month's first days it falls in the month before, and the
// test goes back a month where a page opens on this one.
//
// It runs after the tests that read Mishahara (pay.spec.ts) or the month's attendance, by its name, as the tests run one
// at a time, file by file in their names' order (playwright.config.ts): pay.spec.ts expects only the seed's three. An
// approval is never taken back, and it moves nothing of anyone else's: she shares no meals.
import type { Page } from "@playwright/test";

import sw from "../messages/sw.json";

import {
  asShown,
  daysAfter,
  expect,
  MANAGER_EMAIL,
  MANAGER_PASSWORD,
  test,
  words,
} from "./the-shop";

const ADVANCES = sw.advances;
const ATTENDANCE = sw.attendanceMonth;
const DAY = sw.attendanceWorker;
const PAY = sw.pay;
const WORKERS = sw.workers;

/** The last working day before `today`, both as a date box writes them: yesterday, or a Saturday before a Sunday. */
function lastWorkingDayBefore(today: string): string {
  const yesterday = daysAfter(today, -1);
  const isSunday = new Date(`${yesterday}T00:00:00Z`).getUTCDay() === 0;
  return isSunday ? daysAfter(today, -2) : yesterday;
}

/** Back to the office home, from a page one tap away from it. */
async function back(phone: Page) {
  await phone.getByRole("button", { name: sw.pageHeader.back }).click();
}

test("Meneja approves the pay of one who left, and none of it changes after", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();
  const sheetCalled = (title: string) =>
    phone.getByRole("dialog", { name: title, exact: true });

  /** One of the office home's pages, on the month of Neema's day: the one it opens on, or the one before. */
  async function openOnHerMonth(title: string, monthBefore: boolean) {
    await phone.getByRole("link", { name: title, exact: true }).click();
    await expect(
      phone.getByRole("heading", { name: title, level: 1, exact: true }),
    ).toBeVisible();
    if (monthBefore)
      await phone
        .getByRole("button", { name: ATTENDANCE.before, exact: true })
        .click();
  }

  const [herDay, monthBefore] =
    await test.step("Meneja logs in and adds Neema, from the last working day", async () => {
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
        .getByRole("link", { name: WORKERS.title, exact: true })
        .click();
      await phone.getByRole("link", { name: WORKERS.add, exact: true }).click();
      await phone
        .getByLabel(WORKERS.form.fullName, { exact: true })
        .fill("Neema Mfano");
      await phone
        .getByLabel(WORKERS.form.nickname, { exact: true })
        .fill("Neema");
      const firstDay = phone.getByLabel(WORKERS.form.firstDay, { exact: true });
      // The box starts at the shop's today.
      const today = await firstDay.inputValue();
      const day = lastWorkingDayBefore(today);
      await firstDay.fill(day);
      await phone
        .getByRole("button", { name: WORKERS.form.save, exact: true })
        .click();
      await expect(
        phone.getByRole("heading", { name: "Neema", level: 1, exact: true }),
      ).toBeVisible();
      return [day, day.slice(0, 7) !== today.slice(0, 7)] as const;
    });

  await test.step("her pay is 10,000 a day from that day, with no meals", async () => {
    await phone
      .getByRole("button", { name: WORKERS.pay.set, exact: true })
      .click();
    const sheet = sheetCalled(words(WORKERS.pay.form.title, { name: "Neema" }));
    await sheet
      .getByLabel(WORKERS.pay.form.amount, { exact: true })
      .fill("10000");
    // It starts on her first day, the only one she works.
    await expect(
      sheet.getByLabel(WORKERS.pay.form.from, { exact: true }),
    ).toHaveValue(herDay);
    // No meals: so her total is her day alone, whatever the seed typed, and the other sharers' parts stay as they were.
    await sheet
      .getByRole("radio", { name: WORKERS.pay.form.mealsNo, exact: true })
      .click();
    await sheet
      .getByRole("button", { name: WORKERS.pay.form.save, exact: true })
      .click();
    await expect(sheet).toBeHidden();
  });

  await test.step("Ameondoka, her last day that same one", async () => {
    await phone
      .getByRole("button", { name: WORKERS.actions.leave, exact: true })
      .click();
    const sheet = sheetCalled(
      words(WORKERS.actions.title.leave, { name: "Neema" }),
    );
    await sheet
      .getByLabel(WORKERS.actions.lastDay, { exact: true })
      .fill(herDay);
    await sheet
      .getByLabel(WORKERS.actions.reason, { exact: true })
      .fill("Amehamia mbali");
    await sheet
      .getByRole("button", { name: WORKERS.actions.confirm.leave, exact: true })
      .click();
    await expect(sheet).toBeHidden();
    await expect(
      phone.getByText(
        words(WORKERS.actions.done.leave, {
          name: "Neema",
          day: asShown(herDay),
        }),
      ),
    ).toBeVisible();
    // The list, then the office home.
    await back(phone);
    await back(phone);
  });

  // Her day under her calendar: its title names it, "Jumanne 24/11/2026".
  const dayRegion = phone.getByRole("region").filter({
    has: phone.getByRole("heading", {
      name: new RegExp(`${asShown(herDay)}$`),
      level: 3,
    }),
  });

  const calendar =
    await test.step("Meneja adds her Ingia 07:00 and her Toka 18:45 on her calendar", async () => {
      await openOnHerMonth(ATTENDANCE.title, monthBefore);
      await phone.getByRole("link", { name: "Neema", exact: true }).click();
      await expect(
        phone.getByRole("heading", { name: "Neema", level: 1, exact: true }),
      ).toBeVisible();
      // "Jumanne 24/11: hakuja": her one day, with no tap.
      const [, month, date] = herDay.split("-");
      await phone
        .getByRole("button", {
          name: new RegExp(` ${date}/${month}: ${ATTENDANCE.kind.absent}$`),
        })
        .click();
      for (const [kind, time] of [
        [DAY.tapKind.in, "07:00"],
        [DAY.tapKind.out, "18:45"],
      ] as const) {
        await dayRegion
          .getByRole("button", { name: DAY.addTap, exact: true })
          .click();
        const sheet = sheetCalled(words(DAY.addSheetTitle, { name: "Neema" }));
        // Ingia is picked on a day with none, and Toka once it has one.
        await expect(
          sheet.getByRole("radio", { name: kind, exact: true }),
        ).toHaveAttribute("aria-checked", "true");
        await sheet.getByLabel(DAY.timeLabel, { exact: true }).fill(time);
        // On the demo, the reason is a ready one to tap (Jack: A), never typed.
        await sheet
          .getByText(DAY.readyTapReason.forgot_tap, { exact: true })
          .click();
        await sheet
          .getByRole("button", { name: DAY.addTapSave, exact: true })
          .click();
        await expect(sheet).toBeHidden();
        await expect(
          dayRegion
            .getByRole("listitem")
            .filter({ hasText: `${kind} ${time}` }),
        ).toBeVisible();
      }
      await expect(
        dayRegion.getByText(DAY.status.on_time, { exact: true }),
      ).toBeVisible();
      // Kept for later: the page's own address opens her calendar on that month, and on that day.
      const address = phone.url();
      await back(phone);
      await back(phone);
      return address;
    });

  await test.step("her pay says TSh 10,000, and Idhinisha malipo ya Neema approves it", async () => {
    await openOnHerMonth(PAY.title, monthBefore);
    await phone
      .getByRole("list", { name: PAY.workersLabel })
      .getByRole("link", { name: "Neema", exact: true })
      .click();
    const approveHers = words(PAY.approval.leaverTitle, { name: "Neema" });
    await phone.getByRole("button", { name: approveHers, exact: true }).click();
    const sheet = sheetCalled(approveHers);
    // What is approved is what was read: "Novemba 2026 · Jumla TSh 10,000".
    await expect(sheet.getByText(/ · Jumla TSh\s10,000$/)).toBeVisible();
    await sheet
      .getByRole("button", { name: PAY.approval.action, exact: true })
      .click();
    await expect(sheet).toBeHidden();
    await expect(phone.getByText(/^Imeidhinishwa na Meneja · /)).toBeVisible();
    await expect(
      phone.getByRole("button", { name: approveHers, exact: true }),
    ).toHaveCount(0);
    // Read again from the server, the payslip says the same.
    await phone.reload();
    await expect(phone.getByText(/^Imeidhinishwa na Meneja · /)).toBeVisible();
    const total = phone
      .getByRole("table", { name: PAY.linesCaption })
      .getByRole("row")
      .last()
      .getByRole("cell")
      .last();
    await expect(total).toHaveText(/^TSh\s10,000$/);
  });

  await test.step("her day says it can't change any more, and offers nothing", async () => {
    await phone.goto(calendar);
    await expect(
      dayRegion.getByText(DAY.closed, { exact: true }),
    ).toBeVisible();
    // Its taps stay to be read.
    await expect(
      dayRegion
        .getByRole("list", { name: DAY.tapsLabel })
        .getByRole("listitem"),
    ).toHaveCount(2);
    await expect(dayRegion.getByRole("button")).toHaveCount(0);
  });

  await test.step("an advance typed for her is refused by the server, beside its day", async () => {
    await phone.goto("/office/");
    await openOnHerMonth(ADVANCES.title, monthBefore);
    await phone
      .getByRole("button", { name: ADVANCES.record.title, exact: true })
      .click();
    const sheet = sheetCalled(ADVANCES.record.title);
    await sheet
      .getByRole("radio", {
        name: words(ADVANCES.record.workerLeft, {
          name: "Neema",
          date: asShown(herDay),
        }),
        exact: true,
      })
      .click();
    await sheet.getByLabel(ADVANCES.record.date, { exact: true }).fill(herDay);
    await sheet
      .getByLabel(ADVANCES.record.amount, { exact: true })
      .fill("5000");
    await sheet
      .getByRole("button", { name: ADVANCES.record.save, exact: true })
      .click();
    await expect(sheet.getByText(sw.errors.pay.day_approved)).toBeVisible();
    await sheet
      .getByRole("button", { name: sw.sheet.cancel, exact: true })
      .click();
    await expect(sheet).toBeHidden();
  });
});
