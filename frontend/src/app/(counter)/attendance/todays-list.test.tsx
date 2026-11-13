// todays-list.test.tsx — the list of who clocked in today on this laptop, under the Mahudhurio button
// (SYNC-11): one line per person, with when they came and, once out, when they left; read live from the
// laptop, so a tap shows at once; and a new day starts empty at midnight, with nothing saved or pulled.
import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import { arriveAtCounter } from "@/features/login/at-the-counter";
import { setLanguage } from "@/i18n/language";
import { DAY_CHECK_EVERY } from "@/offline/clock-today";
import { saveDocument } from "@/offline/outbox";
import { LAST_DEVICE_SEQ, LAST_SERVER_TIME } from "@/offline/sync/meta";
import { shopDatabase } from "@/offline/this-shop";
import { DAWA, DAWA_LAPTOP } from "@/test/devices";
import { swahiliIn } from "@/test/language";
import { staffRow, theLaptopKnows } from "@/test/laptop";
import { render } from "@/test/render";
import { DAWA_SIDE } from "@/test/shop-lists";

import CounterLayout from "../layout";
import AttendancePage from "./page";
import { TodaysList } from "./todays-list";

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

const SERVER_TIME = "2026-11-13T04:00:00Z";
/** 18:05 in Dar on 13 November, by the laptop's clock. */
const EVENING = new Date("2026-11-13T15:05:00Z");

const db = () => shopDatabase(DAWA_LAPTOP.shop.id);

/** A tap saved earlier, as the screen saves one, at `at` by the laptop's clock. */
async function tapped(
  who: typeof ASHA,
  kind: "in" | "out",
  at: string,
): Promise<void> {
  vi.setSystemTime(new Date(at));
  await saveDocument(db(), {
    type: "clock",
    schema_version: 1,
    created_by: who.id,
    payload: { kind, last_server_time: SERVER_TIME },
  });
}

/** The list's rows under its header, each as its cells' text. */
async function rows(): Promise<string[][]> {
  const table = await screen.findByRole("table");
  return within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) =>
      within(row)
        .getAllByRole("cell")
        .map((cell) => cell.textContent ?? ""),
    );
}

// The pretend clock: the time and the timers only, and it still moves on its own (fake-indexeddb runs
// on setImmediate, which must stay real).
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
});

describe("today's list", () => {
  it("names each person once, with when they came and, once out, when they left", async () => {
    await tapped(JUMA, "in", "2026-11-13T04:40:00Z");
    await tapped(ASHA, "in", "2026-11-13T04:55:00Z");
    await tapped(ASHA, "out", "2026-11-13T15:02:00Z");
    vi.setSystemTime(EVENING);

    render(<TodaysList />);

    // Rows first: the list draws nothing until both reads are in.
    expect(await rows()).toEqual([
      ["Juma", "07:40", ""],
      ["Asha", "07:55", "18:02"],
    ]);
    expect(
      screen.getByRole("heading", { name: "Leo kwenye kompyuta hii" }),
    ).toBeDefined();
  });

  it("says so while nobody has clocked in today", async () => {
    vi.setSystemTime(EVENING);

    render(<TodaysList />);

    expect(
      await screen.findByText("Bado hakuna aliyeingia kazini leo."),
    ).toBeDefined();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows a tap the moment it is saved", async () => {
    // Live: the screen reads the laptop's database, and redraws when a save changes it.
    vi.setSystemTime(new Date("2026-11-13T04:55:00Z"));
    arriveAtCounter(ASHA, 15);
    render(
      <CounterLayout>
        <AttendancePage />
      </CounterLayout>,
    );
    await screen.findByText("Bado hakuna aliyeingia kazini leo.");

    fireEvent.click(
      await screen.findByRole("button", { name: "Ingia kazini" }),
    );

    expect(await rows()).toEqual([["Asha", "07:55", ""]]);
  });

  it("starts the new day empty at midnight, by itself", async () => {
    // Asha came late at 23:50; the screen stays open past midnight in Dar.
    await tapped(ASHA, "in", "2026-11-13T20:50:00Z");
    vi.setSystemTime(new Date("2026-11-13T20:59:30Z"));
    render(<TodaysList />);
    expect(await rows()).toEqual([["Asha", "23:50", ""]]);

    await act(() => vi.advanceTimersByTimeAsync(DAY_CHECK_EVERY));

    expect(
      await screen.findByText("Bado hakuna aliyeingia kazini leo."),
    ).toBeDefined();
  });

  it("still lists a tap by someone no longer on the laptop's list", async () => {
    // Juma clocked in, then left the shop's staff; the next pull took his row off the laptop.
    await tapped(JUMA, "in", "2026-11-13T04:40:00Z");
    await db().staff.delete(JUMA.id);
    vi.setSystemTime(EVENING);

    render(<TodaysList />);

    expect(await rows()).toEqual([["Mfanyakazi asiyejulikana", "07:40", ""]]);
  });

  it("leaves out a tap the server refused: the attendance book never got it", async () => {
    // The refused records' warning names it instead (needs-attention.tsx).
    await tapped(JUMA, "in", "2026-11-13T04:40:00Z");
    await tapped(ASHA, "in", "2026-11-13T04:55:00Z");
    const ashas = (await db().documents.toArray()).find(
      (each) => each.created_by === ASHA.id,
    );
    await db().outbox.update(ashas?.id ?? "", {
      status: "needs_attention",
      last_error: "document.maker_unknown",
    });
    vi.setSystemTime(EVENING);

    render(<TodaysList />);

    expect(await rows()).toEqual([["Juma", "07:40", ""]]);
  });

  it("speaks English, with no Swahili left", async () => {
    await tapped(ASHA, "in", "2026-11-13T04:55:00Z");
    vi.setSystemTime(EVENING);
    setLanguage("en");

    const { container } = render(<TodaysList />);

    expect(
      await screen.findByRole("heading", { name: "Today on this laptop" }),
    ).toBeDefined();
    await rows();
    expect(swahiliIn(container)).toEqual([]);
  });
});
