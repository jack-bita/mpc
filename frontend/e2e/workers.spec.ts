// workers.spec.ts — the demo's manager adds a worker and suspends him, end to end (PPL-6): on the manager's phone,
// Wafanyakazi lists the seed's people; Ongeza adds Juma, who comes at the top; his name opens his own page; Simamisha,
// with a reason, suspends him, and Rudisha takes its place. The card's Done when, through the real server: PPL-4's
// routes, their key (staff.manage on the whole shop, which the seed gives the demo's Meneja), and their rules.
//
// Juma is the visitor's own worker, so the demo lets him change (demo.people_fixed guards only the seed's people). The
// tests share one database (the-shop.ts), made fresh for each run, and no other test reads or adds workers, so one
// Juma per run never meets a nickname already taken.
import type { Page } from "@playwright/test";

import sw from "../messages/sw.json";

import {
  asShown,
  expect,
  MANAGER_EMAIL,
  MANAGER_PASSWORD,
  test,
  words,
} from "./the-shop";

const WORKERS = sw.workers;

/** A worker's link on the list: their nickname and full name, as the row writes them. */
function rowLink(phone: Page, nickname: string, fullName: string) {
  return phone.getByRole("link", {
    name: words(WORKERS.names, { nickname, fullName }),
    exact: true,
  });
}

/** The value beside a label on a worker's page: the <dd> after its <dt>. */
function valueOf(phone: Page, label: string) {
  return phone.locator(`dt:text-is("${label}") + dd`);
}

test("the demo's manager adds a worker and suspends him", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();

  await test.step("Meneja logs in on the phone and opens Wafanyakazi", async () => {
    await phone.goto("/login/");
    await phone.getByLabel(sw.login.password.name).fill(MANAGER_EMAIL);
    // exact: the eye beside the box is labelled "Onyesha nenosiri", which holds the word too (the-shop.ts).
    await phone
      .getByLabel(sw.login.password.password, { exact: true })
      .fill(MANAGER_PASSWORD);
    await phone
      .getByRole("button", { name: sw.login.password.send, exact: true })
      .click();
    await phone.getByRole("link", { name: WORKERS.title, exact: true }).click();
    await expect(
      phone.getByRole("heading", { name: WORKERS.title, level: 1 }),
    ).toBeVisible();
  });

  await test.step("the seed's people are listed", async () => {
    await expect(rowLink(phone, "Meneja", "Meneja Mfano")).toBeVisible();
    await expect(rowLink(phone, "Asha", "Asha Mfano")).toBeVisible();
    await expect(rowLink(phone, "Baraka", "Baraka Mfano")).toBeVisible();
  });

  const firstDay = await test.step("Ongeza: Juma, and Hifadhi", async () => {
    await phone.getByRole("button", { name: WORKERS.add, exact: true }).click();
    await phone
      .getByLabel(WORKERS.form.fullName, { exact: true })
      .fill("Juma Mfano");
    await phone.getByLabel(WORKERS.form.nickname, { exact: true }).fill("Juma");
    await phone
      .getByLabel(WORKERS.form.jobTitle, { exact: true })
      .fill("Muuzaji wa dawa");
    // The box starts at the shop's today, as the page reads it: the test never leans on its own clock or zone.
    const today = await phone
      .getByLabel(WORKERS.form.firstDay, { exact: true })
      .inputValue();
    await phone
      .getByRole("button", { name: WORKERS.form.save, exact: true })
      .click();
    await expect(
      phone.getByText(words(WORKERS.added, { name: "Juma" })),
    ).toBeVisible();
    // At the top: the list comes newest first.
    await expect(
      phone.getByRole("list").first().getByRole("listitem").first(),
    ).toContainText(
      words(WORKERS.names, { nickname: "Juma", fullName: "Juma Mfano" }),
    );
    return today;
  });

  await test.step("his name opens his own page, with everything of his", async () => {
    await rowLink(phone, "Juma", "Juma Mfano").click();
    await expect(
      phone.getByRole("heading", { name: "Juma", level: 1 }),
    ).toBeVisible();
    await expect(valueOf(phone, WORKERS.form.fullName)).toHaveText(
      "Juma Mfano",
    );
    await expect(valueOf(phone, WORKERS.form.jobTitle)).toHaveText(
      "Muuzaji wa dawa",
    );
    await expect(valueOf(phone, WORKERS.form.firstDay)).toHaveText(
      asShown(firstDay),
    );
    await expect(valueOf(phone, WORKERS.view.status)).toHaveText(
      WORKERS.status.active,
    );
    await expect(valueOf(phone, WORKERS.view.roles)).toHaveText(WORKERS.noRole);
  });

  await test.step("Simamisha, with a reason: he is suspended, and Rudisha takes its place", async () => {
    await phone
      .getByRole("button", { name: WORKERS.actions.suspend, exact: true })
      .click();
    await phone
      .getByLabel(WORKERS.actions.reason, { exact: true })
      .fill("Hakuja siku tatu bila ruhusa");
    await phone
      .getByRole("button", { name: WORKERS.actions.save, exact: true })
      .click();
    await expect(
      phone.getByText(words(WORKERS.actions.done.suspend, { name: "Juma" })),
    ).toBeVisible();
    await expect(valueOf(phone, WORKERS.view.status)).toHaveText(
      WORKERS.status.suspended,
    );
    await expect(
      phone.getByRole("button", {
        name: WORKERS.actions.unsuspend,
        exact: true,
      }),
    ).toBeVisible();
  });

  await test.step("back on the list, he shows as suspended", async () => {
    await phone.getByRole("button", { name: sw.pageHeader.back }).click();
    const juma = phone
      .getByRole("listitem")
      .filter({ has: rowLink(phone, "Juma", "Juma Mfano") });
    await expect(juma).toContainText(WORKERS.status.suspended);
  });
});
