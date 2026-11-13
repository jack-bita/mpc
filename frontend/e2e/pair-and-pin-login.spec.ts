// pair-and-pin-login.spec.ts — the counter's way in, in a real browser against the real server (UI-6).
//
// The story every shop morning depends on: a new laptop asks to join the shop and shows a code; the
// manager types it on their phone; the laptop shows the shop's people; a seller logs in with her PIN; the
// laptop locks itself when nobody touches it; she logs in again, and logs out. A change that breaks any
// of it fails here, before the merge, instead of at the counter. Stage 1's own goal is this test (04).
//
// The shop, the people, the two browsers and the joining steps are shared with the other stories
// (the-shop.ts, SYNC-11).
import sw from "../messages/sw.json";
import type { components } from "../src/api/schema";

import { aLaptopJoins, ASHA, expect, logsIn, test, words } from "./the-shop";

// The name the manager gives the new laptop.
const LAPTOP = "Laptop Dawa";
// The shop's idle minutes when it sets none: `session.idle_minutes` (backend/apps/core/settings_registry.py),
// which a PIN's session takes at its login and `me` sends as `idle_minutes`. The test checks the server says
// this number, then jumps the clock by it.
const IDLE_MINUTES = 15;

test("pair a laptop, log in by PIN, lock when idle, log in again, log out", async ({
  laptop,
  managersPhone,
}) => {
  const counter = await laptop.newPage();
  const phone = await managersPhone.newPage();

  const welcome = counter.getByRole("heading", {
    name: words(sw.login.welcome, { name: ASHA.name }),
  });
  const tiles = counter.getByRole("heading", { name: sw.login.picker.title });

  await aLaptopJoins(counter, phone, LAPTOP);

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
    await logsIn(counter, ASHA);
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
    await logsIn(counter, ASHA);
    await counter
      .getByRole("button", { name: sw.login.logout, exact: true })
      .click();
    await expect(tiles).toBeVisible();
    await expect(welcome).toBeHidden();
  });
});
