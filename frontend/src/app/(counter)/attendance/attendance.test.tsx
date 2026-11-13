// attendance.test.tsx — the Mahudhurio screen (SYNC-11, 02 §12): one big button, the one that fits; a tap
// saved on the laptop as one clock document in the person's name, with the last server time the laptop had
// seen; Toka kazini says goodbye, then logs her out (Jack, SYNC-11); and nothing asked of the server.
import {
  act,
  fireEvent,
  renderHook,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import {
  arriveAtCounter,
  useLeaveAsked,
} from "@/features/login/at-the-counter";
import { saveDocument } from "@/offline/outbox";
import { LAST_DEVICE_SEQ, LAST_SERVER_TIME } from "@/offline/sync/meta";
import { shopDatabase } from "@/offline/this-shop";
import { DAWA, DAWA_LAPTOP } from "@/test/devices";
import { swahiliIn } from "@/test/language";
import { staffRow, theLaptopKnows } from "@/test/laptop";
import { render } from "@/test/render";
import { router } from "@/test/router";
import { DAWA_SIDE } from "@/test/shop-lists";

import CounterLayout from "../layout";
import { GOODBYE_FOR } from "./attendance";
import AttendancePage from "./page";

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
const leaveAsked = () => renderHook(() => useLeaveAsked()).result.current;
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

/** The screen, inside the counter's frame, with Asha logged in at the home page before it opened. */
async function theScreen() {
  arriveAtCounter(ASHA, 15);
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
  // The Dawa laptop, registered, filled by a bootstrap (its last record #57) and a pull since.
  saveDevice(DAWA_LAPTOP);
  await theLaptopKnows(ASHA, JUMA);
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

    expect(await screen.findByText("Umeingia kazini saa 07:55.")).toBeDefined();
    const saved = await db().documents.toArray();
    expect(saved).toHaveLength(1);
    expect(saved[0]).toMatchObject({
      type: "clock",
      schema_version: 1,
      created_by: ASHA.id,
      // The laptop's clock at the tap, 07:55 in Dar: the pretend clock still moves on, by milliseconds.
      client_time: expect.stringMatching(/^2026-11-13T04:55:/),
      payload: { kind: "in", last_server_time: SERVER_TIME },
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

    await screen.findByText("Umeingia kazini saa 07:55.");
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
    await screen.findByText("Umeingia kazini saa 07:55.");

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

    expect(await screen.findByText("Uliingia kazini saa 07:55.")).toBeDefined();
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
      await screen.findByText("Umetoka kazini saa 18:02. Kwaheri!"),
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

  it("offers Ingia kazini again after she clocked out, as after lunch", async () => {
    await tappedEarlier(ASHA, "in", MORNING);
    await tappedEarlier(ASHA, "out", new Date("2026-11-13T09:30:00Z"));
    vi.setSystemTime(new Date("2026-11-13T10:25:00Z"));

    await theScreen();

    expect(await screen.findByText("Ulitoka kazini saa 12:30.")).toBeDefined();
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

describe("the screen's words", () => {
  it("speak English to someone who reads it, with no Swahili left", async () => {
    await db().staff.put({ ...ASHA, language: "en" });
    arriveAtCounter({ ...ASHA, language: "en" }, 15);
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
