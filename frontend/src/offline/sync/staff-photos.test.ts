// staff-photos.test.ts — the workers' photos come down for their tiles (PPL-14, 03 §5.13): each one a staff row names
// and the laptop lacks, asked for once and kept; each one no row names any more, dropped; a photo that doesn't come
// waits longer after each try, and never stops a sync; Wi-Fi first; and a sync fetches them last, after the pull.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRefusal } from "@/api/refusal";
import { saveDevice, savedBlocked } from "@/features/devices/this-device";
import { newId } from "@/lib/ids";
import { forgetCsrfToken, giveCsrfToken } from "@/test/csrf";
import { DAWA_LAPTOP } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { madeUpJpeg, madeUpPng, madeUpWebp } from "@/test/photos";
import { ASHA, BOOTSTRAP } from "@/test/shop-lists";

import { LARGEST_PHOTO } from "../attachments";
import type { ShopDatabase } from "../db";
import { shopDatabase } from "../this-shop";
import { FIRST_WAIT_MS, LONGEST_WAIT_MS, MOST_BYTES } from "./attachments";
import { CURSOR, LAST_DEVICE_SEQ } from "./meta";
import { noteCutOff } from "./outages";
import { pagePlace } from "./page-place";
import { fetchStaffPhotos } from "./staff-photos";
import { syncShop } from "./sync";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const SHOP = DAWA_LAPTOP.shop.id;
const PUSH = "/api/sync/v1/push/";
const PULL = "/api/sync/v1/pull/";
const photoRoute = (id: string) => `/api/sync/v1/staff-photos/${id}/`;

// Two more people at work at the shop, made up as Asha is.
const BARAKA = {
  ...ASHA,
  id: "019a5e00-0000-7000-8000-0000000000c4",
  full_name: "Baraka Mfano",
  display_name: "Baraka",
};
const JUMA = {
  ...ASHA,
  id: "019a5e00-0000-7000-8000-0000000000c3",
  full_name: "Juma Mfano",
  display_name: "Juma",
};

let db: ShopDatabase;
beforeEach(async () => {
  // A working laptop, filled at change 130, its last record #57, with its CSRF token, for the pushes of the syncs.
  db = shopDatabase(SHOP);
  await db.meta.bulkPut([
    { key: CURSOR, value: 130 },
    { key: LAST_DEVICE_SEQ, value: 57 },
  ]);
  giveCsrfToken();
});

