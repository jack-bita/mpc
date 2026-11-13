// rescue.test.tsx — the Kompyuta hii screen's rescue part (SYNC-12): saving the waiting records to a file,
// and a manager loading one. What the file holds, and how its records land, is offline/rescue.test.ts's.
import { fireEvent, screen } from "@testing-library/react";
import Dexie from "dexie";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import { arriveAtCounter } from "@/features/login/at-the-counter";
import { openShopDatabase } from "@/offline/db";
import { forgetKeepData } from "@/offline/keep-data";
import { saveDocument } from "@/offline/outbox";
import { exportWaiting, type RescueFile } from "@/offline/rescue";
import { LAST_DEVICE_SEQ } from "@/offline/sync/meta";
import { shopDatabase } from "@/offline/this-shop";
import { DAWA, DAWA_LAPTOP } from "@/test/devices";
import { staffRow, theLaptopKnows } from "@/test/laptop";
import { render } from "@/test/render";

import CounterLayout from "../layout";
import ThisLaptopPage from "./page";

/** Asha sells; Neema is the manager, who pairs and blocks the shop's laptops. */
const ASHA = {
  ...staffRow("019a5e00-0000-7000-8000-0000000000c2", "Asha Mfano", "Asha"),
  permissions: {
    every_side: [],
    sides: [{ side: DAWA.id, permissions: ["sale.make"] }],
  },
};
const NEEMA = {
  ...staffRow("019a5e00-0000-7000-8000-0000000000c4", "Neema Mfano", "Neema"),
  permissions: {
    every_side: [],
    sides: [{ side: DAWA.id, permissions: ["device.manage"] }],
  },
};

const db = () => shopDatabase(DAWA_LAPTOP.shop.id);
const saveButton = () =>
  screen.queryByRole("button", { name: "Hifadhi kwenye faili" });
const loadButton = () => screen.queryByRole("button", { name: "Pakia faili" });

/** Asha clocks in on this laptop: one more record waiting. */
const clockIn = () =>
  saveDocument(db(), {
    type: "clock",
    schema_version: 1,
    created_by: ASHA.id,
    payload: { kind: "in", last_server_time: "2026-11-13T04:00:00Z" },
  });

/** The screen in the counter's frame, with `who` logged in. */
async function theScreen(who: typeof ASHA) {
  arriveAtCounter(who, 15, "server");
  render(
    <CounterLayout>
      <ThisLaptopPage />
    </CounterLayout>,
  );
  await screen.findByRole("heading", { level: 1, name: "Kompyuta hii" });
}

/** The file another laptop of the shop saved, with one clock-in of Asha's. */
async function aFileFromTheDawaLaptop(shopId = DAWA_LAPTOP.shop.id) {
  const other = openShopDatabase("dying-laptop-test");
  await other.meta.put({ key: LAST_DEVICE_SEQ, value: 9 });
  await saveDocument(other, {
    type: "clock",
    schema_version: 1,
    created_by: ASHA.id,
    payload: { kind: "in", last_server_time: "2026-11-13T04:00:00Z" },
  });
  // The dying laptop's id: another laptop of the Dawa shop, not this one.
  const file = await exportWaiting(
    other,
    shopId,
    "019a5e00-0000-7000-8000-0000000000e9",
  );
  other.close();
  await Dexie.delete(other.name);
  return new File([JSON.stringify(file)], "mpc-unsent.json", {
    type: "application/json",
  });
}

beforeEach(async () => {
  // The Dawa laptop, registered, filled by a bootstrap: its last record #57.
  saveDevice(DAWA_LAPTOP);
  await theLaptopKnows(ASHA, NEEMA);
  await db().meta.put({ key: LAST_DEVICE_SEQ, value: 57 });
});
afterEach(() => {
  vi.useRealTimers();
  forgetKeepData();
  vi.restoreAllMocks();
});

