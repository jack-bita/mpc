// clock-in-offline.spec.ts — the walking skeleton, end to end (SYNC-11, 03 §16 step 6): a clock-in made with no
// network is kept on the laptop through a reload, and reaches the server once, and only once, when the network
// is back. The whole road of one record: the screen, the laptop's database, the outbox, the push, the server's
// posting, its answer.
//
// The card's exit test: offline → clock in → reload → still there → online → exactly one event on the server;
// pushing again changes nothing. Playwright takes the laptop off the network as a whole (setOffline), as a
// router whose line dropped would, and puts it back.
//
// Honest limit: the test can't look inside the server's database. It reads the server's answers instead,
// which are its word on what it kept: the clock-in answered `accepted` by exactly one push, and the same push
// sent again answered `duplicate`, with `accepted` as its first answer. That the answer log saves nothing a
// second time is the server's own tests' (SYNC-4, ATT-1).
//
// The shop, the people, the two browsers and the joining steps are shared (the-shop.ts).
import type { Page } from "@playwright/test";

import sw from "../messages/sw.json";
import type { components } from "../src/api/schema";

import { aLaptopJoins, ASHA, expect, logsIn, test } from "./the-shop";

type PushBatch = components["schemas"]["PushBatchRequest"];
type PushAnswer = components["schemas"]["PushAnswer"];

const PUSH = "/api/sync/v1/push/";
const PULL = "/api/sync/v1/pull/";
// The name the manager gives this story's laptop: the tests share one database, so each pairs its own.
const LAPTOP = "Laptop Mahudhurio";

