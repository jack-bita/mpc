// clock-in-photo.spec.ts — the clock-in's photo in a real browser (ATT-3, 03 §5.13): Asha sees her face live
// on Mahudhurio, taps Ingia kazini, and sees the photo taken. On the demo, which these tests run on
// (compose.e2e.yml, DEMO_SEED=yes), it never leaves the laptop (Jack: A): every visitor shares Meneja's
// login, which opens clock-in photos.
//
// Two things only a real browser can prove, which the unit tests' jsdom can't: the camera's live picture,
// and the shrinking's drawing (shrink-photo.ts): the photo comes out a JPEG under 1 MB with none of a camera's
// hidden data (no Exif block). The camera is Chromium's pretend one (playwright.config.ts), its picture made
// up, never a face, and smaller than 1,600 px: so the photo is never brought down here, and its longest side
// within 1,600 px only shows nothing grew; bringing a bigger frame down is fitWithin's, in shrink-photo.test.ts.
//
// Honest limit: on the demo no photo goes up, so the upload road (the label in the push, the file after it)
// is proven by the server's tests (apps/sync/tests/test_clock_photo.py, CTRL-3's test_attachment_route.py),
// the laptop's (attendance.test.tsx, sync/attachments.send.test.ts), and Jack's hand test on a laptop that
// isn't the demo.
import sw from "../messages/sw.json";
import type { components } from "../src/api/schema";

import type { Page } from "@playwright/test";

import { aLaptopJoins, ASHA, expect, logsIn, test } from "./the-shop";

type PushBatch = components["schemas"]["PushBatchRequest"];
type PushAnswer = components["schemas"]["PushAnswer"];

const PUSH = "/api/sync/v1/push/";
const PULL = "/api/sync/v1/pull/";
const PHOTOS = "/api/sync/v1/attachments/";
// The tests share one database, so each pairs its own laptop.
const LAPTOP = "Laptop Picha";

/** How many photos wait on the laptop to go up (attachment_files, CTRL-6), read from its own database inside
 * the page: none means none can ever be sent. */
function photosWaitingOnTheLaptop(counter: Page): Promise<number> {
  return counter.evaluate(async () => {
    // The shop's database is named by the shop's id, from the device's saved copy (this-device.ts, db.ts).
    const saved = JSON.parse(localStorage.getItem("mpc.device") ?? "null") as {
      device?: { shop?: { id?: string } };
    } | null;
    const shopId = saved?.device?.shop?.id;
    if (shopId === undefined) throw new Error("This laptop has no shop.");
    return new Promise<number>((done, failed) => {
      const opening = indexedDB.open(`mpc-shop-${shopId}`);
      opening.onerror = () => failed(opening.error);
      opening.onsuccess = () => {
        const db = opening.result;
        const counting = db
          .transaction("attachment_files")
          .objectStore("attachment_files")
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

test("a clock-in's photo is taken and shown, and on the demo never leaves the laptop", async ({
  laptop,
  managersPhone,
}) => {
  const counter = await laptop.newPage();
  const phone = await managersPhone.newPage();

  // Every request to the photos' door: on the demo there must be none, ever.
  const photosSent: string[] = [];
  counter.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith(PHOTOS))
      photosSent.push(request.url());
  });

  const firstPull = counter.waitForResponse(
    (answer) => new URL(answer.url()).pathname === PULL && answer.ok(),
  );
  await aLaptopJoins(counter, phone, LAPTOP);
  await firstPull;

  const live = counter.getByLabel(sw.attendance.camera.live);

  await test.step("Asha opens Mahudhurio, and sees her face live above the button", async () => {
    await logsIn(counter, ASHA);
    await counter
      .getByRole("link", { name: sw.attendance.title, exact: true })
      .click();
    await expect(live).toBeVisible();
    // Playing: the camera's frames reach the <video>, which knows their size once the first has come.
    await expect
      .poll(() => live.evaluate((video: HTMLVideoElement) => video.videoWidth))
      .toBeGreaterThan(0);
    // No line about a camera that can't ("Hakuna kamera: …"): this one can.
    const noCamera = sw.attendance.camera.no_camera.split(":")[0] ?? "";
    await expect(counter.getByText(noCamera)).toHaveCount(0);
  });

  // The push that carries her clock-in, with what it sent and the server's answer.
  const clockInPush = counter.waitForResponse(
    (answer) =>
      new URL(answer.url()).pathname === PUSH &&
      answer.request().method() === "POST" &&
      answer.ok() &&
      (answer.request().postDataJSON() as PushBatch).documents.some(
        (document) => document.type === "clock",
      ),
  );

  // On the demo, named as the photo just taken: it is kept nowhere.
  const photo = counter.getByRole("img", { name: sw.attendance.photo.taken });

  await test.step("she taps Ingia kazini: the photo shows, and the camera goes off", async () => {
    await counter
      .getByRole("button", { name: sw.attendance.clockIn, exact: true })
      .click();
    await expect(photo).toBeVisible();
    await expect(counter.getByText(sw.attendance.photo.demo)).toBeVisible();
    // The live picture is gone with the button. That the camera's light is off, its tracks stopped, is the
    // camera hook's own tests' (use-camera.test.ts): a page can't see the light.
    await expect(live).toHaveCount(0);
  });

  await test.step("the photo is a small JPEG with none of the camera's hidden data", async () => {
    // Read inside the page, from the address the screen shows it at: the very bytes the tap would have kept.
    const facts = await photo.evaluate(async (image: HTMLImageElement) => {
      const bytes = new Uint8Array(
        await (await fetch(image.src)).arrayBuffer(),
      );
      const drawn = await createImageBitmap(new Blob([bytes]));
      // An Exif block opens with the letters "Exif" and two zero bytes, in the file's first part.
      const exif = [0x45, 0x78, 0x69, 0x66, 0, 0];
      const head = bytes.subarray(0, 64 * 1024);
      const hasExif = head.some((_, at) =>
        exif.every((byte, step) => head[at + step] === byte),
      );
      return {
        jpeg: bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff,
        size: bytes.length,
        longest: Math.max(drawn.width, drawn.height),
        hasExif,
      };
    });
    expect(facts.jpeg).toBe(true);
    expect(facts.size).toBeGreaterThan(0);
    expect(facts.size).toBeLessThan(1_048_576);
    expect(facts.longest).toBeGreaterThan(0);
    expect(facts.longest).toBeLessThanOrEqual(1600);
    expect(facts.hasExif).toBe(false);
  });

  await test.step("the tap reaches the server marked demo, and no photo is ever sent", async () => {
    const pushed = await clockInPush;
    const sent = pushed.request().postDataJSON() as PushBatch;
    const tap = sent.documents.find((document) => document.type === "clock");
    expect(tap?.schema_version).toBe(2);
    expect(tap?.payload).toMatchObject({ kind: "in", no_photo: "demo" });
    expect(tap?.payload).not.toHaveProperty("photo");
    const answer = (await pushed.json()) as PushAnswer;
    expect(answer.answers.map((each) => each.status)).toEqual(["accepted"]);
    // No photo waits on the laptop, so none can ever go; and none went.
    expect(await photosWaitingOnTheLaptop(counter)).toBe(0);
    expect(photosSent).toEqual([]);
  });
});
