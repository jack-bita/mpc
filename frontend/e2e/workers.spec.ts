// workers.spec.ts — the demo's manager adds a worker and suspends him, end to end (PPL-6): on the manager's phone,
// Wafanyakazi lists the seed's people; Ongeza, on the title's row, opens Mfanyakazi mpya, whose Hifadhi adds Juma and
// lands on his own page (UI-11); Simamisha, with a reason, suspends him, and Rudisha takes its place; back on the list
// he is at the top, suspended; Rudisha, with a reason, brings him back. The card's Done
// when, through the real server: PPL-4's routes, their key (staff.manage on the whole shop, which the seed gives the
// demo's Meneja), and their rules. Since UI-10, Simamisha, Rudisha and Ondoa each open a sheet over the page, its main
// button naming the action, and a tap on the dimmed page, a real browser's, leaves it open with what was typed.
// And roles (PPL-8): Meneja adds Zawadi, gives Zawadi the Seller role on Dawa on Ongeza kazi's own page (UI-11), back on
// her page with its line, and takes it away again with Ondoa and a reason, through PPL-7's routes: the giver rule, the give's own id, the end's reason. And on Zawadi's
// page, Kuingia (PPL-12): on the demo, Weka PIN and Nenosiri la muda are both off, with the one line saying why, as
// every visitor shares the seed's logins (Jack, PPL-12: A); a PIN or a password itself is checked by hand on the
// laptop's own stack, as the demo can show neither.
//
// Juma and Zawadi are the visitor's own workers, so the demo lets them change (demo.people_fixed guards only the seed's
// people, their roles included, PPL-7). The tests share one database (the-shop.ts), made fresh for each run, and no
// other test reads or adds workers, so one Juma and one Zawadi per run never meet a nickname already taken.
import type { Page } from "@playwright/test";

import sw from "../messages/sw.json";

import {
  asShown,
  expect,
  MANAGER_EMAIL,
  MANAGER_PASSWORD,
  SIDE,
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

/** Meneja logs in on the phone with the demo's public login, and opens Wafanyakazi from the office home. */
async function openWorkers(phone: Page) {
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
    phone.getByRole("heading", { name: WORKERS.title, level: 1, exact: true }),
  ).toBeVisible();
}

/** The sheet open over the page (UI-10), by its title. */
function sheet(phone: Page, title: string) {
  return phone.getByRole("dialog", { name: title, exact: true });
}

/** One of a worker's roles or keys card's two parts, by its heading: Cheo or Ruhusa za ziada. */
function cardPart(phone: Page, heading: string) {
  return phone.getByRole("region", { name: heading, exact: true });
}

