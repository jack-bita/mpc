// the-shop.ts — what the browser tests share (UI-6, SYNC-11): the demo shop's people and logins, the story's
// two browsers as fixtures, a new laptop joining the shop, and a seller logging in by PIN. Not a test itself:
// Playwright runs only *.spec.ts files.
//
// The shop is the demo's, made by the demo seed (`manage.py seed_demo`, backend/apps/demo/services.py) on an
// empty database as the test container starts, as the demo does (backend/start-demo.sh, compose.e2e.yml),
// before the tests run (scripts/run_e2e.sh): the same shop and people a visitor of the demo meets. The tests
// share that one database and run one at a time (playwright.config.ts), so each pairs a laptop of its own.
//
// The words come from the Swahili book (messages/sw.json), the app's default language, never typed here: a
// reworded button moves the tests with it, and a word the screen lost fails them.
import {
  type BrowserContext,
  test as base,
  devices,
  expect,
  type Page,
} from "@playwright/test";

import sw from "../messages/sw.json";

// The demo's logins, as the demo seed makes them (PEOPLE in backend/apps/demo/services.py), public on purpose:
// change both together. If they ever differ, a login fails at once, so the mismatch can't hide.
export const MANAGER_EMAIL = "meneja@example.com";
export const MANAGER_PASSWORD = "jaribu-demo";

/** A seller of the seed's: her tile shows her full name, her welcome her short one; her PIN is the seed's. */
export interface Seller {
  fullName: string;
  name: string;
  pin: string;
}

// Asha sells on Dawa, one of the demo's two sides, the one the manager gives each new laptop.
export const ASHA: Seller = {
  fullName: "Asha Mfano",
  name: "Asha",
  pin: "2580",
};
export const SIDE = "Dawa";

/** A sentence from the word book with its {names} filled in, as use-intl fills them on the screen. */
export function words(
  sentence: string,
  values: Record<string, string>,
): string {
  return sentence.replace(
    /\{(\w+)\}/g,
    (_, name: string) => values[name] ?? `{${name}}`,
  );
}

// The story's two browsers, as fixtures: Playwright opens each before a test that names it, and closes it
// after that test, passed or failed. After, not inside the test: Playwright takes a failed test's screenshots
// and trace first, so a red run keeps its pictures. Each is a context, a browser that never saw the site: no
// cookie, no saved device. By hand that took a second browser (UI-4: Incognito windows share one session).
// `provide`, the name Playwright's own docs call `use`: hands the fixture to the test and waits for it to end.
export const test = base.extend<{
  laptop: BrowserContext;
  managersPhone: BrowserContext;
}>({
  // The shop's new laptop, with a clock the test can move: the idle lock waits 15 minutes, and a test can't.
  // Put in before the first page, so every timer the app starts runs on it. It keeps normal time until moved.
  laptop: async ({ browser }, provide) => {
    const laptop = await browser.newContext();
    await laptop.clock.install();
    await provide(laptop);
    await laptop.close();
  },
  // The manager's own phone, at a phone's size and with touch, as UI-5's hand test could only pretend with a
  // laptop's Chrome.
  managersPhone: async ({ browser }, provide) => {
    const phone = await browser.newContext({ ...devices["Pixel 7"] });
    await provide(phone);
    await phone.close();
  },
});

export { expect };

/**
 * A new laptop joins the shop: it asks and shows a code, the manager logs in on their phone and confirms it
 * by name for the Dawa side, and the laptop then shows the shop's people. Three steps of the story, each
 * named in the report.
 */
export async function aLaptopJoins(
  counter: Page,
  phone: Page,
  laptopName: string,
): Promise<void> {
  const code =
    await test.step("a new laptop asks to join the shop and shows its code", async () => {
      await counter.goto("/");
      await expect(
        counter.getByRole("heading", { name: sw.home.title }),
      ).toBeVisible();
      await counter
        .getByRole("link", { name: sw.device.register.title, exact: true })
        .click();
      await counter
        .getByRole("button", { name: sw.device.register.start })
        .click();
      // The server made a waiting request and gave this browser its key: the code is on show, in two
      // halves to read out across the counter (codeForReading, src/features/devices/pairing.ts).
      await expect(
        counter.getByRole("heading", { name: sw.device.register.giveCode }),
      ).toBeVisible();
      const shown = counter.getByText(/^[A-Z0-9]{4}-[A-Z0-9]{4}$/);
      await expect(shown).toBeVisible();
      return shown.innerText();
    });

  await test.step("the manager logs in on their phone and confirms the code", async () => {
    await phone.goto("/login/");
    await phone.getByLabel(sw.login.password.name).fill(MANAGER_EMAIL);
    // exact: the eye beside the box is labelled "Onyesha nenosiri", which holds the word too.
    await phone
      .getByLabel(sw.login.password.password, { exact: true })
      .fill(MANAGER_PASSWORD);
    await phone
      .getByRole("button", { name: sw.login.password.send, exact: true })
      .click();
    // The office's home page, where a password's login lands (UI-5).
    await phone
      .getByRole("link", { name: sw.device.office.title, exact: true })
      .click();
    await phone
      .getByRole("button", { name: sw.device.office.register, exact: true })
      .click();
    await phone.getByLabel(sw.device.office.code).fill(code);
    await phone.getByLabel(sw.device.office.name).fill(laptopName);
    await phone.getByRole("radio", { name: SIDE }).click();
    await phone
      .getByRole("button", { name: sw.device.office.confirm, exact: true })
      .click();
    await expect(
      phone.getByText(
        words(sw.device.office.registered, { device: laptopName }),
      ),
    ).toBeVisible();
  });

  await test.step("the laptop sees the manager's yes and shows the shop's people", async () => {
    // The laptop asks every 3 seconds while it waits (WAIT_CHECK_EVERY, register-this-device.tsx), so
    // the yes can take a little longer than one look's usual 5 seconds.
    await expect(
      counter.getByRole("heading", { name: sw.device.register.done }),
    ).toBeVisible({ timeout: 10_000 });
    await counter
      .getByRole("link", { name: sw.device.register.continue })
      .click();
    await expect(
      counter.getByRole("heading", { name: sw.login.picker.title }),
    ).toBeVisible();
  });
}

/** Her tile, then her four digits: the 4th sends the PIN, with no OK key (pin-pad.tsx). The PIN screen's
 * heading is her name, so whoever tapped the wrong tile sees it before typing (pin-login.tsx). Done once her
 * welcome shows, whether the server or the laptop said yes. */
export async function logsIn(counter: Page, seller: Seller): Promise<void> {
  await counter.getByRole("button", { name: seller.fullName }).click();
  await expect(
    counter.getByRole("heading", { name: seller.fullName }),
  ).toBeVisible();
  await expect(counter.getByText(sw.login.pin.typePin)).toBeVisible();
  for (const digit of seller.pin) {
    await counter.getByRole("button", { name: digit, exact: true }).click();
  }
  await expect(
    counter.getByRole("heading", {
      name: words(sw.login.welcome, { name: seller.name }),
    }),
  ).toBeVisible();
}
