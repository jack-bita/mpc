// attendance-worker.spec.ts — a worker's month and a day of it on the demo, end to end (ATT-12): Meneja opens
// Mahudhurio ya mwezi on his phone, taps Asha's day to decide, and sees it open under her calendar, with its reason,
// her Ingia from the demo's laptop and why it has no photo; the back arrow takes him back to the same month. Through
// the real server: the demo seed's three weeks of taps (DATA-8), worked out by the book of days (ATT-10), the worker's
// month's route (ATT-12), and the page.
//
// The seed gives Asha one day to decide, her latest working day before today, an Ingia with no Toka, from Laptop ya
// Dawa, with the demo's reason for no photo (DemoPerson in backend/apps/demo/services.py). On a month's first days that
// day falls in the month before, and the month page says no working day is over yet: the test goes back a month, as
// attendance-month.spec.ts does, so it never reads the clock of the machine it runs on.
//
// The tests share one database (the-shop.ts). Others clock Asha in today, which shows on today's square, not on the
// day to decide; none moves a day of the seed's weeks (demo.people_fixed).
import sw from "../messages/sw.json";

import {
  expect,
  MANAGER_EMAIL,
  MANAGER_PASSWORD,
  test,
  words,
} from "./the-shop";

const MONTH = sw.attendanceMonth;
const WORKER = sw.attendanceWorker;

test("Meneja opens Asha's day to decide under her calendar, and comes back to the month", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();
  // The month on show, "Novemba 2026", read once the page has one, to find it again on the way back.
  let monthShown = "";

  await test.step("Meneja logs in on the phone and opens Mahudhurio ya mwezi", async () => {
    await phone.goto("/login/");
    await phone.getByLabel(sw.login.password.name).fill(MANAGER_EMAIL);
    // exact: the eye beside the box is labelled "Onyesha nenosiri", which holds the word too (the-shop.ts).
    await phone
      .getByLabel(sw.login.password.password, { exact: true })
      .fill(MANAGER_PASSWORD);
    await phone
      .getByRole("button", { name: sw.login.password.send, exact: true })
      .click();
    await phone.getByRole("link", { name: MONTH.title, exact: true }).click();
    const nothingOver = phone.getByText(MONTH.nothingOverYet, { exact: true });
    const toDecide = phone.getByRole("list", {
      name: words(MONTH.toDecide, { count: "1" }),
    });
    // One of the two, once the server has answered; on a month's first days, back to the month before.
    await expect(toDecide.or(nothingOver)).toBeVisible();
    if (await nothingOver.isVisible()) {
      await phone
        .getByRole("button", { name: MONTH.before, exact: true })
        .click();
      await expect(toDecide).toBeVisible();
    }
    monthShown =
      (await phone.getByRole("heading", { level: 2 }).textContent()) ?? "";
  });

  await test.step("Asha's day to decide opens under her calendar", async () => {
    await phone
      .getByRole("link", {
        name: new RegExp(`^Asha · .+ · ${MONTH.reason.no_out}$`),
      })
      .click();
    await expect(
      phone.getByRole("heading", { name: "Asha", level: 1 }),
    ).toBeVisible();
    await expect(
      phone.getByRole("table", {
        name: words(WORKER.calendarCaption, {
          name: "Asha",
          month: monthShown,
        }),
      }),
    ).toBeVisible();
    const day = phone.getByRole("region").filter({
      hasText: words(WORKER.why, { why: MONTH.reason.no_out }),
    });
    await expect(day).toBeVisible();
    // Her Ingia, from the demo's laptop, at a minute of the morning, and why it has no photo; and no Toka.
    await expect(
      day.getByText(
        new RegExp(`^${WORKER.tapKind.in} \\d\\d:\\d\\d .+ · Laptop ya Dawa$`),
      ),
    ).toBeVisible();
    await expect(
      day.getByText(words(WORKER.noPhoto, { why: WORKER.noPhotoWhy.demo }), {
        exact: true,
      }),
    ).toBeVisible();
    await expect(day.getByText(WORKER.noOut, { exact: true })).toBeVisible();
  });

  await test.step("the back arrow comes back to the same month", async () => {
    await phone.getByRole("button", { name: sw.pageHeader.back }).click();
    await expect(
      phone.getByRole("heading", { name: MONTH.title, level: 1 }),
    ).toBeVisible();
    await expect(
      phone.getByRole("heading", { name: monthShown, level: 2 }),
    ).toBeVisible();
  });
});
