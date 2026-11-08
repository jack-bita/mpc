// pair-and-pin-login.spec.ts — the counter's way in, in a real browser against the real server (UI-6).
//
// The story every shop morning depends on: a new laptop asks to join the shop and shows a code; the
// manager types it on their phone; the laptop shows the shop's people; a seller logs in with her PIN; the
// laptop locks itself when nobody touches it; she logs in again, and logs out. A change that breaks any
// of it fails here, before the merge, instead of at the counter.
//
// The words come from the Swahili book (messages/sw.json), the app's default language, never typed here:
// a reworded button moves the test with it, and a word the screen lost fails the test.
import { expect, test } from "@playwright/test";

import sw from "../messages/sw.json";

test("a new laptop asks to join the shop and shows its code", async ({
  browser,
}) => {
  // A context is a browser that never saw the site: no cookie, no saved device, like a laptop fresh from
  // its box. By hand that took a second browser (UI-4: Incognito windows share one session).
  const laptop = await browser.newContext();
  const page = await laptop.newPage();

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: sw.home.title }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: sw.device.register.title, exact: true })
    .click();
  await page.getByRole("button", { name: sw.device.register.start }).click();

  // The server made a waiting request and gave this browser its key: the code is on show, in two halves
  // to read out across the counter (codeForReading, src/features/devices/pairing.ts).
  await expect(
    page.getByRole("heading", { name: sw.device.register.giveCode }),
  ).toBeVisible();
  await expect(page.getByText(/^[A-Z0-9]{4}-[A-Z0-9]{4}$/)).toBeVisible();

  await laptop.close();
});
