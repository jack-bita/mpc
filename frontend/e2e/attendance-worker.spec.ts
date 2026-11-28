// attendance-worker.spec.ts — a worker's month and a day of it on the demo, end to end (ATT-12): Meneja opens
// Mahudhurio ya mwezi on his phone, taps Asha's day to decide, and sees it open under her calendar, with its reason,
// her Ingia from the demo's laptop and why it has no photo; the back arrow takes him back to the same month. Through
// the real server: the demo seed's taps (DATA-8), worked out by the book of days (ATT-10), the worker's
// month's route (ATT-12), and the page.
//
// The seed gives three days to decide (attendance-month.spec.ts says which); the latest is Asha's, an Ingia with no
// Toka, from Laptop ya Dawa, with the demo's reason for no photo (DemoPerson in backend/apps/demo/services.py). On a month's first days that
// day falls in the month before, and the month page says no working day is over yet: the test goes back a month, as
// attendance-month.spec.ts does, so it never reads the clock of the machine it runs on.
//
// The tests share one database (the-shop.ts). Others clock Asha in today, which shows on today's square, not on the
// day to decide; none before it moves a day of the seed's (demo.people_fixed).
//
// The second test decides that day (ATT-6): Meneja opens it, taps Amua siku hii, picks Siku kamili and one of the demo's
// ready reasons in the sheet, and the day shows his decision beside what the system said, and leaves Zinahitaji
// uamuzi. A decision is never taken back, so it runs last of the tests that read Asha's day to decide: after
// attendance-month.spec.ts, as the tests run one at a time, file by file in their names' order (playwright.config.ts),
// and after the test above, in this file's order. Of the later files, pay.spec.ts reads the month and asks nothing of a
// day to decide, and whole-month.spec.ts decides whatever of last month still waits, however many.
//
// The third fixes the taps of another of Asha's days to decide, her third latest, out at 15:00 (ATT-13): Meneja crosses
// out the 15:00 Toka in its sheet, as tapped by mistake, adds Toka 18:45, as she left after closing, and the day is a
// full day, on time, its crossed-out Toka struck through, and waits no more. A fix is never taken back either, so it
// runs last of all, after the decision above.
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

// "Zinahitaji uamuzi (3)", or (1) or (2): the three latest working days may fall across two months.
const TO_DECIDE = new RegExp(
  `^${MONTH.toDecide.replace("({count})", "\\(\\d\\)")}$`,
);
// Asha's line of the list, her latest day, an Ingia with no Toka: "Asha · Ijumaa 20/11 · hakuna Toka".
const ASHAS_NO_TOKA = new RegExp(`^Asha · .+ · ${MONTH.reason.no_out}$`);
// Her third latest, out at 15:00, before closing: "Asha · Jumanne 17/11 · aliondoka saa 15:00 mchana".
const ASHAS_EARLY_TOKA = new RegExp(
  `^Asha · .+ · ${MONTH.reason.left_early.replace("{time}", "15:00 .+")}$`,
);
// A sentence of the book with a date in it, "… na Meneja, 20/11/2026 …", whatever day the test runs on.
function withADate(sentence: string, values: Record<string, string>): RegExp {
  const [before, after] = words(sentence, { ...values, date: "@" }).split("@");
  return new RegExp(`^${before}\\d\\d/\\d\\d/\\d{4}${after}$`);
}

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
    const toDecide = phone.getByRole("list", { name: TO_DECIDE });
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
    await phone.getByRole("link", { name: ASHAS_NO_TOKA }).click();
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
    const toDecide = phone.getByRole("list", { name: TO_DECIDE });
    // On a month's first days, the day is in the month before, as in the test above.
    await expect(toDecide.or(nothingOver)).toBeVisible();
    if (await nothingOver.isVisible()) {
      await phone
        .getByRole("button", { name: MONTH.before, exact: true })
        .click();
      await expect(toDecide).toBeVisible();
    }
    await phone.getByRole("link", { name: ASHAS_NO_TOKA }).click();
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
    // The list, or the words for none, once the server has answered; and Asha's day with no Toka no longer in it. The
    // seed's other days to decide may still be there, in this month or the one before (attendance-month.spec.ts).
    await expect(
      phone
        .getByRole("list", { name: TO_DECIDE })
        .or(phone.getByText(MONTH.noneToDecide, { exact: true })),
    ).toBeVisible();
    await expect(phone.getByRole("link", { name: ASHAS_NO_TOKA })).toHaveCount(
      0,
    );
  });
});