test("the demo's manager adds a worker and suspends him", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();

  await test.step("Meneja logs in on the phone and opens Wafanyakazi", () =>
    openWorkers(phone));

  await test.step("the seed's people are listed", async () => {
    await expect(rowLink(phone, "Meneja", "Meneja Mfano")).toBeVisible();
    await expect(rowLink(phone, "Asha", "Asha Mfano")).toBeVisible();
    await expect(rowLink(phone, "Baraka", "Baraka Mfano")).toBeVisible();
  });

  const firstDay =
    await test.step("Ongeza opens Mfanyakazi mpya: Juma, and Hifadhi", async () => {
      await phone.getByRole("link", { name: WORKERS.add, exact: true }).click();
      await expect(
        phone.getByRole("heading", {
          name: WORKERS.newTitle,
          level: 1,
          exact: true,
        }),
      ).toBeVisible();
      await phone
        .getByLabel(WORKERS.form.fullName, { exact: true })
        .fill("Juma Mfano");
      await phone
        .getByLabel(WORKERS.form.nickname, { exact: true })
        .fill("Juma");
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
      return today;
    });

  await test.step("Hifadhi lands on his own page, with everything of his and the line that he was added", async () => {
    await expect(
      phone.getByRole("heading", { name: "Juma", level: 1, exact: true }),
    ).toBeVisible();
    await expect(
      phone.getByText(words(WORKERS.added, { name: "Juma" })),
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
    // His roles and keys, in their own card under the buttons (PPL-8): none of either yet.
    await expect(cardPart(phone, WORKERS.view.roles)).toContainText(
      WORKERS.noRole,
    );
    await expect(cardPart(phone, WORKERS.view.extraKeys)).toContainText(
      WORKERS.view.noExtraKeys,
    );
  });

  await test.step("Simamisha, in its sheet, with a reason: he is suspended, and Rudisha takes its place", async () => {
    await phone
      .getByRole("button", { name: WORKERS.actions.suspend, exact: true })
      .click();
    const suspending = sheet(
      phone,
      words(WORKERS.actions.title.suspend, { name: "Juma" }),
    );
    await suspending
      .getByLabel(WORKERS.actions.reason, { exact: true })
      .fill("Hakuja siku tatu bila ruhusa");
    // A thumb on the dimmed page above the sheet, its top-left corner: the sheet stays, and so does the reason (UI-10).
    // A finger's tap, as the manager's phone (a Pixel 7, touch on) gives, not a mouse's click (UI-10's review).
    await phone.touchscreen.tap(8, 8);
    await expect(suspending).toBeVisible();
    await expect(
      suspending.getByLabel(WORKERS.actions.reason, { exact: true }),
    ).toHaveValue("Hakuja siku tatu bila ruhusa");
    await suspending
      .getByRole("button", {
        name: WORKERS.actions.confirm.suspend,
        exact: true,
      })
      .click();
    await expect(suspending).toBeHidden();
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

  await test.step("back on the list, never in the form, he is at the top, suspended", async () => {
    // Mfanyakazi mpya gave its place to his page (UI-11): the arrow leads to the list.
    await phone.getByRole("button", { name: sw.pageHeader.back }).click();
    await expect(
      phone.getByRole("heading", {
        name: WORKERS.title,
        level: 1,
        exact: true,
      }),
    ).toBeVisible();
    // At the top: the list comes newest first.
    const juma = phone.getByRole("list").first().getByRole("listitem").first();
    await expect(juma).toContainText(
      words(WORKERS.names, { nickname: "Juma", fullName: "Juma Mfano" }),
    );
    await expect(juma).toContainText(WORKERS.status.suspended);
  });

  await test.step("Rudisha, in its sheet, with a reason: he works again", async () => {
    await rowLink(phone, "Juma", "Juma Mfano").click();
    await phone
      .getByRole("button", { name: WORKERS.actions.unsuspend, exact: true })
      .click();
    const bringing = sheet(
      phone,
      words(WORKERS.actions.title.unsuspend, { name: "Juma" }),
    );
    await bringing
      .getByLabel(WORKERS.actions.reason, { exact: true })
      .fill("Ameomba radhi");
    await bringing
      .getByRole("button", {
        name: WORKERS.actions.confirm.unsuspend,
        exact: true,
      })
      .click();
    await expect(
      phone.getByText(words(WORKERS.actions.done.unsuspend, { name: "Juma" })),
    ).toBeVisible();
    await expect(valueOf(phone, WORKERS.view.status)).toHaveText(
      WORKERS.status.active,
    );
  });
});

test("the demo's manager gives a role and takes it away", async ({
  managersPhone,
}) => {
  const phone = await managersPhone.newPage();
  const seller = words(WORKERS.roleOnSide, {
    role: WORKERS.roles.seller,
    side: SIDE,
  });

  await test.step("Meneja logs in on the phone and opens Wafanyakazi", () =>
    openWorkers(phone));

  await test.step("Ongeza: Zawadi, a worker of the visitor's own, and her page", async () => {
    await phone.getByRole("link", { name: WORKERS.add, exact: true }).click();
    await phone
      .getByLabel(WORKERS.form.fullName, { exact: true })
      .fill("Zawadi Mfano");
    await phone
      .getByLabel(WORKERS.form.nickname, { exact: true })
      .fill("Zawadi");
    await phone
      .getByRole("button", { name: WORKERS.form.save, exact: true })
      .click();
    // Hifadhi lands on her own page (UI-11).
    await expect(
      phone.getByRole("heading", { name: "Zawadi", level: 1, exact: true }),
    ).toBeVisible();
    await expect(cardPart(phone, WORKERS.view.roles)).toContainText(
      WORKERS.noRole,
    );
  });

  await test.step("Kuingia: on the demo, no PIN and no password for anyone", async () => {
    // Asked of the real server, which answers that this is the demo (askDemoOpen).
    await expect(valueOf(phone, WORKERS.logins.pin)).toHaveText(
      WORKERS.logins.pinNotSet,
    );
    await expect(
      phone.getByRole("button", { name: WORKERS.logins.setPin, exact: true }),
    ).toBeDisabled();
    await expect(
      phone.getByRole("button", {
        name: WORKERS.logins.temporaryPassword,
        exact: true,
      }),
    ).toBeDisabled();
    await expect(phone.getByText(sw.errors.demo.logins_fixed)).toBeVisible();
  });

  await test.step("Ongeza kazi opens its own page: the Seller role on Dawa, and back on her page", async () => {
    await phone
      .getByRole("link", { name: WORKERS.giving.add, exact: true })
      .click();
    // Its own page since UI-11, titled with what and who.
    await expect(
      phone.getByRole("heading", {
        name: words(WORKERS.giving.title, { name: "Zawadi" }),
        level: 1,
        exact: true,
      }),
    ).toBeVisible();
    await phone
      .getByRole("radio", { name: WORKERS.giving.aRole, exact: true })
      .click();
    // The shop's roles are asked as the page opens: the Seller's row comes with their answer.
    await phone
      .getByRole("radio", { name: WORKERS.roles.seller, exact: true })
      .click();
    // The Owner role is never offered, even to a manager the server would refuse anyway.
    await expect(
      phone.getByRole("radio", { name: WORKERS.roles.owner, exact: true }),
    ).toHaveCount(0);
    await phone.getByRole("radio", { name: SIDE, exact: true }).click();
    await phone
      .getByRole("button", { name: WORKERS.actions.save, exact: true })
      .click();
    // Back on Zawadi's page, where the person came from, its line on Cheo: the note went with the move (UI-11). Exact:
    // a heading's name matches a part of it by default, and "Ongeza kazi kwa Zawadi" holds "Zawadi" (UI-11's review).
    await expect(
      phone.getByRole("heading", { name: "Zawadi", level: 1, exact: true }),
    ).toBeVisible();
    await expect(
      phone.getByText(
        words(WORKERS.giving.done, { name: "Zawadi", what: seller }),
      ),
    ).toBeVisible();
    await expect(cardPart(phone, WORKERS.view.roles)).toContainText(seller);
  });

  await test.step("Ondoa, in its sheet, with a reason: the role is gone", async () => {
    await phone
      .getByRole("button", {
        name: words(WORKERS.ending.removeWhat, { what: seller }),
        exact: true,
      })
      .click();
    const removing = sheet(
      phone,
      words(WORKERS.ending.title, { what: seller, name: "Zawadi" }),
    );
    await removing
      .getByLabel(WORKERS.actions.reason, { exact: true })
      .fill("Amehamia Vyakula");
    await removing
      .getByRole("button", { name: WORKERS.ending.remove, exact: true })
      .click();
    await expect(removing).toBeHidden();
    await expect(
      phone.getByText(
        words(WORKERS.ending.done, { name: "Zawadi", what: seller }),
      ),
    ).toBeVisible();
    await expect(cardPart(phone, WORKERS.view.roles)).toContainText(
      WORKERS.noRole,
    );
  });
});