afterEach(() => {
  // The browser's own navigator, with no connection of a test's.
  Reflect.deleteProperty(navigator, "connection");
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/** A clock a test moves by hand, starting in the shop's morning. */
function aClockByHand(): void {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-23T05:00:00Z"));
}

/** A new photo's id. Each test asks for photos of its own, as a photo's wait is kept by its id for as long as the page
 * is open (staff-photos.ts). */
const aPhoto = () => newId();

/** The server hands this photo out, as its route does: the file's bytes, with its type. */
function hasPhoto(id: string, photo: Blob = madeUpJpeg()): void {
  answer(
    "GET",
    photoRoute(id),
    async () =>
      new Response(await photo.arrayBuffer(), {
        headers: { "Content-Type": photo.type },
      }),
  );
}

/** The photos asked for, in order, by their ids. */
const asked = () =>
  sent
    .map((request) => new URL(request.url).pathname)
    .filter((path) => path.includes("/staff-photos/"))
    .map((path) => path.split("/").at(-2));

/** The photos the laptop holds, by their ids. */
const held = () => db.staff_photos.toCollection().primaryKeys();

const bytesOf = (bytes: ArrayBuffer) => Array.from(new Uint8Array(bytes));

/** What the browser says of the line, as Chrome does on a phone. */
function onLine(connection: { type?: string; saveData?: boolean }): void {
  Object.defineProperty(navigator, "connection", {
    value: connection,
    configurable: true,
  });
}

const aDay = 24 * 60 * 60_000;

describe("the workers' photos", () => {
  it("brings the photo Asha's row names, and keeps it", async () => {
    const photo = aPhoto();
    await db.staff.put({ ...ASHA, photo });
    hasPhoto(photo, madeUpJpeg(200));

    await fetchStaffPhotos(db, pagePlace);

    expect(asked()).toEqual([photo]);
    const kept = await db.staff_photos.get(photo);
    expect(kept?.content_type).toBe("image/jpeg");
    expect(bytesOf(kept!.bytes)).toEqual(
      bytesOf(await madeUpJpeg(200).arrayBuffer()),
    );
  });

  it("asks for a photo once: the next sync finds it here", async () => {
    // A changed photo is a new id, so one kept never needs asking for again.
    const photo = aPhoto();
    await db.staff.put({ ...ASHA, photo });
    hasPhoto(photo);

    await fetchStaffPhotos(db, pagePlace);
    await fetchStaffPhotos(db, pagePlace);

    expect(asked()).toEqual([photo]);
    expect(await held()).toEqual([photo]);
  });

  it("asks for nothing where no row names a photo, nor one saved before rows named any", async () => {
    // A row a laptop saved before PPL-14 holds no `photo` at all: read as none.
    const before = { ...BARAKA };
    Reflect.deleteProperty(before, "photo");
    await db.staff.bulkPut([ASHA, before]);

    await fetchStaffPhotos(db, pagePlace);

    expect(sent).toEqual([]);
    expect(await held()).toEqual([]);
  });

  it("keeps a WebP as one, by its first bytes, whatever the answer calls it", async () => {
    const photo = aPhoto();
    await db.staff.put({ ...ASHA, photo });
    hasPhoto(
      photo,
      new Blob([await madeUpWebp().arrayBuffer()], { type: "image/jpeg" }),
    );

    await fetchStaffPhotos(db, pagePlace);

    expect((await db.staff_photos.get(photo))?.content_type).toBe("image/webp");
  });

  it("brings a new photo in the old one's place, and drops the old one", async () => {
    // Meneja chose a better photo of Asha: her row names it at the next pull. Nothing shows the old one any more.
    const [first, better] = [aPhoto(), aPhoto()];
    await db.staff.put({ ...ASHA, photo: first });
    hasPhoto(first);
    hasPhoto(better);
    await fetchStaffPhotos(db, pagePlace);
    await db.staff.put({ ...ASHA, photo: better });

    await fetchStaffPhotos(db, pagePlace);

    expect(await held()).toEqual([better]);
  });

  it("drops a photo taken off, and asks for nothing", async () => {
    const photo = aPhoto();
    await db.staff.put({ ...ASHA, photo });
    hasPhoto(photo);
    await fetchStaffPhotos(db, pagePlace);
    await db.staff.put({ ...ASHA, photo: null });
    sent.length = 0;

    await fetchStaffPhotos(db, pagePlace);

    expect(await held()).toEqual([]);
    expect(sent).toEqual([]);
  });

  it("drops the photo of someone who left, and keeps the others'", async () => {
    // The pull took Asha's row off the laptop (an archive): her face goes too, as personal data is kept only as long
    // as it is needed (03 §10).
    const [ashas, barakas] = [aPhoto(), aPhoto()];
    await db.staff.bulkPut([
      { ...ASHA, photo: ashas },
      { ...BARAKA, photo: barakas },
    ]);
    hasPhoto(ashas);
    hasPhoto(barakas);
    await fetchStaffPhotos(db, pagePlace);
    await db.staff.delete(ASHA.id);

    await fetchStaffPhotos(db, pagePlace);

    expect(await held()).toEqual([barakas]);
  });

  it("keeps a suspended person's photo, for the day they are brought back", async () => {
    const photo = aPhoto();
    await db.staff.put({ ...ASHA, photo, status: "suspended" });
    hasPhoto(photo);

    await fetchStaffPhotos(db, pagePlace);

    expect(await held()).toEqual([photo]);
  });

  it("keeps no photo that no row names by the time it comes", async () => {
    // Asha's photo was taken off while the old one was on its way.
    const photo = aPhoto();
    await db.staff.put({ ...ASHA, photo });
    answer("GET", photoRoute(photo), async () => {
      await db.staff.put({ ...ASHA, photo: null });
      return new Response(await madeUpJpeg().arrayBuffer());
    });

    await fetchStaffPhotos(db, pagePlace);

    expect(asked()).toEqual([photo]);
    expect(await held()).toEqual([]);
  });

  it("asks for the photos one at a time", async () => {
    const photos = [aPhoto(), aPhoto(), aPhoto()];
    await db.staff.bulkPut([
      { ...ASHA, photo: photos[0]! },
      { ...BARAKA, photo: photos[1]! },
      { ...JUMA, photo: photos[2]! },
    ]);
    let atOnce = 0;
    let mostAtOnce = 0;
    for (const photo of photos)
      answer("GET", photoRoute(photo), async () => {
        atOnce += 1;
        mostAtOnce = Math.max(mostAtOnce, atOnce);
        await new Promise((resolve) => setTimeout(resolve, 5));
        atOnce -= 1;
        return new Response(await madeUpJpeg().arrayBuffer());
      });

    await fetchStaffPhotos(db, pagePlace);

    expect((await held()).sort()).toEqual([...photos].sort());
    expect(mostAtOnce).toBe(1);
  });
});

describe("a photo that doesn't come", () => {
  it.each(["attachment.not_found", "attachment.file_removed"])(
    "waits when the server says %s, and the others come",
    async (code) => {
      // Changed since the pull: the next one says to what. Asked again at every sync till then, it would cost a call
      // each 30 s for nothing.
      const [lost, next] = [aPhoto(), aPhoto()];
      await db.staff.bulkPut([
        { ...ASHA, photo: lost },
        { ...BARAKA, photo: next },
      ]);
      answer("GET", photoRoute(lost), refusal(404, code));
      hasPhoto(next);

      // In one round, the lost one first, as the rows come by id: a second round would hide a stop.
      await fetchStaffPhotos(db, pagePlace);
      expect(asked()).toEqual([lost, next]);
      expect(await held()).toEqual([next]);

      await fetchStaffPhotos(db, pagePlace);
      expect(asked()).toEqual([lost, next]);
    },
  );

  it.each([
    { when: "the network drops", how: null },
    {
      when: "the server has a problem",
      how: refusal(500, "server_error"),
    },
    {
      when: "the server has no such route, as one older than the app",
      how: refusal(404, "not_found"),
    },
  ])(
    "stops the round when $when, and the rest wait for the next sync",
    async ({ how }) => {
      const [first, second] = [aPhoto(), aPhoto()];
      await db.staff.bulkPut([
        { ...ASHA, photo: first },
        { ...BARAKA, photo: second },
      ]);
      const inTrouble = () => {
        // fetch's own way of saying no answer came (NoConnection, make-client.ts).
        throw new TypeError("Failed to fetch");
      };
      for (const photo of [first, second])
        answer("GET", photoRoute(photo), how ?? inTrouble);

      await fetchStaffPhotos(db, pagePlace);

      expect(asked()).toHaveLength(1);
      expect(await held()).toEqual([]);
    },
  );

  it.each([
    {
      what: "a Wi-Fi's own login page",
      body: () => "<!doctype html><title>Ingia</title>",
    },
    { what: "nothing at all", body: () => "" },
    {
      what: "a picture of another kind",
      body: () => madeUpPng().arrayBuffer(),
    },
    {
      what: "a photo over 1 MB",
      body: () => madeUpJpeg(LARGEST_PHOTO + 1).arrayBuffer(),
    },
  ])("is not kept when what comes is $what", async ({ body }) => {
    // Anything may answer 200 on a shop's line. What isn't a photo the server would hand out proves the server didn't,
    // so the round stops, and the face isn't there rather than broken.
    const [first, second] = [aPhoto(), aPhoto()];
    await db.staff.bulkPut([
      { ...ASHA, photo: first },
      { ...BARAKA, photo: second },
    ]);
    for (const photo of [first, second])
      answer(
        "GET",
        photoRoute(photo),
        async () =>
          new Response(await body(), {
            headers: { "Content-Type": "image/jpeg" },
          }),
      );

    await fetchStaffPhotos(db, pagePlace);

    expect(asked()).toHaveLength(1);
    expect(await held()).toEqual([]);
  });

  it("is kept at exactly 1 MB, the largest the server keeps", async () => {
    const photo = aPhoto();
    await db.staff.put({ ...ASHA, photo });
    hasPhoto(photo, madeUpJpeg(LARGEST_PHOTO));

    await fetchStaffPhotos(db, pagePlace);

    expect((await db.staff_photos.get(photo))?.bytes.byteLength).toBe(
      LARGEST_PHOTO,
    );
  });

  it("waits longer after each try, at most an hour, then is asked for again", async () => {
    aClockByHand();
    const photo = aPhoto();
    await db.staff.put({ ...ASHA, photo });
    answer("GET", photoRoute(photo), refusal(500, "server_error"));
    const waits = [1, 2, 4, 8, 16, 32, 60, 60];

    for (const [tries, minutes] of waits.entries()) {
      await fetchStaffPhotos(db, pagePlace);
      expect(asked()).toHaveLength(tries + 1);
      // A moment before its wait ends, a sync asks for nothing.
      vi.setSystemTime(Date.now() + minutes * 60_000 - 1);
      await fetchStaffPhotos(db, pagePlace);
      expect(asked()).toHaveLength(tries + 1);
      vi.setSystemTime(Date.now() + 1);
    }
    expect([FIRST_WAIT_MS, LONGEST_WAIT_MS]).toEqual([60_000, 60 * 60_000]);

    hasPhoto(photo);
    await fetchStaffPhotos(db, pagePlace);
    expect(await held()).toEqual([photo]);
  });

  it("is asked for when the laptop's clock was put far back", async () => {
    // No real wait is over an hour: more left means the clock moved, and the face would wait for as long as it did.
    aClockByHand();
    const photo = aPhoto();
    await db.staff.put({ ...ASHA, photo });
    answer("GET", photoRoute(photo), refusal(500, "server_error"));
    await fetchStaffPhotos(db, pagePlace);
    vi.setSystemTime(Date.now() - aDay);
    hasPhoto(photo);

    await fetchStaffPhotos(db, pagePlace);

    expect(await held()).toEqual([photo]);
  });

  it("starts its waits afresh when its row names it again", async () => {
    // Taken off and, by the superuser say, named again: the old tries were about a row that is gone.
    aClockByHand();
    const photo = aPhoto();
    await db.staff.put({ ...ASHA, photo });
    answer("GET", photoRoute(photo), refusal(404, "attachment.not_found"));
    await fetchStaffPhotos(db, pagePlace);
    await db.staff.put({ ...ASHA, photo: null });
    await fetchStaffPhotos(db, pagePlace);
    await db.staff.put({ ...ASHA, photo });
    hasPhoto(photo);

    await fetchStaffPhotos(db, pagePlace);

    expect(await held()).toEqual([photo]);
  });

  it("locks the app when the laptop is blocked, and asks for nothing more", async () => {
    // Thrown on, as from any sync call, with the block kept (answer.ts): a blocked laptop must stop asking (03 §5.9).
    saveDevice(DAWA_LAPTOP);
    const [first, second] = [aPhoto(), aPhoto()];
    await db.staff.bulkPut([
      { ...ASHA, photo: first },
      { ...BARAKA, photo: second },
    ]);
    for (const photo of [first, second])
      answer("GET", photoRoute(photo), refusal(401, "device.blocked"));

    await expect(fetchStaffPhotos(db, pagePlace)).rejects.toBeInstanceOf(
      ApiRefusal,
    );

    expect(asked()).toHaveLength(1);
    expect(savedBlocked()).toBe(true);
  });
});

describe("the line", () => {
  it("brings no more once 1.5 MB came, and the rest at the next sync", async () => {
    // The sync holds its lock while they come: a record saved meanwhile must not wait behind a whole shop of faces.
    expect(MOST_BYTES).toBe(1_572_864);
    const photos = [aPhoto(), aPhoto(), aPhoto()];
    await db.staff.bulkPut([
      { ...ASHA, photo: photos[0]! },
      { ...BARAKA, photo: photos[1]! },
      { ...JUMA, photo: photos[2]! },
    ]);
    for (const photo of photos) hasPhoto(photo, madeUpJpeg(800_000));

    await fetchStaffPhotos(db, pagePlace);
    expect(await held()).toHaveLength(2);

    await fetchStaffPhotos(db, pagePlace);
    expect((await held()).sort()).toEqual([...photos].sort());
    expect(asked()).toHaveLength(3);
  });

  it.each([
    ["mobile data", { type: "cellular" }],
    ["Wi-Fi with a data saver on", { type: "wifi", saveData: true }],
  ])(
    "brings none on %s, and drops what no row names",
    async (_, connection) => {
      const [gone, wanted] = [aPhoto(), aPhoto()];
      await db.staff_photos.put({
        id: gone,
        content_type: "image/jpeg",
        bytes: await madeUpJpeg().arrayBuffer(),
      });
      await db.staff.put({ ...ASHA, photo: wanted });
      hasPhoto(wanted);
      onLine(connection);

      await fetchStaffPhotos(db, pagePlace);

      // A drop costs no data.
      expect(await held()).toEqual([]);
      expect(asked()).toEqual([]);

      // Waiting for Wi-Fi is no failed try: it comes at the first sync on it.
      onLine({ type: "wifi", saveData: false });
      await fetchStaffPhotos(db, pagePlace);
      expect(await held()).toEqual([wanted]);
    },
  );

  it("stops the moment the device leaves the Wi-Fi", async () => {
    const [first, second] = [aPhoto(), aPhoto()];
    await db.staff.bulkPut([
      { ...ASHA, photo: first },
      { ...BARAKA, photo: second },
    ]);
    for (const photo of [first, second])
      answer("GET", photoRoute(photo), async () => {
        onLine({ type: "cellular" });
        return new Response(await madeUpJpeg().arrayBuffer());
      });

    await fetchStaffPhotos(db, pagePlace);

    expect(asked()).toHaveLength(1);
    expect(await held()).toEqual(asked());
  });
});

describe("a sync", () => {
  const paths = () => sent.map((request) => new URL(request.url).pathname);

  /** The pull brings Asha's row, naming this photo, as Meneja's save left it. */
  function pullNames(photo: string): void {
    answer("GET", PULL, {
      status: 200,
      body: {
        changes: [
          {
            seq: 131,
            entity: "staff",
            id: ASHA.id,
            op: "upsert",
            data: { ...ASHA, photo },
          },
        ],
        cursor: 131,
        has_more: false,
        server_time: "2026-11-23T05:00:00Z",
        min_app_version: 1,
      },
    });
  }

  beforeEach(() => {
    answer("POST", PUSH, { status: 200, body: { answers: [] } });
  });

  it("brings the row, then the face it names", async () => {
    // Done when: Meneja sets Asha's photo in the office, and the laptop holds it after its next sync.
    const photo = aPhoto();
    pullNames(photo);
    hasPhoto(photo);

    await syncShop(SHOP);

    expect(paths()).toEqual([PUSH, PULL, photoRoute(photo)]);
    expect(await held()).toEqual([photo]);
  });

  it("brings the faces of a laptop filled for the first time", async () => {
    const photo = aPhoto();
    await db.meta.delete(CURSOR);
    answer("GET", "/api/sync/v1/bootstrap/", {
      status: 200,
      body: { ...BOOTSTRAP, staff: [{ ...ASHA, photo }] },
    });
    pullNames(photo);
    hasPhoto(photo);

    await syncShop(SHOP);

    expect(await held()).toEqual([photo]);
  });

  it("brings them though the push failed, or has no CSRF token yet: a photo is only read", async () => {
    const photo = aPhoto();
    pullNames(photo);
    hasPhoto(photo);
    answer("POST", PUSH, refusal(502, "server_error"));

    await expect(syncShop(SHOP)).rejects.toBeInstanceOf(ApiRefusal);
    expect(await held()).toEqual([photo]);

    const next = aPhoto();
    pullNames(next);
    hasPhoto(next);
    forgetCsrfToken();
    await syncShop(SHOP);
    expect(await held()).toEqual([next]);
  });

  it("asks for none when its pull failed", async () => {
    // The line or the server is in trouble, and the rows may be old.
    await db.staff.put({ ...ASHA, photo: aPhoto() });
    answer("GET", PULL, refusal(502, "server_error"));

    await expect(syncShop(SHOP)).rejects.toBeInstanceOf(ApiRefusal);

    expect(asked()).toEqual([]);
  });

  it("works whole when a photo doesn't come", async () => {
    // The records went up and the office's changes came down: a face missing is no failed sync.
    const photo = aPhoto();
    pullNames(photo);
    answer("GET", photoRoute(photo), refusal(500, "server_error"));

    await syncShop(SHOP);

    expect(paths()).toEqual([PUSH, PULL, photoRoute(photo)]);
  });

  it("works whole when the photos meet a trouble of their own, and logs it", async () => {
    const photo = aPhoto();
    pullNames(photo);
    hasPhoto(photo);
    vi.spyOn(db.staff_photos, "put").mockRejectedValue(new Error("disk full"));
    const logged = vi.spyOn(console, "error").mockImplementation(() => {});

    await syncShop(SHOP);

    expect(logged).toHaveBeenCalledWith(
      "the workers' photos were not fetched",
      new Error("disk full"),
    );
  });

  it("fails when the laptop is blocked meanwhile", async () => {
    saveDevice(DAWA_LAPTOP);
    const photo = aPhoto();
    pullNames(photo);
    answer("GET", photoRoute(photo), refusal(401, "device.blocked"));

    await expect(syncShop(SHOP)).rejects.toBeInstanceOf(ApiRefusal);

    expect(savedBlocked()).toBe(true);
  });

  it("ends the office's report of a cut at the pull's answer, not after the photos", async () => {
    // As for the photos that go up (SYNC-14): the photos' minutes on a slow line are no part of the cut.
    aClockByHand();
    vi.setSystemTime(new Date("2026-11-23T09:59:00Z"));
    await noteCutOff(db, Date.now());
    vi.setSystemTime(new Date("2026-11-23T10:00:00Z"));
    const photo = aPhoto();
    pullNames(photo);
    answer("GET", photoRoute(photo), async () => {
      vi.setSystemTime(new Date("2026-11-23T10:04:00Z"));
      return new Response(await madeUpJpeg().arrayBuffer());
    });

    await syncShop(SHOP);

    expect(await held()).toEqual([photo]);
    expect(await db.outages.toArray()).toMatchObject([
      {
        started_at: "2026-11-23T09:59:00.000Z",
        ended_at: "2026-11-23T10:00:00.000Z",
      },
    ]);
  });
});