test("Meneja crosses out Asha's Toka tapped by mistake and adds her true one, and the day waits no more", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();
  // Her day out at 15:00: the region whose taps hold that Toka, before the fixes and after.
  const day = phone.getByRole("region").filter({
    hasText: new RegExp(`${WORKER.tapKind.out} 15:00`),
  });

  await test.step("Meneja opens Asha's day out at 15:00, from Mahudhurio ya mwezi", async () => {
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
    const toDecide = phone.getByRole("list", { name: TO_DECIDE });
    // On a month's first days, the day is in the month before, as in the tests above; and it may be the month before
    // even later in a month, as it is her third latest working day.
    await expect(toDecide.or(nothingOver)).toBeVisible();
    const early = phone.getByRole("link", { name: ASHAS_EARLY_TOKA });
    if (!(await early.isVisible())) {
      await phone
        .getByRole("button", { name: MONTH.before, exact: true })
        .click();
    }
    await early.click();
    await expect(day).toBeVisible();
  });

  await test.step("he crosses out the 15:00 Toka in its sheet, with the demo's ready reason", async () => {
    const toka = day.getByRole("listitem").filter({
      hasText: new RegExp(`^${WORKER.tapKind.out} 15:00`),
    });
    await toka
      .getByRole("button", { name: WORKER.voidTap, exact: true })
      .click();
    const sheet = phone.getByRole("dialog", {
      name: words(WORKER.voidSheetTitle, {
        kind: WORKER.tapKind.out,
        name: "Asha",
      }),
    });
    await expect(sheet).toBeVisible();
    // On the demo, the reason is the ready one to tap (Jack: A), never typed.
    await sheet
      .getByText(WORKER.readyTapReason.wrong_tap, { exact: true })
      .click();
    await sheet
      .getByRole("button", { name: WORKER.voidTap, exact: true })
      .click();
    await expect(sheet).toBeHidden();
    // Struck through, with who, when and why, and the day now has no Toka.
    await expect(
      day.getByText(
        withADate(WORKER.voidedBy, {
          by: "Meneja",
          reason: WORKER.readyTapReason.wrong_tap,
        }),
      ),
    ).toBeVisible();
    await expect(day.getByText(WORKER.noOut, { exact: true })).toBeVisible();
  });

  await test.step("he adds Toka 18:45 in its sheet, and the day is a full day", async () => {
    await day.getByRole("button", { name: WORKER.addTap, exact: true }).click();
    const sheet = phone.getByRole("dialog", {
      name: words(WORKER.addSheetTitle, { name: "Asha" }),
    });
    await expect(sheet).toBeVisible();
    // Toka is picked already, as the day has an Ingia.
    await expect(
      sheet.getByRole("radio", { name: WORKER.tapKind.out, exact: true }),
    ).toHaveAttribute("aria-checked", "true");
    await sheet.getByLabel(WORKER.timeLabel, { exact: true }).fill("18:45");
    await sheet
      .getByText(WORKER.readyTapReason.forgot_tap, { exact: true })
      .click();
    await sheet
      .getByRole("button", { name: WORKER.addTapSave, exact: true })
      .click();
    await expect(sheet).toBeHidden();
    await expect(
      day.getByText(
        withADate(WORKER.tapLineEntered, {
          kind: WORKER.tapKind.out,
          time: "18:45 jioni",
          by: "Meneja",
        }),
      ),
    ).toBeVisible();
    // In at 07:20, out at 18:45, after closing at 18:40: on time, and nothing to decide.
    await expect(
      day.getByText(WORKER.status.on_time, { exact: true }),
    ).toBeVisible();
  });

  await test.step("back on the month, the day waits no more", async () => {
    await phone.getByRole("button", { name: sw.pageHeader.back }).click();
    await expect(
      phone.getByRole("heading", { name: MONTH.title, level: 1 }),
    ).toBeVisible();
    await expect(
      phone
        .getByRole("list", { name: TO_DECIDE })
        .or(phone.getByText(MONTH.noneToDecide, { exact: true })),
    ).toBeVisible();
    await expect(
      phone.getByRole("link", { name: ASHAS_EARLY_TOKA }),
    ).toHaveCount(0);
  });
});
