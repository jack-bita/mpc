// staff-picker.test.tsx — the PIN screen's first step on a shared laptop: a tile for each person who works
// at the shop, and a tap on your own (UI-4, 03 §5.9). The list is the laptop's own copy of the staff
// (SYNC-10), so it shows with no network, and the server is never asked.
import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DEMO_LOGINS_KEY,
  DEMO_PINS_KEY,
  saveLogins,
  savePins,
} from "@/features/devices/demo-pins";
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
// The demo's manager: a password and no PIN, as the seed makes him (apps/demo/services.py). A made-up name
// of his own here: "Meneja" is a word of the Swahili book, which the English test would flag.
const MENEJA = {
  ...staffRow("019a5e00-0000-7000-8000-0000000000c1", "Neema Mfano", "Neema"),
  pin_changed_at: null,
};
// What one tap on Jaribu demo kept for him: the demo's public login (OPS-13).
const MENEJA_LOGIN = {
  staff_id: MENEJA.id,
  login: "meneja@example.com",
  password: "jaribu-demo",
};

/** Everyone's tile, as a screen reader lists them. */
async function tiles() {
  const list = await screen.findByRole("list");
  return within(list).getAllByRole("button");
}

// The Dawa laptop, registered. Each test fills its database as it needs.
beforeEach(() => saveDevice(DAWA_LAPTOP));
afterEach(() => {
  window.localStorage.removeItem(DEMO_PINS_KEY);
  window.localStorage.removeItem(DEMO_LOGINS_KEY);
});

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
    // The full name in large letters, the nickname under it, until photos come (PPL-14; 02 §5).
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

  it("gives someone with no PIN no tile", async () => {
    // Juma was added in the office, and has no PIN yet: a tile would lead to a PIN pad that can't let him in. On
    // the demo, a visitor's made-up workers never get one, so they never crowd the tiles of every visitor after
    // (Jack, PPL-4's review: A). His tile comes with his PIN, at the next sync.
    await theLaptopKnows(ASHA, { ...JUMA, pin_changed_at: null });
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

  it("shows a demo seller's PIN under their names, and none for the others", async () => {
    // One tap on Jaribu demo kept Asha's PIN (OPS-3). Juma, who has none kept, gets a plain tile.
    savePins([{ staff_id: ASHA.id, pin: "2580" }]);
    await theLaptopKnows(ASHA, JUMA);
    render(<StaffPicker onPick={vi.fn()} />);

    expect((await tiles()).map((tile) => tile.textContent)).toEqual([
      "Asha Mfano Asha PIN 2580",
      "Juma Mfano Juma",
    ]);
  });

  it("shows no PIN on a laptop that never tried the demo, nor one kept for other people", async () => {
    // A real shop's laptop keeps none; yesterday's demo kept PINs of people the reset made again with new
    // ids, which match no tile of today's.
    savePins([
      { staff_id: "019a5e00-0000-7000-8000-0000000000ff", pin: "2580" },
    ]);
    await theLaptopKnows(ASHA, JUMA);
    render(<StaffPicker onPick={vi.fn()} />);

    expect((await tiles()).map((tile) => tile.textContent)).toEqual([
      "Asha Mfano Asha",
      "Juma Mfano Juma",
    ]);
  });

  it("gives the demo's manager a tile that opens the password login, never the PIN pad", async () => {
    // He has no PIN, so PPL-4's rule took his tile away; one tap on Jaribu demo kept his login, so it is back
    // (OPS-13). A link, not a button: it goes to the login page, with his id for it to fill the boxes.
    saveLogins([MENEJA_LOGIN]);
    await theLaptopKnows(ASHA, MENEJA);
    const picked = vi.fn();
    render(<StaffPicker onPick={picked} />);

    const tile = await screen.findByRole("link", {
      name: "Neema Mfano Neema Ingia kwa nenosiri",
    });
    // The app's pages end in a slash (`/login/`), which the test's stand-in for Next's link leaves off.
    expect(tile.getAttribute("href")).toMatch(
      new RegExp(`^/login/?\\?as=${MENEJA.id}$`),
    );
    // Sized as every tile, and in the same A to Z list as the sellers.
    expect(tile.className).toContain("min-h-(--control-big)");
    const list = within(await screen.findByRole("list"));
    expect(
      list.getAllByRole("listitem").map((item) => item.textContent),
    ).toEqual(["Asha Mfano Asha", "Neema Mfano Neema Ingia kwa nenosiri"]);
    // A tap never picks him for the pad: the pad can't let in someone with no PIN.
    fireEvent.click(tile);
    expect(picked).not.toHaveBeenCalled();
  });

  it("keeps the PIN pad for someone with a PIN, a login kept for them or not", async () => {
    // The server hands over a login only for someone with no PIN (_demo_logins), but the tile never trusts
    // that alone: Asha has a PIN, so her tile picks her for the pad, and opens no password page (OPS-13's
    // review).
    saveLogins([{ ...MENEJA_LOGIN, staff_id: ASHA.id }]);
    await theLaptopKnows(ASHA);
    const picked = vi.fn();
    render(<StaffPicker onPick={picked} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Asha Mfano Asha" }),
    );
    expect(picked).toHaveBeenCalledWith(ASHA);
    expect(screen.queryByRole("link", { name: /Asha/ })).toBeNull();
  });

  it("gives no tile for a login kept for other people", async () => {
    // Yesterday's demo kept a login of a Meneja the reset made again with a new id: today's Meneja, with no PIN,
    // gets no tile from it, as on a real shop's laptop, which keeps none.
    saveLogins([
      { ...MENEJA_LOGIN, staff_id: "019a5e00-0000-7000-8000-0000000000ff" },
    ]);
    await theLaptopKnows(ASHA, MENEJA);
    render(<StaffPicker onPick={vi.fn()} />);

    expect((await tiles()).map((tile) => tile.textContent)).toEqual([
      "Asha Mfano Asha",
    ]);
    expect(screen.queryByRole("link", { name: /Neema/ })).toBeNull();
  });

  it("gives a suspended manager no tile, his login kept or not", async () => {
    // A login opens no door the server shut (X2): no tile for him, as for anyone suspended.
    saveLogins([MENEJA_LOGIN]);
    await theLaptopKnows(ASHA, { ...MENEJA, status: "suspended" });
    render(<StaffPicker onPick={vi.fn()} />);

    expect((await tiles()).map((tile) => tile.textContent)).toEqual([
      "Asha Mfano Asha",
    ]);
    expect(screen.queryByRole("link", { name: /Neema/ })).toBeNull();
  });

  it("offers the password button under a real shop's tiles", async () => {
    // Baba, the owner, has a password and no PIN, so no tile: the button is his way in at the laptop (Jack,
    // 8 Nov 2026, at UI-5's review).
    await theLaptopKnows(ASHA, JUMA);
    render(<StaffPicker onPick={vi.fn()} />);

    const link = await screen.findByRole("link", {
      name: "Ingia kwa nenosiri",
    });
    // The end slash comes from next.config.ts (trailingSlash), which a test doesn't read.
    expect(link.getAttribute("href")).toMatch(/^\/login\/?$/);
  });

  it("offers it before the first sync, and on a shop with nobody yet", async () => {
    // No tile at all yet: the owner still gets in, to add the staff.
    const { unmount } = render(<StaffPicker onPick={vi.fn()} />);
    expect(
      await screen.findByRole("link", { name: "Ingia kwa nenosiri" }),
    ).toBeDefined();
    unmount();

    await theLaptopKnows();
    render(<StaffPicker onPick={vi.fn()} />);
    expect(
      await screen.findByRole("link", { name: "Ingia kwa nenosiri" }),
    ).toBeDefined();
  });

  it("offers no password button on the demo before the first sync either", async () => {
    // Just after the tap, the laptop waits for its first copy of the staff, which brings Meneja's tile: the
    // button would show for that moment, and lead a visitor to an empty form (OPS-13's review).
    saveLogins([MENEJA_LOGIN]);
    render(<StaffPicker onPick={vi.fn()} />);

    expect(
      await screen.findByText(
        "Subiri kidogo: kompyuta hii inaleta orodha ya wafanyakazi kwa mara ya kwanza.",
      ),
    ).toBeDefined();
    expect(
      screen.queryByRole("link", { name: "Ingia kwa nenosiri" }),
    ).toBeNull();
  });

  it("offers no password button on the demo, where the manager's tile does its job", async () => {
    // Asha and Baraka have PINs, and Meneja his own tile: a second way to the same page would only make a
    // visitor wonder which to take (Jack, OPS-13).
    saveLogins([MENEJA_LOGIN]);
    await theLaptopKnows(ASHA, MENEJA);
    render(<StaffPicker onPick={vi.fn()} />);

    await screen.findByRole("link", {
      name: "Neema Mfano Neema Ingia kwa nenosiri",
    });
    expect(
      screen.queryByRole("link", { name: "Ingia kwa nenosiri" }),
    ).toBeNull();
  });

  it("speaks English on the demo manager's tile", async () => {
    setLanguage("en");
    saveLogins([MENEJA_LOGIN]);
    await theLaptopKnows(MENEJA);
    const { container } = render(<StaffPicker onPick={vi.fn()} />);

    expect(
      await screen.findByRole("link", {
        name: "Neema Mfano Neema Log in with a password",
      }),
    ).toBeDefined();
    expect(swahiliIn(container)).toEqual([]);
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