describe("saving to a file", () => {
  it("says how many wait, and saves them all in one file", async () => {
    const saved = [await clockIn(), await clockIn()];
    // The browser's download, watched: the file it is handed, and the click that starts it.
    let blob: Blob | undefined;
    const makeLink = vi.fn((made: Blob) => {
      blob = made;
      return "blob:rescue";
    });
    Object.assign(URL, { createObjectURL: makeLink, revokeObjectURL: vi.fn() });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    await theScreen(ASHA);

    expect(
      await screen.findByText("Kumbukumbu 2 zinasubiri kutumwa."),
    ).toBeDefined();
    fireEvent.click(saveButton()!);

    await vi.waitFor(() => expect(click).toHaveBeenCalledOnce());
    const file = JSON.parse(await blob!.text()) as RescueFile;
    expect(file.documents.map((document) => document.id)).toEqual(
      saved.map((document) => document.id),
    );
  });

  it("names the file by the laptop and the shop's day, and lets the link go only later", async () => {
    // 01:30 on 13 November in Arusha is still the 12th by UTC: the file is the 13th's.
    vi.useFakeTimers({
      shouldAdvanceTime: true,
      toFake: ["Date", "setTimeout", "clearTimeout"],
    });
    vi.setSystemTime(new Date("2026-11-12T22:30:00Z"));
    await clockIn();
    const revoke = vi.fn();
    Object.assign(URL, {
      createObjectURL: () => "blob:rescue",
      revokeObjectURL: revoke,
    });
    let name = "";
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      name = this.download;
    });
    await theScreen(ASHA);
    fireEvent.click(
      await screen.findByRole("button", { name: "Hifadhi kwenye faili" }),
    );

    await vi.waitFor(() => expect(name).not.toBe(""));
    expect(name).toBe("mpc-unsent-laptop-1-2026-11-13.json");
    // Still held as the click returns, as Firefox and Safari read it then; let go a minute on.
    expect(revoke).not.toHaveBeenCalled();
    vi.advanceTimersByTime(60 * 1000);
    expect(revoke).toHaveBeenCalledWith("blob:rescue");
  });

  it("says so when the records can't be read to save them", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    // An outbox row whose document is gone: the read stops, as a database that refused would.
    const saved = await clockIn();
    await db().documents.delete(saved.id);
    await theScreen(ASHA);
    fireEvent.click(
      await screen.findByRole("button", { name: "Hifadhi kwenye faili" }),
    );

    expect(
      await screen.findByText("Haikufanikiwa. Jaribu tena."),
    ).toBeDefined();
  });

  it("has no button with nothing to save", async () => {
    await theScreen(ASHA);
    expect(
      await screen.findByText(
        "Hakuna kumbukumbu inayosubiri kutumwa kutoka kompyuta hii.",
      ),
    ).toBeDefined();
    expect(saveButton()).toBeNull();
  });
});

describe("loading a file", () => {
  it("isn't offered to a seller: a file edited by hand could clock in a colleague", async () => {
    await clockIn();
    await theScreen(ASHA);
    await screen.findByText("Kumbukumbu 1 inasubiri kutumwa.");
    expect(loadButton()).toBeNull();
  });

  it("adds a manager's file to this laptop's outbox, to be sent from here", async () => {
    await theScreen(NEEMA);
    fireEvent.change(await screen.findByLabelText("Pakia faili"), {
      target: { files: [await aFileFromTheDawaLaptop()] },
    });

    expect(
      await screen.findByText("Kumbukumbu 1 imeongezwa, na itatumwa yenyewe."),
    ).toBeDefined();
    expect(
      await screen.findByText("Kumbukumbu 1 inasubiri kutumwa."),
    ).toBeDefined();
    // Loaded by Neema, the one at the counter: the push names her to the server, which checks her key.
    const [document] = await db().documents.toArray();
    expect(document?.carried_from?.loaded_by).toBe(NEEMA.id);
  });

  it("refuses another shop's file, and says so", async () => {
    await theScreen(NEEMA);
    fireEvent.change(await screen.findByLabelText("Pakia faili"), {
      target: {
        files: [
          await aFileFromTheDawaLaptop("019a5e00-0000-7000-8000-00000000ffff"),
        ],
      },
    });

    // Found by its words: the page's other alert says jsdom's browser can't keep the data.
    expect(
      await screen.findByText("Faili hili ni la duka jingine: halikupakiwa."),
    ).toBeDefined();
    expect(await db().outbox.count()).toBe(0);
  });
});
