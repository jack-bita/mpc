// attendance.test.tsx — the Mahudhurio screen (SYNC-11, 02 §12): one big button, the one that fits; a tap
// saved on the laptop as one clock document in the person's name, with the last server time the laptop had
// seen; Toka kazini says goodbye, then logs her out (Jack, SYNC-11); and nothing asked of the server. With a
// photo at each tap, saved with it, or the tap saved all the same when the camera can't, and on the demo the
// photo shown but kept nowhere (ATT-3).
//
// The tests' browser (jsdom) has no camera: a test that wants one gives the page a pretend one, and the
// shrinking is a stand-in (shrink-photo.test.ts tests it), so every other test meets a laptop with none.
import {
  act,
  fireEvent,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import { shrinkFrame } from "@/lib/shrink-photo";
import {
  arriveAtCounter,
  useLeaveAsked,
} from "@/features/login/at-the-counter";
import { useAttendanceOn } from "@/offline/attendance-on";
import { saveDocument } from "@/offline/outbox";
import { LAST_DEVICE_SEQ, LAST_SERVER_TIME } from "@/offline/sync/meta";
import { shopDatabase } from "@/offline/this-shop";
import { DAWA, DAWA_LAPTOP } from "@/test/devices";
import { swahiliIn } from "@/test/language";
import { attendanceSwitchedOn, staffRow, theLaptopKnows } from "@/test/laptop";
import { render } from "@/test/render";
import { router } from "@/test/router";
import { DAWA_SIDE } from "@/test/shop-lists";

import CounterLayout from "../layout";
import { GOODBYE_FOR } from "./attendance";
import AttendancePage from "./page";

vi.mock("@/lib/shrink-photo", () => ({ shrinkFrame: vi.fn() }));

// Two sellers on Dawa, as the sync left them on the laptop. Fake people.
const keys = {
  every_side: [],
  sides: [{ side: DAWA.id, permissions: ["sale.make"] }],
};
const ASHA = {
  ...staffRow("019a5e00-0000-7000-8000-0000000000c2", "Asha Mfano", "Asha"),
  permissions: keys,
};
const JUMA = {
  ...staffRow("019a5e00-0000-7000-8000-0000000000c3", "Juma Mfano", "Juma"),
  permissions: keys,
};

/** The last time the server told this laptop, at its last pull: 07:00 in Dar. */
const SERVER_TIME = "2026-11-13T04:00:00Z";
/** 07:55 in Dar on 13 November, by the laptop's clock: Asha arrives. */
const MORNING = new Date("2026-11-13T04:55:00Z");
/** 18:02 the same day: she leaves. */
const EVENING = new Date("2026-11-13T15:02:00Z");

const db = () => shopDatabase(DAWA_LAPTOP.shop.id);
const leaveAsked = () =>
  renderHook(() => useLeaveAsked()).result.current?.staffId ?? null;
const clockIn = () => screen.queryByRole("button", { name: "Ingia kazini" });
const clockOut = () => screen.queryByRole("button", { name: "Toka kazini" });

/** A tap saved earlier, as the screen saves one, at `at` by the laptop's clock. */
async function tappedEarlier(
  who: typeof ASHA,
  kind: "in" | "out",
  at: Date,
): Promise<void> {
  vi.setSystemTime(at);
  await saveDocument(db(), {
    type: "clock",
    schema_version: 1,
    created_by: who.id,
    payload: { kind, last_server_time: SERVER_TIME },
  });
}

/** The owner switches attendance off again from `day`: a second row, after the start-of-month one. */
async function switchedOffFrom(day: string): Promise<void> {
  await db().setting.put({
    id: "019a5e00-0000-7000-8000-00000000a7e3",
    key: "attendance.enabled",
    side: null,
    value: "false",
    effective_from: day,
  });
}

/** The screen, inside the counter's frame, with Asha logged in at the home page before it opened. */
async function theScreen() {
  arriveAtCounter(ASHA, 15, "server");
  render(
    <CounterLayout>
      <AttendancePage />
    </CounterLayout>,
  );
  await screen.findByRole("heading", { level: 1, name: "Mahudhurio" });
}

// The pretend clock: the time and the timers only, and it still moves on its own. The test database
// (fake-indexeddb) runs on setImmediate, which must stay real, or its transactions never end (SYNC-10).
beforeEach(async () => {
  vi.useFakeTimers({
    shouldAdvanceTime: true,
    toFake: [
      "setTimeout",
      "setInterval",
      "clearTimeout",
      "clearInterval",
      "Date",
    ],
  });
  vi.setSystemTime(MORNING);
  // The Dawa laptop, registered, filled by a bootstrap (its last record #57) and a pull since, at a shop that
  // switched attendance on at the start of the month (ATT-2).
  saveDevice(DAWA_LAPTOP);
  await theLaptopKnows(ASHA, JUMA);
  await attendanceSwitchedOn("2026-11-01");
  await db().side.put(DAWA_SIDE);
  await db().meta.bulkPut([
    { key: LAST_DEVICE_SEQ, value: 57 },
    { key: LAST_SERVER_TIME, value: SERVER_TIME },
  ]);
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("clocking in", () => {
  it("offers Ingia kazini to someone not in today, and says so", async () => {
    await theScreen();

    expect(await screen.findByText("Hujaingia kazini leo.")).toBeDefined();
    expect(clockIn()).not.toBeNull();
    expect(clockOut()).toBeNull();
  });

  it("saves one clock-in on the laptop, in her name, with the last server time it had seen", async () => {
    await theScreen();

    fireEvent.click(
      await screen.findByRole("button", { name: "Ingia kazini" }),
    );

    expect(
      await screen.findByText("Umeingia kazini saa 07:55 asubuhi."),
    ).toBeDefined();
    const saved = await db().documents.toArray();
    expect(saved).toHaveLength(1);
    expect(saved[0]).toMatchObject({
      type: "clock",
      // Version 2, with its photo or why it has none (ATT-3): this laptop has no camera.
      schema_version: 2,
      created_by: ASHA.id,
      // The laptop's clock at the tap, 07:55 in Dar: the pretend clock still moves on, by milliseconds.
      client_time: expect.stringMatching(/^2026-11-13T04:55:/),
      payload: {
        kind: "in",
        last_server_time: SERVER_TIME,
        no_photo: "no_camera",
      },
    });
    // Waiting in the outbox, the next number after the bootstrap's: the sync takes it from there.
    expect(await db().outbox.toArray()).toMatchObject([
      { id: saved[0]?.id, device_seq: 58, status: "waiting" },
    ]);
  });

  it("takes the button away once tapped, so a double tap saves one clock-in", async () => {
    // A quick double tap: the second must not save a second in, nor land on Toka kazini.
    await theScreen();
    const button = await screen.findByRole("button", { name: "Ingia kazini" });

    fireEvent.click(button);
    fireEvent.click(button);

    await screen.findByText("Umeingia kazini saa 07:55 asubuhi.");
    expect(clockIn()).toBeNull();
    expect(clockOut()).toBeNull();
    expect(await db().documents.count()).toBe(1);
  });

  it("asks the server nothing: the same with or without the internet", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    await theScreen();

    fireEvent.click(
      await screen.findByRole("button", { name: "Ingia kazini" }),
    );
    await screen.findByText("Umeingia kazini saa 07:55 asubuhi.");

    expect(fetch).not.toHaveBeenCalled();
  });

  it("counts only her own taps: Juma in already, Asha still offered Ingia kazini", async () => {
    await tappedEarlier(JUMA, "in", new Date("2026-11-13T04:40:00Z"));
    vi.setSystemTime(MORNING);

    await theScreen();

    expect(await screen.findByText("Hujaingia kazini leo.")).toBeDefined();
    expect(clockIn()).not.toBeNull();
  });

  it("offers Ingia kazini again on a new day: yesterday's clock-in doesn't count", async () => {
    await tappedEarlier(ASHA, "in", new Date("2026-11-12T04:50:00Z"));
    vi.setSystemTime(MORNING);

    await theScreen();

    expect(await screen.findByText("Hujaingia kazini leo.")).toBeDefined();
    expect(clockIn()).not.toBeNull();
  });
});

describe("a clock-in the server refused", () => {
  it("doesn't count: she is offered Ingia kazini again, and the warning says why", async () => {
    // Set aside by the push (push.ts): it never reached the attendance book, so she isn't in on the server.
    await tappedEarlier(ASHA, "in", MORNING);
    const [first] = await db().outbox.toArray();
    await db().outbox.update(first?.id ?? "", {
      status: "needs_attention",
      last_error: "document.maker_unknown",
    });
    vi.setSystemTime(new Date("2026-11-13T05:10:00Z"));

    await theScreen();

    expect(await screen.findByText("Hujaingia kazini leo.")).toBeDefined();
    expect(clockIn()).not.toBeNull();
    expect(
      await screen.findByRole("alert", {
        name: "Kumbukumbu zilizokataliwa na seva",
      }),
    ).toBeDefined();
  });
});

describe("clocking out", () => {
  it("offers Toka kazini once she is in, with the time she came", async () => {
    await tappedEarlier(ASHA, "in", MORNING);
    vi.setSystemTime(EVENING);

    await theScreen();

    expect(
      await screen.findByText("Uliingia kazini saa 07:55 asubuhi."),
    ).toBeDefined();
    expect(clockOut()).not.toBeNull();
    expect(clockIn()).toBeNull();
  });

  it("says goodbye, then logs her out by itself", async () => {
    // Jack's choice: she is leaving the shop, so the laptop must not stay open in her name.
    await tappedEarlier(ASHA, "in", MORNING);
    vi.setSystemTime(EVENING);
    await theScreen();

    fireEvent.click(await screen.findByRole("button", { name: "Toka kazini" }));

    expect(
      await screen.findByText("Umetoka kazini saa 18:02 jioni. Kwaheri!"),
    ).toBeDefined();
    // Long enough to read it: not logged out yet.
    expect(leaveAsked()).toBeNull();

    await act(() => vi.advanceTimersByTimeAsync(GOODBYE_FOR));

    expect(leaveAsked()).toBe(ASHA.id);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
    const saved = await db().documents.toArray();
    expect(
      saved.map((each) => (each.payload as { kind: string }).kind),
    ).toEqual(["in", "out"]);
  });

  it("has the back arrow, to her welcome with no page of the app's before, and no Rudi", async () => {
    // Every page reached from another has the arrow at its top left, the one way back (Jack, OPS-13).
    await theScreen();

    expect(screen.queryByRole("link", { name: "Rudi" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Rudi ulipotoka" }));
    expect(router.push).toHaveBeenCalledWith("/");
  });

  it("offers no back arrow during the goodbye, and leaving the screen then logs her out at once", async () => {
    // Asha taps Toka kazini, then Back in the browser out of habit, and walks out. The laptop must not stay
    // on her welcome for the next 15 minutes, for anyone to clock in as her.
    await tappedEarlier(ASHA, "in", MORNING);
    vi.setSystemTime(EVENING);
    arriveAtCounter(ASHA, 15, "server");
    const { unmount } = render(
      <CounterLayout>
        <AttendancePage />
      </CounterLayout>,
    );
    expect(
      await screen.findByRole("button", { name: "Rudi ulipotoka" }),
    ).toBeDefined();

    fireEvent.click(await screen.findByRole("button", { name: "Toka kazini" }));
    await screen.findByText("Umetoka kazini saa 18:02 jioni. Kwaheri!");
    expect(screen.queryByRole("button", { name: "Rudi ulipotoka" })).toBeNull();
    // The title stays, the page's one heading, as she reads her goodbye.
    expect(
      screen.getByRole("heading", { level: 1, name: "Mahudhurio" }),
    ).toBeDefined();

    unmount();

    expect(leaveAsked()).toBe(ASHA.id);
  });

  it("follows the tap she made last, even when the laptop's clock went back between the two", async () => {
    // In at 08:00 by the laptop's clock; then the clock is set back 10 minutes, and she clocks out at what it
    // calls 07:50. Her last tap is the out, by its number on the laptop, whatever the clock says.
    await tappedEarlier(ASHA, "in", new Date("2026-11-13T05:00:00Z"));
    await tappedEarlier(ASHA, "out", new Date("2026-11-13T04:50:00Z"));
    vi.setSystemTime(new Date("2026-11-13T05:10:00Z"));

    await theScreen();

    expect(
      await screen.findByText("Ulitoka kazini saa 07:50 asubuhi."),
    ).toBeDefined();
    expect(clockIn()).not.toBeNull();
  });

  it("offers Ingia kazini again after she clocked out, as after lunch", async () => {
    await tappedEarlier(ASHA, "in", MORNING);
    await tappedEarlier(ASHA, "out", new Date("2026-11-13T09:30:00Z"));
    vi.setSystemTime(new Date("2026-11-13T10:25:00Z"));

    await theScreen();

    expect(
      await screen.findByText("Ulitoka kazini saa 12:30 mchana."),
    ).toBeDefined();
    expect(clockIn()).not.toBeNull();
  });
});

describe("a laptop not ready to save", () => {
  it("says to wait for the first sync on a laptop never filled, and saves nothing", async () => {
    // A new laptop before its first bootstrap: no number to give a record (NeverFilled, outbox.ts).
    await db().meta.delete(LAST_DEVICE_SEQ);
    await theScreen();

    fireEvent.click(
      await screen.findByRole("button", { name: "Ingia kazini" }),
    );

    expect(
      await screen.findByText(
        "Subiri kidogo: kompyuta hii bado inaleta data za duka kwa mara ya kwanza. Jaribu tena baada ya muda mfupi.",
      ),
    ).toBeDefined();
    expect(await db().documents.count()).toBe(0);
    // Still there, for the next try.
    expect(clockIn()).not.toBeNull();
  });

  it("says the same before its first pull: the server refuses a clock-in with no server time", async () => {
    await db().meta.delete(LAST_SERVER_TIME);
    await theScreen();

    fireEvent.click(
      await screen.findByRole("button", { name: "Ingia kazini" }),
    );

    expect(
      await screen.findByText(/^Subiri kidogo: kompyuta hii bado inaleta/),
    ).toBeDefined();
    expect(await db().documents.count()).toBe(0);
  });
});

describe("while attendance is switched off (ATT-2)", () => {
  const switchedOff =
    "Mahudhurio hayajawashwa kwenye duka hili. Mwenye duka huyawasha kwenye Mipangilio ya duka.";

  it("says it isn't switched on, offers no button, and the way back", async () => {
    // The owner switched it on from tomorrow: today it is still off.
    await attendanceSwitchedOn("2026-11-14");

    await theScreen();

    expect(await screen.findByText(switchedOff)).toBeDefined();
    expect(clockIn()).toBeNull();
    expect(clockOut()).toBeNull();
    expect(
      screen.getByRole("button", { name: "Rudi ulipotoka" }),
    ).toBeDefined();
    expect(screen.queryByRole("link", { name: "Rudi" })).toBeNull();
  });

  it("still shows the taps the server refused, and what waits to be sent", async () => {
    // Switched off again after a day of taps: one was refused, one waits. A manager must still hear of the first,
    // and Tuma sasa still sends the second.
    await tappedEarlier(ASHA, "in", MORNING);
    await tappedEarlier(JUMA, "in", MORNING);
    const [first] = await db().outbox.toArray();
    await db().outbox.update(first?.id ?? "", {
      status: "needs_attention",
      last_error: "document.maker_unknown",
    });
    await switchedOffFrom("2026-11-13");

    await theScreen();

    expect(await screen.findByText(switchedOff)).toBeDefined();
    expect(
      await screen.findByRole("alert", {
        name: "Kumbukumbu zilizokataliwa na seva",
      }),
    ).toBeDefined();
    expect(
      await screen.findByRole("button", { name: "Tuma sasa" }),
    ).toBeDefined();
  });

  it("keeps saying her tap was saved when a pull switches it off a moment after", async () => {
    await theScreen();
    fireEvent.click(
      await screen.findByRole("button", { name: "Ingia kazini" }),
    );
    await screen.findByText("Umeingia kazini saa 07:55 asubuhi.");

    await switchedOffFrom("2026-11-13");

    // Once the laptop reads the switch as off, as the screen's own reader does from the same rows, the screen still
    // stays on her saved tap.
    const reader = renderHook(() => useAttendanceOn());
    await waitFor(() => expect(reader.result.current).toBe(false));
    await act(() => vi.advanceTimersByTimeAsync(100));
    expect(
      screen.getByText("Umeingia kazini saa 07:55 asubuhi."),
    ).toBeDefined();
    expect(screen.queryByText(switchedOff)).toBeNull();
  });

  it("offers Ingia kazini from the day it is switched on", async () => {
    await attendanceSwitchedOn("2026-11-13");

    await theScreen();

    expect(
      await screen.findByRole("button", { name: "Ingia kazini" }),
    ).toBeDefined();
  });
});

/** A camera's track: its light is on until `stop()`. */
class PretendTrack extends EventTarget {
  stop = vi.fn();
}

/** The laptop's webcam, which the browser hands over at once, or refuses with `refusal`. */
function theLaptopHasACamera(refusal?: string): PretendTrack {
  const track = new PretendTrack();
  const stream = { getTracks: () => [track] } as unknown as MediaStream;
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: () =>
        refusal === undefined
          ? Promise.resolve(stream)
          : Promise.reject(new DOMException("no", refusal)),
    },
  });
  return track;
}

/** A made-up JPEG, its first bytes a JPEG's, never a face: what the shrinking gives back. */
const PHOTO = new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3])], {
  type: "image/jpeg",
});

