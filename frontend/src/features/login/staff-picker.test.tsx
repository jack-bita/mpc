// staff-picker.test.tsx — the PIN screen's first step on a shared laptop: a tile for each person who works
// at the shop, and a tap on your own (UI-4, 03 §5.9). The list comes from the device's own route, which the
// fake server answers here.
import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { setLanguage } from "@/i18n/language";
import { answer, refusal } from "@/test/fake-server";
import { swahiliIn } from "@/test/language";
import { render } from "@/test/render";

import { type PinScreenStaff, StaffPicker } from "./staff-picker";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const STAFF = "/api/devices/v1/staff/";

// Fake people: made-up names. In the server's order, A to Z by full name.
const ASHA: PinScreenStaff = {
  id: "019a5e00-0000-7000-8000-0000000000c2",
  full_name: "Asha Mfano",
  display_name: "Asha",
};
const JUMA: PinScreenStaff = {
  id: "019a5e00-0000-7000-8000-0000000000c3",
  full_name: "Juma Mfano",
  display_name: "Juma",
};

/** Everyone's tile, as a screen reader lists them. */
async function tiles() {
  const list = await screen.findByRole("list");
  return within(list).getAllByRole("button");
}

describe("the staff picker", () => {
  it("asks who you are, with a tile for each person, in the server's order", async () => {
    answer("GET", STAFF, { status: 200, body: [ASHA, JUMA] });
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

  it("picks the person whose tile is tapped", async () => {
    answer("GET", STAFF, { status: 200, body: [ASHA, JUMA] });
    const picked = vi.fn();
    render(<StaffPicker onPick={picked} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Juma Mfano Juma" }),
    );

    expect(picked).toHaveBeenCalledOnce();
    expect(picked).toHaveBeenCalledWith(JUMA);
  });

  it("has big tiles, sized for a finger at the counter", async () => {
    answer("GET", STAFF, { status: 200, body: [ASHA, JUMA] });
    render(<StaffPicker onPick={vi.fn()} />);

    for (const tile of await tiles())
      expect(tile.className).toContain("min-h-(--control-big)");
  });

  it("says so when nobody works here yet", async () => {
    // A new shop, before the owner adds its people: no tile to tap, and the reason why.
    answer("GET", STAFF, { status: 200, body: [] });
    render(<StaffPicker onPick={vi.fn()} />);

    expect(
      await screen.findByText(
        "Bado hakuna mfanyakazi hapa. Mwombe mwenye duka awaongeze.",
      ),
    ).toBeDefined();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("shows a refusal in the shop's words", async () => {
    // A browser that isn't a registered device: the route is only for the shop's own.
    answer("GET", STAFF, refusal(401, "not_authenticated"));
    render(<StaffPicker onPick={vi.fn()} />);

    expect(await screen.findByText("Ingia kwanza.")).toBeDefined();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("speaks English after the switch, with no Swahili left", async () => {
    setLanguage("en");
    answer("GET", STAFF, { status: 200, body: [] });
    const { container } = render(<StaffPicker onPick={vi.fn()} />);

    expect(
      await screen.findByText(
        "No one works here yet. Ask the shop's owner to add the staff.",
      ),
    ).toBeDefined();
    expect(screen.getByRole("heading", { name: "Who are you?" })).toBeDefined();
    expect(swahiliIn(container)).toEqual([]);
  });
});
