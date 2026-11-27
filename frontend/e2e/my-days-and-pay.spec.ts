// my-days-and-pay.spec.ts — Siku na malipo yangu on the demo, end to end (WAGE-4): Asha logs in by PIN on a new shop
// laptop, taps Siku na malipo yangu on her welcome, reads her own month, opens a day in its sheet and closes it with
// Funga, then reads her pay on the Malipo tab, with no one else's name anywhere; the server says to keep none of it, and
// after Toka the laptop's caches hold nothing of the API. Through the real server: the demo seed's three weeks of taps
// (DATA-8), her rate, the worker's own routes (MineViewSet) and the page, with its service worker.
//
// It only reads, so it leaves the shop as it found it, and reads nothing another test must have done: the tests share
// one database (the-shop.ts) and run one at a time, file by file in their names' order (playwright.config.ts). Earlier
// files decide Asha's days, fix her taps and cross out a correction of hers; none approves her month, which
// payslip.spec.ts does, after this one. On a month's first days no day of this month is over: the test goes back a month,
// as a person would, so it never reads the clock of the machine it runs on.
import sw from "../messages/sw.json";

import { aLaptopJoins, ASHA, expect, logsIn, test } from "./the-shop";

const MINE = sw.mine;
const MONTH = sw.attendanceMonth;
const WORKER = sw.attendanceWorker;

test("Asha reads her own days and pay at the laptop, and the laptop keeps none of it", async ({
  laptop,
  managersPhone,
}) => {
  const counter = await laptop.newPage();
  const phone = await managersPhone.newPage();
  // Every answer of her own routes, as the browser got it, to read what the server told it to keep.
  const ownAnswers: { url: string; cacheControl: string }[] = [];
  counter.on("response", (reply) => {
    if (reply.url().includes("/api/v1/staffpay/mine/"))
      ownAnswers.push({
        url: reply.url(),
        cacheControl: reply.headers()["cache-control"] ?? "",
      });
  });
  // A day of hers counted on time, as its button names it: "Jumatano 18/11: kwa wakati".
  const onTime = counter.getByRole("button", {
    name: new RegExp(`: ${MONTH.kind.on_time}$`),
  });

  await aLaptopJoins(counter, phone, "Laptop ya siku zangu");

  await test.step("Asha logs in by PIN and opens Siku na malipo yangu from her welcome", async () => {
    await logsIn(counter, ASHA);
    await counter.getByRole("link", { name: MINE.title, exact: true }).click();
    await expect(
      counter.getByRole("heading", { level: 1, name: MINE.title }),
    ).toBeVisible();
    await expect(
      counter.getByRole("table", { name: /^Siku za Asha, / }),
    ).toBeVisible();
    // On a month's first days nothing is over yet: the month before, which the seed's weeks reach.
    if ((await onTime.count()) === 0) {
      await counter
        .getByRole("button", { name: MONTH.before, exact: true })
        .click();
      await expect(onTime.first()).toBeVisible();
    }
  });

  await test.step("a day of hers opens in a sheet with its taps, and Funga closes it", async () => {
    await onTime.first().click();
    const sheet = counter.getByRole("dialog");
    await expect(sheet).toBeVisible();
    // Her taps of the day, from the seed's laptop, each with its time and the laptop.
    const taps = sheet.getByRole("list", { name: WORKER.tapsLabel });
    await expect(taps.getByRole("listitem").first()).toContainText(
      WORKER.tapKind.in,
    );
    await expect(taps).toContainText("Laptop ya Dawa");
    // Only to read: Funga, and nothing else.
    await expect(sheet.getByRole("button")).toHaveText([sw.sheet.close]);
    await sheet.getByRole("button", { name: sw.sheet.close }).click();
    await expect(sheet).toBeHidden();
  });

  await test.step("Malipo: her pay of the month, not approved yet, and no one else's", async () => {
    await counter.getByRole("tab", { name: MINE.pay, exact: true }).click();
    const lines = counter.getByRole("table", { name: sw.pay.linesCaption });
    await expect(lines).toBeVisible();
    // Her own rate, the seed's 10,000 a day (PEOPLE, backend/apps/demo/services.py).
    await expect(lines).toContainText("× 10,000");
    await expect(
      counter.getByText(MINE.notApproved, { exact: true }),
    ).toBeVisible();
    // The other seller's name nowhere on her page.
    await expect(counter.locator("main")).not.toContainText("Baraka");
  });

  await test.step("the server said to keep none of it, and after Toka the laptop holds nothing of the API", async () => {
    expect(ownAnswers.length).toBeGreaterThan(0);
    for (const { url, cacheControl } of ownAnswers)
      expect(cacheControl, url).toContain("no-store");
    await counter
      .getByRole("button", { name: sw.login.logout, exact: true })
      .click();
    await expect(
      counter.getByRole("heading", { name: sw.login.picker.title }),
    ).toBeVisible();
    // Every address the laptop's caches keep: the service worker's copies of the app's own files, never an answer.
    const kept = await counter.evaluate(async () => {
      const urls: string[] = [];
      for (const name of await caches.keys()) {
        const cache = await caches.open(name);
        for (const request of await cache.keys()) urls.push(request.url);
      }
      return urls;
    });
    expect(kept.filter((url) => url.includes("/api/"))).toEqual([]);
  });
});
