// workers.spec.ts — the demo's manager adds a worker and suspends him, end to end (PPL-6): on the manager's phone,
// Wafanyakazi lists the seed's people; Ongeza, on the title's row, opens Mfanyakazi mpya, whose Hifadhi adds Juma and
// lands on his own page (UI-11); Simamisha, with a reason, suspends him, and Rudisha takes its place; back on the list
// he is at the top, suspended; Rudisha, with a reason, brings him back. The card's Done when, through the real server:
// PPL-4's routes, their key (staff.manage on the whole shop, which the seed gives the demo's Meneja), and their rules.
// Since UI-10, Simamisha, Rudisha and Ondoa each open a sheet over the page, its main button naming the action, and a
// tap on the dimmed page, a real browser's, leaves it open with what was typed. And roles (PPL-8): Meneja adds Zawadi,
// gives Zawadi the Seller role on Dawa on Ongeza kazi's own page (UI-11), back on her page with its line, and takes it
// away again with Ondoa and a reason, through PPL-7's routes: the giver rule, the give's own id, the end's reason. And
// on Zawadi's page, Kuingia (PPL-12): on the demo, Weka PIN and Nenosiri la muda are both off, with the one line saying
// why, as every visitor shares the seed's logins (Jack, PPL-12: A); a PIN or a password itself is checked by hand on
// the laptop's own stack, as the demo can show neither. And Picha (PPL-9): a photo like a phone's own, big and lying on
// its side, comes out small and upright in the sheet, holding none of the phone's hidden data, which only a real browser
// can show (photo-sheet.tsx, shrink-photo.ts); Hifadhi is off, as the demo keeps no photo (Jack, PPL-9), so a photo saved
// is checked by hand too.
//
// Juma and Zawadi are the visitor's own workers, so the demo lets them change (demo.people_fixed guards only the seed's
// people, their roles included, PPL-7). The tests share one database (the-shop.ts), made fresh for each run, and the one
// other test that adds a worker, payslip.spec.ts, calls her Neema and marks her left (WAGE-3), so one Juma and one Zawadi
// per run never meet a nickname already taken, and the list's first is still the one just added.
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

/** A photo as a phone makes one: a JPEG of 3000 × 2000 pixels, some 2.7 MB of it, with the phone's note (Exif,
 * orientation 6) that it was held upright, so the picture must be turned a quarter to stand: 2000 × 3000. Made in the
 * browser, which can write a JPEG, then given the note a canvas never writes. */
async function aPhonesOwnPhoto(phone: Page): Promise<Buffer> {
  const drawn = await phone.evaluate(async () => {
    const canvas = document.createElement("canvas");
    canvas.width = 3000;
    canvas.height = 2000;
    const context = canvas.getContext("2d") as CanvasRenderingContext2D;
    // A wall, and someone's head before it.
    const wall = context.createLinearGradient(0, 0, 3000, 2000);
    wall.addColorStop(0, "#c9b79c");
    wall.addColorStop(1, "#5d6b57");
    context.fillStyle = wall;
    context.fillRect(0, 0, 3000, 2000);
    context.fillStyle = "#6b4630";
    context.beginPath();
    context.ellipse(1500, 1000, 520, 700, 0, 0, 2 * Math.PI);
    context.fill();
    // A camera's grain on every pixel, as it is what makes a photo big, and what shrinking smooths away: flat colours
    // would be small already. From a fixed start, so each run draws the same picture.
    const picture = context.getImageData(0, 0, 3000, 2000);
    let grain = 1;
    for (let at = 0; at < picture.data.length; at += 4) {
      grain = (grain * 16807) % 2147483647;
      for (let colour = at; colour < at + 3; colour += 1)
        picture.data[colour] = (picture.data[colour] ?? 0) + (grain % 33) - 16;
    }
    context.putImageData(picture, 0, 0);
    const photo = await new Promise<Blob | null>((done) =>
      canvas.toBlob(done, "image/jpeg", 0.95),
    );
    // As text, which the test and the browser pass each other far faster than millions of numbers.
    return new Promise<string>((done) => {
      const reader = new FileReader();
      reader.onload = () => done(String(reader.result).split(",")[1] ?? "");
      reader.readAsDataURL(photo as Blob);
    });
  });
  const jpeg = Buffer.from(drawn, "base64");
  const note = [
    // The segment: its mark, its length (34), and the word that says what it holds.
    ...[0xff, 0xe1, 0x00, 0x22, ...Buffer.from("Exif"), 0x00, 0x00],
    // Big numbers first, and where the one list of facts starts.
    ...[0x4d, 0x4d, 0x00, 0x2a, 0x00, 0x00, 0x00, 0x08],
    // One fact: orientation (0x0112), one short number, 6: turn a quarter to the right. Then no more lists.
    ...[0x00, 0x01, 0x01, 0x12, 0x00, 0x03, 0x00, 0x00, 0x00, 0x01],
    ...[0x00, 0x06, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
  ];
  // Right after the JPEG's first two bytes, where a camera writes it.
  return Buffer.concat([
    jpeg.subarray(0, 2),
    Buffer.from(note),
    jpeg.subarray(2),
  ]);
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

  await test.step("Picha: a phone's photo comes out small and upright, and on the demo it isn't saved", async () => {
    await expect(cardPart(phone, WORKERS.photo.title)).toContainText(
      WORKERS.photo.none,
    );
    const photo = await aPhonesOwnPhoto(phone);
    // One the server would refuse as it is: it keeps none over 1 MB.
    expect(photo.length).toBeGreaterThan(1024 * 1024);
    const gallery = phone.waitForEvent("filechooser");
    await phone
      .getByRole("button", { name: WORKERS.photo.choose, exact: true })
      .click();
    await (
      await gallery
    ).setFiles({
      name: "IMG_0001.jpg",
      mimeType: "image/jpeg",
      buffer: photo,
    });

    const showing = sheet(
      phone,
      words(WORKERS.photo.sheetTitle, { name: "Zawadi" }),
    );
    const picture = showing.getByRole("img", {
      name: words(WORKERS.photo.newAlt, { name: "Zawadi" }),
    });
    await expect(picture).toBeVisible();
    // The copy that would go: standing, at most 1,600 px, a JPEG of about 150 KB (the card's box), and no Exif in it.
    const copy = await picture.evaluate(async (image) => {
      const shown = image as HTMLImageElement;
      await shown.decode();
      const file = await (await fetch(shown.src)).blob();
      const words = new TextDecoder("latin1").decode(await file.arrayBuffer());
      return {
        size: [shown.naturalWidth, shown.naturalHeight],
        type: file.type,
        bytes: file.size,
        hidden: words.includes("Exif"),
      };
    });
    expect(copy).toMatchObject({
      size: [1067, 1600],
      type: "image/jpeg",
      hidden: false,
    });
    expect(copy.bytes).toBeLessThanOrEqual(150 * 1024);

    // On the demo, shown and kept nowhere, with the one line saying why (Jack, PPL-9).
    await expect(showing.getByText(sw.errors.demo.photos_fixed)).toBeVisible();
    await expect(
      showing.getByRole("button", { name: WORKERS.photo.save, exact: true }),
    ).toBeDisabled();
    await showing
      .getByRole("button", { name: sw.sheet.cancel, exact: true })
      .click();
    await expect(showing).toBeHidden();
    await expect(cardPart(phone, WORKERS.photo.title)).toContainText(
      WORKERS.photo.none,
    );
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
