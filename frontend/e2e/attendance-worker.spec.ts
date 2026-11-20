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
//
// The second test decides that day (ATT-6): Meneja opens it, taps Amua siku hii, picks Siku kamili and one of the demo's
// ready reasons in the sheet, and the day shows his decision beside what the system said, and leaves Zinahitaji
// uamuzi. A decision is never taken back, so it runs last of the tests that read Asha's day to decide: after
// attendance-month.spec.ts, as the tests run one at a time, file by file in their names' order (playwright.config.ts),
// and after the test above, in this file's order. No later file reads the month.
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

test("Meneja decides Asha's day in a sheet, and it waits no more", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();
  const sheet = phone.getByRole("dialog", {
    name: words(WORKER.sheetTitle, { name: "Asha" }),
  });

  await test.step("Meneja opens Asha's day to decide, from Mahudhurio ya mwezi", async () => {
    await phone.goto("/login/");
    await phone.getByLabel(sw.login.password.name).fill(MANAGER_EMAIL);
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
    // On a month's first days, the day is in the month before, as in the test above.
    await expect(toDecide.or(nothingOver)).toBeVisible();
    if (await nothingOver.isVisible()) {
      await phone
        .getByRole("button", { name: MONTH.before, exact: true })
        .click();
      await expect(toDecide).toBeVisible();
    }
    await phone
      .getByRole("link", {
        name: new RegExp(`^Asha · .+ · ${MONTH.reason.no_out}$`),
      })
      .click();
  });

  await test.step("the sheet slides up with the day's choices, and Meneja decides a full day", async () => {
    const day = phone.getByRole("region").filter({
      hasText: words(WORKER.why, { why: MONTH.reason.no_out }),
    });
    await day.getByRole("button", { name: WORKER.decide, exact: true }).click();
    await expect(sheet).toBeVisible();
    // The demo's fines are made up (rule 10): the line for a late day names one, whatever its amount.
    await expect(
      sheet.getByText(WORKER.decision.on_time, { exact: true }),
    ).toBeVisible();
    await sheet.getByText(WORKER.decision.on_time, { exact: true }).click();
    // On the demo, the reason is one of three ready ones to tap (Jack: A), never typed.
    await sheet
      .getByText(WORKER.readyReason.forgot_toka, { exact: true })
      .click();
    await sheet.getByRole("button", { name: WORKER.save, exact: true }).click();
    await expect(sheet).toBeHidden();
  });

  await test.step("the day shows his decision beside what the system said", async () => {
    const day = phone.getByRole("region").filter({
      hasText: words(WORKER.decisionReason, {
        reason: WORKER.readyReason.forgot_toka,
      }),
    });
    // "Siku kamili · uamuzi wa Meneja, 20/11/2026": the sentence from the book, with whatever day the test runs on.
    const [before, after] = words(WORKER.decidedBy, {
      decision: WORKER.decision.on_time,
      by: "Meneja",
      date: "@",
    }).split("@");
    await expect(
      day.getByText(new RegExp(`^${before}\\d\\d/\\d\\d/\\d{4}${after}$`)),
    ).toBeVisible();
    await expect(
      day.getByText(
        words(WORKER.systemSaidWhy, {
          said: WORKER.status.needs_review,
          why: MONTH.reason.no_out,
        }),
        { exact: true },
      ),
    ).toBeVisible();
    await expect(
      day.getByRole("button", { name: WORKER.changeDecision, exact: true }),
    ).toBeVisible();
  });

  await test.step("back on the month, the day waits no more", async () => {
    await phone.getByRole("button", { name: sw.pageHeader.back }).click();
    await expect(
      phone.getByRole("heading", { name: MONTH.title, level: 1 }),
    ).toBeVisible();
    await expect(
      phone.getByText(MONTH.noneToDecide, { exact: true }),
    ).toBeVisible();
  });
});
