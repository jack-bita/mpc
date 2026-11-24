// flags.spec.ts — Tofauti on the demo, end to end (CTRL-4): Meneja opens the list on his phone, keeps it to one kind in
// Chuja's sheet, opens the record of Asha's the server refused, reads why, and closes it as no problem with one of the
// demo's ready notes; the list he comes back to is as he left it, with that flag among the closed ones. Through the real
// server: the demo seed's three flags, the flags' routes, the sheets and the pages.
//
// The seed gives two that wait and one closed (backend/apps/demo/services.py). A close is never taken back and the tests
// share one database (the-shop.ts), so the count is read before and compared after, never typed here: another test's
// laptop could raise a flag of its own. No other file reads the flags.
import sw from "../messages/sw.json";

import {
  expect,
  MANAGER_EMAIL,
  MANAGER_PASSWORD,
  test,
  words,
} from "./the-shop";

const FLAGS = sw.flags;
const REFUSED = FLAGS.kind.invalid_document;

/** The waiting tab, "Zinasubiri (2)", whatever it counts. */
const WAITING_TAB = new RegExp(
  `^${FLAGS.tabs.waitingCount.replace("({count})", "\\((\\d+)\\)")}$`,
);

test("Meneja closes a flag on the demo, and finds it among the closed ones", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();
  const flagsLine = phone.getByRole("link", {
    // Its kind, then who it names, where and the day: "Kumbukumbu haikukubalika Asha · Duka zima · Jumatatu 23/11".
    name: new RegExp(`^${REFUSED} Asha · ${FLAGS.wholeShop} · .+$`),
  });

  await test.step("Meneja logs in on the phone and opens Tofauti", async () => {
    await phone.goto("/login/");
    await phone.getByLabel(sw.login.password.name).fill(MANAGER_EMAIL);
    // exact: the eye beside the box is labelled "Onyesha nenosiri", which holds the word too (the-shop.ts).
    await phone
      .getByLabel(sw.login.password.password, { exact: true })
      .fill(MANAGER_PASSWORD);
    await phone
      .getByRole("button", { name: sw.login.password.send, exact: true })
      .click();
    await phone.getByRole("link", { name: FLAGS.title, exact: true }).click();
    await expect(
      phone.getByRole("heading", { name: FLAGS.title, level: 1 }),
    ).toBeVisible();
    await expect(phone.getByRole("tab", { name: WAITING_TAB })).toBeVisible();
    // The seed's two, whatever else waits.
    await expect(flagsLine).toBeVisible();
    await expect(
      phone
        .getByRole("link", { name: new RegExp(`^${FLAGS.kind.device_gap} `) })
        .first(),
    ).toBeVisible();
  });

  await test.step("Chuja keeps the list to one kind, from a sheet", async () => {
    await phone
      .getByRole("button", { name: FLAGS.filter.title, exact: true })
      .click();
    const sheet = phone.getByRole("dialog", { name: FLAGS.filter.title });
    await sheet.getByRole("radio", { name: REFUSED, exact: true }).click();
    await sheet
      .getByRole("button", { name: FLAGS.filter.show, exact: true })
      .click();
    await expect(sheet).toBeHidden();
    await expect(
      phone.getByText(words(FLAGS.filter.on, { what: REFUSED }), {
        exact: true,
      }),
    ).toBeVisible();
    await expect(flagsLine).toBeVisible();
    await expect(
      phone.getByRole("link", {
        name: new RegExp(`^${FLAGS.kind.device_gap} `),
      }),
    ).toHaveCount(0);
  });

  const before = Number(
    WAITING_TAB.exec(
      (await phone.getByRole("tab", { name: WAITING_TAB }).textContent()) ?? "",
    )?.[1],
  );

  await test.step("the flag's own page says what happened, and why", async () => {
    await flagsLine.click();
    await expect(
      phone.getByRole("heading", { name: REFUSED, level: 1 }),
    ).toBeVisible();
    await expect(
      phone.getByText(FLAGS.what.recordRefused, { exact: true }),
    ).toBeVisible();
    await expect(
      phone.getByText(
        words(FLAGS.page.why, { why: sw.errors.document.type_unknown }),
        { exact: true },
      ),
    ).toBeVisible();
    await expect(
      phone.getByRole("region", {
        name: words(FLAGS.page.notes, { count: "0" }),
      }),
    ).toBeVisible();
  });

  await test.step("Meneja closes it as no problem, with a ready note", async () => {
    await phone
      .getByRole("button", { name: FLAGS.act.dismiss.button, exact: true })
      .click();
    const sheet = phone.getByRole("dialog", { name: FLAGS.act.dismiss.title });
    await sheet
      .getByRole("radio", { name: FLAGS.ready.checkedLaptop, exact: true })
      .click();
    await sheet
      .getByRole("button", { name: FLAGS.act.dismiss.save, exact: true })
      .click();
    await expect(sheet).toBeHidden();
    await expect(
      phone.getByText(FLAGS.act.dismiss.done, { exact: true }),
    ).toBeVisible();
    const notes = phone.getByRole("region", {
      name: words(FLAGS.page.notes, { count: "1" }),
    });
    await expect(
      notes.getByText(FLAGS.ready.checkedLaptop, { exact: true }),
    ).toBeVisible();
    // Closed for good: no button is left.
    await expect(
      phone.getByRole("button", {
        name: FLAGS.act.resolve.button,
        exact: true,
      }),
    ).toHaveCount(0);
  });

  await test.step("the list is as he left it, and the flag is among the closed ones", async () => {
    await phone.getByRole("button", { name: sw.pageHeader.back }).click();
    await expect(
      phone.getByText(words(FLAGS.filter.on, { what: REFUSED }), {
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      phone.getByRole("tab", {
        name: words(FLAGS.tabs.waitingCount, { count: String(before - 1) }),
        exact: true,
      }),
    ).toBeVisible();
    await expect(flagsLine).toHaveCount(0);

    await phone
      .getByRole("tab", { name: FLAGS.tabs.closed, exact: true })
      .click();
    await expect(flagsLine).toBeVisible();
    await expect(
      phone
        .getByRole("listitem")
        .filter({ hasText: REFUSED })
        .getByText(FLAGS.status.dismissed, { exact: true }),
    ).toBeVisible();
  });
});
