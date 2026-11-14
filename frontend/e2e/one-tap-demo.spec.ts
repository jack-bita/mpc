// one-tap-demo.spec.ts — the one-tap demo, end to end (OPS-3, BP15): a visitor who has never seen the shop goes
// from the demo's address to a clock-in made with no network in under a minute. Jaribu demo, Asha's tile with her
// PIN on it, her PIN, Mahudhurio, the network gone, Ingia kazini: no manager, no code to read out.
//
// The card's first Done when. Timed on the test's own clock, from the first page to the saved clock-in: the
// laptop's clock is Playwright's (the-shop.ts), which a test may move, and this one never does. The PIN is read off
// her tile, as a visitor reads it, never typed in from this file: if the tile showed none, or a wrong one, the
// story would stop there. It is then checked against the seed's, so the README's PIN is the one that works.
//
// The container's database holds the demo shop alone, as the seed makes it (compose.e2e.yml), so the demo is open
// there. The other stories pair laptops of their own in the same shop; this one taps, and pairs none.
import sw from "../messages/sw.json";

import { ASHA, expect, logsIn, test } from "./the-shop";

const PULL = "/api/sync/v1/pull/";
// The card's promise.
const A_MINUTE = 60_000;

test("a visitor goes from the demo link to an offline clock-in in under a minute", async ({
  laptop,
}) => {
  const counter = await laptop.newPage();
  // The laptop's first sync after the tap: the bootstrap, then a pull, which brings the last server time a
  // clock-in carries (SYNC-11). Waited for before the tap on Ingia kazini, as a tap before it would be told to
  // wait for the first sync; a visitor meets the same wait.
  const firstPull = counter.waitForResponse(
    (answer) => new URL(answer.url()).pathname === PULL && answer.ok(),
  );
  const started = Date.now();

  await test.step("the visitor opens the demo and taps Jaribu demo", async () => {
    await counter.goto("/");
    await counter
      .getByRole("button", { name: sw.device.demo.try, exact: true })
      .click();
    await expect(
      counter.getByRole("heading", { name: sw.login.picker.title }),
    ).toBeVisible();
  });

  const pin =
    await test.step("Asha's tile shows her PIN, the seed's own", async () => {
      // Her tile, by the start of its name: the rest, her nickname and her PIN, is what this step reads.
      const tile = counter.getByRole("button", { name: ASHA.fullName });
      await expect(tile).toBeVisible();
      const shown = sw.login.picker.demoPin.replace("{pin}", "(\\d{4})");
      const read = new RegExp(shown).exec((await tile.textContent()) ?? "");
      expect(read?.[1]).toBe(ASHA.pin);
      return read?.[1] ?? "";
    });

  await test.step("Asha logs in with the PIN her tile showed", async () => {
    await logsIn(counter, { ...ASHA, pin });
  });

  await test.step("the network goes, and Asha clocks in", async () => {
    await counter
      .getByRole("link", { name: sw.attendance.title, exact: true })
      .click();
    await expect(
      counter.getByRole("heading", { level: 1, name: sw.attendance.title }),
    ).toBeVisible();
    await firstPull;
    await laptop.setOffline(true);

    await counter
      .getByRole("button", { name: sw.attendance.clockIn, exact: true })
      .click();

    // Saved on the laptop, with no network: the screen says when ("Umeingia kazini saa 07:55 asubuhi."), and
    // that it waits to be sent.
    const [before, after] = sw.attendance.savedIn
      .split("{time}")
      .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    await expect(
      counter.getByText(
        new RegExp(`^${before ?? ""}\\d{2}:\\d{2} [a-z]+${after ?? ""}$`),
      ),
    ).toBeVisible();
    await expect(
      counter.getByText(sw.attendance.sendNow.offline),
    ).toBeVisible();
  });

  expect(Date.now() - started).toBeLessThan(A_MINUTE);
});
