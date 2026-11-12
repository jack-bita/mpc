// staff-picker.test.tsx — the PIN screen's first step on a shared laptop: a tile for each person who works
// at the shop, and a tap on your own (UI-4, 03 §5.9). The list is the laptop's own copy of the staff
// (SYNC-10), so it shows with no network, and the server is never asked.
import { act, fireEvent, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { saveDevice } from "@/features/devices/this-device";
import { setLanguage } from "@/i18n/language";
import { shopDatabase } from "@/offline/this-shop";
import { DAWA_LAPTOP } from "@/test/devices";
import { sent } from "@/test/fake-server";
import { swahiliIn } from "@/test/language";
import { staffRow, theLaptopKnows } from "@/test/laptop";
import { render } from "@/test/render";

import { StaffPicker } from "./staff-picker";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

// Fake people: made-up names.
const ASHA = staffRow(
  "019a5e00-0000-7000-8000-0000000000c2",
  "Asha Mfano",
  "Asha",
);
const JUMA = staffRow(
  "019a5e00-0000-7000-8000-0000000000c3",
  "Juma Mfano",
  "Juma",
);

/** Everyone's tile, as a screen reader lists them. */
async function tiles() {
  const list = await screen.findByRole("list");
  return within(list).getAllByRole("button");
}

// The Dawa laptop, registered. Each test fills its database as it needs.
beforeEach(() => saveDevice(DAWA_LAPTOP));

describe("the staff picker", () => {
  it("asks who you are, with a tile for each person, A to Z", async () => {
    // Saved in the other order: the tiles sort them, as the server did.
    await theLaptopKnows(JUMA, ASHA);
    render(<StaffPicker onPick={vi.fn()} />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeDefined();
    expect((await tiles()).map((tile) => tile.textContent)).toEqual([
      "Asha Mfano Asha",
      "Juma Mfano Juma",
    ]);
    // Named as a screen reader says it: the full name, a space, the nickname. Without the space it says
    // "Asha MfanoAsha", one word.
    const asha = screen.getByRole("button", { name: "Asha Mfano Asha" });
    // The full name in large letters, the nickname under it, until photos come (PPL-4; 02 §5).
    expect(within(asha).getByText("Asha Mfano").className).toContain(
      "text-2xl",
    );
    expect(within(asha).getByText("Asha")).toBeDefined();
  });

  it("shows the tiles with no network, and never asks the server", async () => {
    // The way in to an offline PIN login (SYNC-10).
    await theLaptopKnows(ASHA, JUMA);
    render(<StaffPicker onPick={vi.fn()} />);

    expect(await tiles()).toHaveLength(2);
    expect(sent).toEqual([]);
  });

  it("puts the keyboard on its question as it shows", async () => {
    // A screen reader says where the person is; Tab goes on from the question to the tiles.
    await theLaptopKnows(ASHA, JUMA);
    render(<StaffPicker onPick={vi.fn()} />);

    // The heading itself, not only its words: the page's <body> holds the same words until the tiles come.
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    );
  });

  it("picks the person whose tile is tapped", async () => {
    await theLaptopKnows(ASHA, JUMA);
    const picked = vi.fn();
    render(<StaffPicker onPick={picked} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Juma Mfano Juma" }),
    );

    expect(picked).toHaveBeenCalledOnce();
    expect(picked).toHaveBeenCalledWith(JUMA);
  });

  it("has big tiles, sized for a finger at the counter", async () => {
    await theLaptopKnows(ASHA, JUMA);
    render(<StaffPicker onPick={vi.fn()} />);

    for (const tile of await tiles())
      expect(tile.className).toContain("min-h-(--control-big)");
  });

  it("gives a suspended person no tile", async () => {
    // Her row says so since the last sync: she can't log in today, online or off (X2).
    await theLaptopKnows(ASHA, { ...JUMA, status: "suspended" });
    render(<StaffPicker onPick={vi.fn()} />);

    expect((await tiles()).map((tile) => tile.textContent)).toEqual([
      "Asha Mfano Asha",
    ]);
  });

  it("gives a tile to someone a sync adds, with no reload", async () => {
    await theLaptopKnows(ASHA);
    render(<StaffPicker onPick={vi.fn()} />);
    expect(await tiles()).toHaveLength(1);

    // What a pull writes when the owner adds Juma in the office.
    await act(() => shopDatabase(DAWA_LAPTOP.shop.id).staff.put(JUMA));

    expect(
      await screen.findByRole("button", { name: "Juma Mfano Juma" }),
    ).toBeDefined();
  });

  it("says so when nobody works here yet", async () => {
    // A new shop, before the owner adds its people: no tile to tap, and the reason why.
    await theLaptopKnows();
    render(<StaffPicker onPick={vi.fn()} />);

    expect(
      await screen.findByText(
        "Bado hakuna mfanyakazi hapa. Mwombe mwenye duka awaongeze.",
      ),
    ).toBeDefined();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("waits for the first sync on a laptop just registered", async () => {
    // No copy yet: the shop isn't empty, the laptop just doesn't know its people.
    render(<StaffPicker onPick={vi.fn()} />);

    expect(
      await screen.findByText(
        "Subiri kidogo: kompyuta hii inaleta orodha ya wafanyakazi kwa mara ya kwanza.",
      ),
    ).toBeDefined();
    expect(
      screen.queryByText(
        "Bado hakuna mfanyakazi hapa. Mwombe mwenye duka awaongeze.",
      ),
    ).toBeNull();
  });

  it("speaks English after the switch, with no Swahili left", async () => {
    setLanguage("en");
    await theLaptopKnows();
    const { container } = render(<StaffPicker onPick={vi.fn()} />);

    expect(
      await screen.findByText(
        "No one works here yet. Ask the shop's owner to add the staff.",
      ),
    ).toBeDefined();
    expect(screen.getByRole("heading", { name: "Who are you?" })).toBeDefined();
    expect(swahiliIn(container)).toEqual([]);
  });

  it("speaks English while it waits for the first sync", async () => {
    setLanguage("en");
    const { container } = render(<StaffPicker onPick={vi.fn()} />);

    expect(
      await screen.findByText(
        "Wait a moment: this laptop is getting the staff list for the first time.",
      ),
    ).toBeDefined();
    expect(swahiliIn(container)).toEqual([]);
  });
});
