// device-health.spec.ts — the outage log, end to end (SYNC-14, 03 §6.11): a laptop ten minutes offline shows,
// after its next sync, as one outage of about ten minutes on the manager's Hali ya vifaa. The whole road of one
// period: the browser's offline event, the laptop's note in its own database, kept up at each 30 s moment, closed
// when the server answers again, sent with the next push, kept by the server, and shown on the office page.
//
// The card's first Done when. Playwright takes the laptop off the network as a whole (setOffline), as a router
// whose power went would, and runs the laptop's clock ten minutes on (runFor), firing every moment on the way, as
// ten real minutes would; fastForward would fire each timer once only, and the app would seem to have been away.
//
// One more thing the story shows for free: the laptop's clock, moved on ten minutes, is then ten minutes ahead of
// the server's, and its push says so (SYNC-14's clock error). The page shows it, in its warning colour.
//
// The shop, the people, the two browsers and the joining steps are shared (the-shop.ts).
import sw from "../messages/sw.json";

import { aLaptopJoins, expect, test } from "./the-shop";

const PUSH = "/api/sync/v1/push/";
// The name the manager gives this story's laptop: the tests share one database, so each pairs its own.
const LAPTOP = "Laptop Hali";
const MINUTE = 60_000;

/** A sentence of the word book as a pattern, each {name} standing for any words, the rest taken as it is. */
function shaped(sentence: string): RegExp {
  const plain = sentence.replace(/[.*+?^$()|[\]\\]/g, "\\$&");
  return new RegExp(`^${plain.replace(/\{\w+\}/g, ".+")}$`);
}

test("ten minutes offline shows as one outage of about ten minutes after the next sync", async ({
  laptop,
  managersPhone,
}) => {
  const counter = await laptop.newPage();
  const phone = await managersPhone.newPage();

  // The laptop's first push, right after the manager's yes: waited for from before it joins, as it may come
  // before the joining steps end. Its report is the server's first word on this laptop.
  const firstPush = counter.waitForResponse(
    (answer) =>
      new URL(answer.url()).pathname === PUSH &&
      answer.request().method() === "POST" &&
      answer.ok(),
  );
  await aLaptopJoins(counter, phone, LAPTOP);

  await test.step("the laptop syncs once with the network, so the server has its first report", async () => {
    // A push needs the CSRF token the device check brings, a moment after the yes (sync.ts): if the first sync
    // went before it, the next 30 s moment pushes, run here on the laptop's clock rather than waited for.
    await laptop.clock.runFor(30_000);
    await firstPush;
  });

  await test.step("the network goes for ten minutes, the laptop left open", async () => {
    await laptop.setOffline(true);
    await laptop.clock.runFor(10 * MINUTE);
  });

  await test.step("the network comes back, and the next sync sends the period", async () => {
    // Back: the laptop syncs at once, and that sync's answer closes the period. The push that carries it is the
    // next one, at the next 30 s moment, run here on the laptop's clock.
    const carried = counter.waitForRequest(
      (request) =>
        new URL(request.url()).pathname === PUSH &&
        request.method() === "POST" &&
        (request.postDataJSON() as { outages: unknown[] }).outages.length > 0,
    );
    await laptop.setOffline(false);
    await laptop.clock.runFor(30_000);
    const sent = (await carried).postDataJSON() as {
      outages: { started_at: string; ended_at: string }[];
    };
    expect(sent.outages).toHaveLength(1);
    const [period] = sent.outages;
    const lasted =
      Date.parse(period?.ended_at ?? "") - Date.parse(period?.started_at ?? "");
    // About ten minutes: the moments land within seconds of the network's going and coming back.
    expect(lasted).toBeGreaterThan(9 * MINUTE);
    expect(lasted).toBeLessThan(11 * MINUTE);
  });

  await test.step("the manager's phone shows it on Hali ya vifaa", async () => {
    await phone.goto("/office/");
    await phone
      .getByRole("link", { name: sw.device.health.title, exact: true })
      .click();
    await expect(
      phone.getByRole("heading", { level: 1, name: sw.device.health.title }),
    ).toBeVisible();
    const card = phone
      .locator("[data-slot=card]")
      .filter({ has: phone.getByRole("heading", { name: LAPTOP }) });
    // One cut, about ten minutes long: the server keeps it once, however often it was sent.
    await expect(
      card.getByText(
        new RegExp(
          `^${sw.device.health.outages
            .replace("{count}", "1")
            .replace("{total}", "dakika (9|10|11)")
            .replace(/[.]/g, "\\.")}$`,
        ),
      ),
    ).toBeVisible();
    await expect(card.getByRole("listitem")).toHaveCount(1);
    // Its clock, moved on ten minutes, now runs ahead of the server's.
    await expect(
      card.getByText(shaped(sw.device.health.clockAhead)),
    ).toBeVisible();
  });
});