/** A sentence of the word book as a pattern, its {time} standing for a time of day ("07:55"), caught. */
function withATime(sentence: string): RegExp {
  // The sentence's own signs, its full stop among them, taken as they are.
  const plain = sentence.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^${plain.replace("\\{time\\}", "(\\d{2}:\\d{2})")}$`);
}

/** A plural sentence's words for one ("Kumbukumbu 1 inasubiri kutumwa."), as use-intl picks them. */
function forOne(sentence: string): string {
  const one = /one \{([^}]*)\}/.exec(sentence)?.[1];
  if (one === undefined) throw new Error(`No words for one in: ${sentence}`);
  return one.replace("#", "1");
}

/** The minutes left in the day in Dar es Salaam, the demo shop's zone, at `now`. */
function minutesLeftInDarsDay(now: number): number {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Africa/Dar_es_Salaam",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const part = (type: string) =>
    Number(parts.find((each) => each.type === type)?.value ?? "0");
  return 24 * 60 - (part("hour") * 60 + part("minute"));
}

/** How many PIN checks the laptop keeps (SYNC-10), read from its own database inside the page. */
function pinChecksOnTheLaptop(counter: Page): Promise<number> {
  return counter.evaluate(async () => {
    // The shop's database is named by the shop's id, from the device's saved copy (this-device.ts, db.ts).
    const saved = JSON.parse(localStorage.getItem("mpc.device") ?? "null") as {
      device?: { shop?: { id?: string } };
    } | null;
    const shopId = saved?.device?.shop?.id;
    if (shopId === undefined) return 0;
    return new Promise<number>((done, failed) => {
      const opening = indexedDB.open(`mpc-shop-${shopId}`);
      opening.onerror = () => failed(opening.error);
      opening.onsuccess = () => {
        const db = opening.result;
        if (!db.objectStoreNames.contains("pin_checks")) {
          db.close();
          done(0);
          return;
        }
        const counting = db
          .transaction("pin_checks")
          .objectStore("pin_checks")
          .count();
        counting.onsuccess = () => {
          db.close();
          done(counting.result);
        };
        counting.onerror = () => failed(counting.error);
      };
    });
  });
}

test("a clock-in made offline survives a reload and reaches the server once", async ({
  laptop,
  managersPhone,
}) => {
  const counter = await laptop.newPage();
  const phone = await managersPhone.newPage();

  // Every push the laptop sends, with what it sent and the server's answers, kept as the story goes.
  const pushes: Promise<{ sent: PushBatch; answers: PushAnswer["answers"] }>[] =
    [];
  counter.on("response", (response) => {
    const request = response.request();
    if (
      new URL(response.url()).pathname !== PUSH ||
      request.method() !== "POST" ||
      !response.ok()
    )
      return;
    pushes.push(
      (response.json() as Promise<PushAnswer>).then((answer) => ({
        sent: request.postDataJSON() as PushBatch,
        answers: answer.answers,
      })),
    );
  });
  /** The pushes that carried a clock-in. */
  const pushesWithAClockIn = async () =>
    (await Promise.all(pushes)).filter((push) =>
      push.sent.documents.some((document) => document.type === "clock"),
    );
  // Every push the laptop tried to send with a clock-in, answered or not: with no network, no answer comes,
  // so only the try can show that something went out.
  let clockInPushesTried = 0;
  counter.on("request", (request) => {
    if (
      new URL(request.url()).pathname === PUSH &&
      request.method() === "POST" &&
      (request.postDataJSON() as PushBatch).documents.some(
        (document) => document.type === "clock",
      )
    )
      clockInPushesTried += 1;
  });

  const tiles = counter.getByRole("heading", { name: sw.login.picker.title });
  const mahudhurio = counter.getByRole("heading", {
    level: 1,
    name: sw.attendance.title,
  });
  const oneWaiting = counter.getByText(forOne(sw.attendance.sendNow.waiting));

  // The laptop's first sync, right after the manager's yes: the bootstrap, then a pull, which brings the last
  // server time a clock-in carries. Waited for, as a tap before it would be told to wait for the first sync.
  const firstPull = counter.waitForResponse(
    (answer) => new URL(answer.url()).pathname === PULL && answer.ok(),
  );
  await aLaptopJoins(counter, phone, LAPTOP);

  await test.step("Asha logs in once with the network, so the laptop keeps its check of her PIN", async () => {
    await firstPull;
    // The app's own copy, the service worker, now looks after the page: a reload with no network is served
    // from it (SPIKE-1). Not before its first files are all kept, as it takes over only once installed.
    await counter.waitForFunction(
      () => navigator.serviceWorker.controller !== null,
    );
    await logsIn(counter, ASHA);
    // The check is saved after the server's yes, on its own (rememberPin, pin-login.tsx): the welcome can come
    // first. Without it, the laptop could not let her in offline.
    await expect.poll(() => pinChecksOnTheLaptop(counter)).toBe(1);
    await counter
      .getByRole("button", { name: sw.login.logout, exact: true })
      .click();
    await expect(tiles).toBeVisible();
  });

  const time =
    await test.step("the network goes; Asha logs in on the laptop's own check and clocks in", async () => {
      // A story that started a few minutes before Dar's midnight would tap on one day and reload on the
      // next, where the list starts empty. The laptop's clock then moves past midnight first: only the
      // laptop's, which the server's time check may flag, and still takes.
      const left = minutesLeftInDarsDay(Date.now());
      if (left <= 3) await laptop.clock.fastForward((left + 1) * 60_000);
      await laptop.setOffline(true);
      await logsIn(counter, ASHA);
      await counter
        .getByRole("link", { name: sw.attendance.title, exact: true })
        .click();
      await expect(mahudhurio).toBeVisible();
      await expect(counter.getByText(sw.attendance.notInYet)).toBeVisible();

      await counter
        .getByRole("button", { name: sw.attendance.clockIn, exact: true })
        .click();

      const saved = counter.getByText(withATime(sw.attendance.savedIn));
      await expect(saved).toBeVisible();
      // Saved on the laptop, waiting: the screen says so, and that it goes once the network is back.
      await expect(oneWaiting).toBeVisible();
      await expect(
        counter.getByText(sw.attendance.sendNow.offline),
      ).toBeVisible();
      const shown = withATime(sw.attendance.savedIn).exec(
        await saved.innerText(),
      )?.[1];
      expect(shown).toBeDefined();
      return shown ?? "";
    });

  await test.step("a reload keeps it: the PIN again, and her clock-in is still there", async () => {
    // The reload ends her local session, as Jack chose (SYNC-10): the counter sends her to the tiles.
    await counter.reload();
    await expect(tiles).toBeVisible();
    await logsIn(counter, ASHA);
    await counter
      .getByRole("link", { name: sw.attendance.title, exact: true })
      .click();
    await expect(mahudhurio).toBeVisible();

    // In, since the time she tapped, so the button that fits is Toka kazini; in today's list; still waiting.
    await expect(
      counter.getByText(withATime(sw.attendance.inSince)),
    ).toHaveText(sw.attendance.inSince.replace("{time}", time));
    await expect(
      counter.getByRole("button", {
        name: sw.attendance.clockOut,
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      counter.getByRole("row", { name: `${ASHA.name} ${time}` }),
    ).toBeVisible();
    await expect(oneWaiting).toBeVisible();
    // The laptop didn't even try to send it while the network was gone: no sync runs then (triggers.tsx).
    expect(clockInPushesTried).toBe(0);
  });

  const accepted =
    await test.step("the network is back: the clock-in goes, and the server takes it once", async () => {
      await laptop.setOffline(false);

      // The network's return is a moment of the sync's own (triggers.tsx): no press of Tuma sasa needed.
      await expect(
        counter.getByText(sw.attendance.sendNow.allSent),
      ).toBeVisible({ timeout: 20_000 });
      const carried = await pushesWithAClockIn();
      expect(carried).toHaveLength(1);
      const [push] = carried;
      const clockIn = push?.sent.documents.find(
        (document) => document.type === "clock",
      );
      expect(clockIn?.payload).toMatchObject({ kind: "in" });
      expect(push?.answers).toEqual([
        expect.objectContaining({ id: clockIn?.id, status: "accepted" }),
      ]);
      return { sent: push?.sent, id: clockIn?.id };
    });

  await test.step("the same push sent again changes nothing", async () => {
    // As a push whose answer was lost on the way is sent again (SYNC-4): through the laptop's own browser,
    // with its key in its cookie and its CSRF token, as the app sends one.
    const csrf = (await laptop.cookies()).find(
      (cookie) => cookie.name === "csrftoken",
    )?.value;
    const again = await laptop.request.post(PUSH, {
      data: accepted.sent,
      headers: { "X-CSRFToken": csrf ?? "" },
    });

    expect(again.ok()).toBe(true);
    const answer = (await again.json()) as PushAnswer;
    expect(answer.answers).toEqual([
      expect.objectContaining({
        id: accepted.id,
        status: "duplicate",
        first: "accepted",
      }),
    ]);
    // And the laptop never sent it a second time itself.
    const carried = await pushesWithAClockIn();
    expect(
      carried
        .flatMap((push) => push.answers)
        .filter(
          (each) => each.id === accepted.id && each.status === "accepted",
        ),
    ).toHaveLength(1);
  });
});