/** The live picture on the screen, showing a webcam's 1280 × 720 frame. */
async function theLivePicture(): Promise<HTMLVideoElement> {
  const video = await screen.findByLabelText<HTMLVideoElement>(
    "Kamera: uso wako sasa hivi",
  );
  Object.defineProperty(video, "videoWidth", { value: 1280 });
  Object.defineProperty(video, "videoHeight", { value: 720 });
  return video;
}

describe("the photo at each tap (ATT-3)", () => {
  beforeEach(() => {
    vi.mocked(shrinkFrame).mockResolvedValue(PHOTO);
    // jsdom has no addresses for a photo in memory: a pretend one, freed as the screen closes.
    URL.createObjectURL = vi.fn(() => "blob:asha-0755");
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => {
    Reflect.deleteProperty(navigator, "mediaDevices");
    Reflect.deleteProperty(URL, "createObjectURL");
    Reflect.deleteProperty(URL, "revokeObjectURL");
    vi.mocked(shrinkFrame).mockReset();
  });

  it("shows her face live, takes her photo as she taps, and saves it with the tap", async () => {
    const light = theLaptopHasACamera();
    await theScreen();
    await theLivePicture();

    fireEvent.click(
      await screen.findByRole("button", { name: "Ingia kazini" }),
    );

    expect(
      await screen.findByText("Umeingia kazini saa 07:55 asubuhi."),
    ).toBeDefined();
    // The tap names its photo by its label, and the photo waits beside it, both saved at once (CTRL-6).
    const [tap] = await db().documents.toArray();
    expect(tap?.payload).toMatchObject({
      kind: "in",
      photo: {
        kind: "clock_photo",
        content_type: "image/jpeg",
        size: PHOTO.size,
        sha256: expect.stringMatching(/^[0-9a-f]{64}$/),
      },
    });
    expect(tap?.payload).not.toHaveProperty("no_photo");
    const waiting = await db().attachment_files.toArray();
    expect(waiting).toMatchObject([
      { document_id: tap?.id, kind: "clock_photo", state: "waiting" },
    ]);
    // She sees the photo kept, and the camera's light is off at once.
    const kept = await screen.findByRole<HTMLImageElement>("img", {
      name: "Picha yako, iliyohifadhiwa pamoja na mahudhurio yako",
    });
    expect(kept.src).toBe("blob:asha-0755");
    expect(light.stop).toHaveBeenCalled();
    expect(screen.queryByLabelText("Kamera: uso wako sasa hivi")).toBeNull();
  });

  it("says there is no camera, and saves the tap all the same, with why", async () => {
    // A laptop with no webcam: nobody loses a day's pay to a camera (Jack: A).
    await theScreen();

    expect(
      await screen.findByText("Hakuna kamera: utaingia bila picha."),
    ).toBeDefined();
    fireEvent.click(
      await screen.findByRole("button", { name: "Ingia kazini" }),
    );

    await screen.findByText("Umeingia kazini saa 07:55 asubuhi.");
    const [tap] = await db().documents.toArray();
    expect(tap?.payload).toMatchObject({ kind: "in", no_photo: "no_camera" });
    expect(await db().attachment_files.count()).toBe(0);
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("says a blocked camera is the manager's to allow, and saves the tap as blocked", async () => {
    theLaptopHasACamera("NotAllowedError");
    await theScreen();

    expect(
      await screen.findByText(
        "Kamera imezuiwa: utaingia bila picha. Mwambie meneja airuhusu.",
      ),
    ).toBeDefined();
    fireEvent.click(
      await screen.findByRole("button", { name: "Ingia kazini" }),
    );

    await screen.findByText("Umeingia kazini saa 07:55 asubuhi.");
    const [tap] = await db().documents.toArray();
    expect(tap?.payload).toMatchObject({ no_photo: "blocked" });
  });

  it("says she clocks out without a photo, on Toka kazini", async () => {
    await tappedEarlier(ASHA, "in", MORNING);
    vi.setSystemTime(EVENING);

    await theScreen();

    expect(
      await screen.findByText("Hakuna kamera: utatoka bila picha."),
    ).toBeDefined();
  });

  it("goes on without a photo the shrinking couldn't make, as failed", async () => {
    // A broken camera, or a bug: the tap is kept all the same, and the console says why.
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.mocked(shrinkFrame).mockRejectedValue(new Error("can't draw"));
    theLaptopHasACamera();
    await theScreen();
    await theLivePicture();

    fireEvent.click(
      await screen.findByRole("button", { name: "Ingia kazini" }),
    );

    await screen.findByText("Umeingia kazini saa 07:55 asubuhi.");
    const [tap] = await db().documents.toArray();
    expect(tap?.payload).toMatchObject({ no_photo: "failed" });
    expect(await db().attachment_files.count()).toBe(0);
  });

  it("on the demo, shows the photo taken but keeps it on the laptop, never saved", async () => {
    // Every demo visitor shares Meneja's login, which opens clock-in photos: a visitor's face never
    // leaves their laptop (Jack, ATT-3: A).
    saveDevice({ ...DAWA_LAPTOP, shop: { ...DAWA_LAPTOP.shop, demo: true } });
    theLaptopHasACamera();
    await theScreen();
    await theLivePicture();

    fireEvent.click(
      await screen.findByRole("button", { name: "Ingia kazini" }),
    );

    await screen.findByText("Umeingia kazini saa 07:55 asubuhi.");
    const [tap] = await db().documents.toArray();
    expect(tap?.payload).toMatchObject({ kind: "in", no_photo: "demo" });
    expect(tap?.payload).not.toHaveProperty("photo");
    expect(await db().attachment_files.count()).toBe(0);
    expect(await db().attachment_bytes.count()).toBe(0);
    expect(
      await screen.findByRole("img", {
        name: "Picha yako, iliyohifadhiwa pamoja na mahudhurio yako",
      }),
    ).toBeDefined();
    expect(
      screen.getByText(
        "Hii ni demo: picha yako inabaki kwenye kompyuta hii, haitumwi kwenye seva.",
      ),
    ).toBeDefined();
  });
});

describe("the screen's words", () => {
  it("speak English to someone who reads it, with no Swahili left", async () => {
    await db().staff.put({ ...ASHA, language: "en" });
    arriveAtCounter({ ...ASHA, language: "en" }, 15, "server");
    render(
      <CounterLayout>
        <AttendancePage />
      </CounterLayout>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Clock in" }));

    expect(await screen.findByText("Clocked in at 07:55.")).toBeDefined();
    expect(swahiliIn(screen.getByRole("main"))).toEqual([]);
  });
});
