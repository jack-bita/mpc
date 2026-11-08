// pair-and-pin-login.spec.ts — the counter's way in, in a real browser against the real server (UI-6).
//
// The story every shop morning depends on: a new laptop asks to join the shop and shows a code; the
// manager types it on their phone; the laptop shows the shop's people; a seller logs in with her PIN; the
// laptop locks itself when nobody touches it; she logs in again, and logs out. A change that breaks any
// of it fails here, before the merge, instead of at the counter. Stage 1's own goal is this test (04).
//
// The shop it logs in to is the demo's, made by the demo seed (`manage.py seed_demo`, backend/apps/demo/services.py)
// on an empty database as the test container starts, as the demo does (backend/start-demo.sh, compose.e2e.yml),
// before the tests run (scripts/run_e2e.sh): the same shop and people a visitor of the demo meets. The words come from the Swahili book (messages/sw.json), the app's default
// language, never typed here: a reworded button moves the test with it, and a word the screen lost fails
// the test.
import {
  type BrowserContext,
  test as base,
  devices,
  expect,
} from "@playwright/test";

import sw from "../messages/sw.json";
import type { components } from "../src/api/schema";

// The demo's logins, as the demo seed makes them (PEOPLE in backend/apps/demo/services.py), public on purpose:
// change both together. If they ever differ, a login below fails at once, so the mismatch can't hide.
const MANAGER_EMAIL = "meneja@example.com";
const MANAGER_PASSWORD = "jaribu-demo";
const SELLER_PIN = "2580";
// Names the seed gives: Asha's tile shows her full name, her welcome her short one. Asha sells on Dawa, one of
// the demo's two sides, the one the manager gives the new laptop.
const SELLER_FULL_NAME = "Asha Mfano";
const SELLER = "Asha";
const SIDE = "Dawa";
// The name the manager gives the new laptop.
const LAPTOP = "Laptop Dawa";
// The shop's idle minutes when it sets none: `session.idle_minutes` (backend/apps/core/settings_registry.py),
// which a PIN's session takes at its login and `me` sends as `idle_minutes`. The test checks the server says
// this number, then jumps the clock by it.
const IDLE_MINUTES = 15;

/** A sentence from the word book with its {names} filled in, as use-intl fills them on the screen. */
function words(sentence: string, values: Record<string, string>): string {
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
const test = base.extend<{
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

test("pair a laptop, log in by PIN, lock when idle, log in again, log out", async ({
  laptop,
  managersPhone,
}) => {
  const counter = await laptop.newPage();
  const phone = await managersPhone.newPage();

  const welcome = counter.getByRole("heading", {
    name: words(sw.login.welcome, { name: SELLER }),
  });
  const tiles = counter.getByRole("heading", { name: sw.login.picker.title });

  // Asha's tile, then her four digits: the 4th sends the PIN, with no OK key (pin-pad.tsx). The PIN screen's
  // heading is her name, so whoever tapped the wrong tile sees it before typing (pin-login.tsx).
  async function ashaLogsIn() {
    await counter.getByRole("button", { name: SELLER_FULL_NAME }).click();
    await expect(
      counter.getByRole("heading", { name: SELLER_FULL_NAME }),
    ).toBeVisible();
    await expect(counter.getByText(sw.login.pin.typePin)).toBeVisible();
    for (const digit of SELLER_PIN) {
      await counter.getByRole("button", { name: digit, exact: true }).click();
    }
    await expect(welcome).toBeVisible();
  }

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
    await phone.getByLabel(sw.device.office.name).fill(LAPTOP);
    await phone.getByRole("radio", { name: SIDE }).click();
    await phone
      .getByRole("button", { name: sw.device.office.confirm, exact: true })
      .click();
    await expect(
      phone.getByText(words(sw.device.office.registered, { device: LAPTOP })),
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
    await expect(tiles).toBeVisible();
  });

  await test.step("Asha logs in with her PIN", async () => {
    // `me`'s first yes after her PIN: who is here, and how long her screen may sit untouched. Read here, as
    // the jump below would lock the laptop just as well if the server said 1 minute by mistake, which
    // would lock Asha out in the middle of a sale. Before the PIN, `me` answers "not logged in", never ok.
    const here = counter.waitForResponse(
      (answer) =>
        new URL(answer.url()).pathname === "/api/auth/me/" &&
        answer.request().method() === "GET" &&
        answer.ok(),
    );
    await ashaLogsIn();
    const asha = (await (
      await here
    ).json()) as components["schemas"]["WhoIsHere"];
    expect(asha.idle_minutes).toBe(IDLE_MINUTES);
  });

  await test.step("the laptop locks itself when nobody touches it", async () => {
    // As if the laptop sat untouched for the shop's idle minutes: the clock jumps, and every timer due
    // on the way fires once, the lock's look at the clock among them (idle-lock.ts). The same as a lid
    // closed and opened again, which is why the lock is a watch, not an egg timer.
    await laptop.clock.fastForward(`${IDLE_MINUTES}:00`);
    // The lock logged her out on the server too: the tiles are back, and her welcome is gone.
    await expect(tiles).toBeVisible();
    await expect(welcome).toBeHidden();
  });

  await test.step("Asha logs in again, then logs out", async () => {
    await ashaLogsIn();
    await counter
      .getByRole("button", { name: sw.login.logout, exact: true })
      .click();
    await expect(tiles).toBeVisible();
    await expect(welcome).toBeHidden();
  });
});
