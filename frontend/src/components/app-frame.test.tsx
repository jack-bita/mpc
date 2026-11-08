// app-frame.test.tsx — the counter, office and setup areas put every screen under the green top bar,
// with the language button, and give the page its one <main> (UI-1, UI-3, 03 §7.1); and once someone
// logs in at a device, the bar names them and the side they work on (UI-4).
import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import CounterLayout from "@/app/(counter)/layout";
import OfficeLayout from "@/app/(office)/layout";
import SetupLayout from "@/app/(setup)/layout";
import { saveDevice } from "@/features/devices/this-device";
import { DAWA_LAPTOP } from "@/test/devices";
import { swahiliIn } from "@/test/language";
import { render } from "@/test/render";

import { AppFrame } from "./app-frame";

const AREAS = [
  ["counter", CounterLayout],
  ["office", OfficeLayout],
  ["setup", SetupLayout],
] as const;

describe.each(AREAS)("the %s area", (area, Layout) => {
  it("puts the screen under the top bar, in the page's one <main>", () => {
    const { container } = render(
      <Layout>
        <p>screen</p>
      </Layout>,
    );

    expect(container.querySelector(`[data-area="${area}"]`)).not.toBeNull();
    expect(screen.getByRole("banner")).toBeTruthy();
    expect(screen.getByRole("main").textContent).toBe("screen");
    // The bar comes first, so it is the first thing Tab and a screen reader reach.
    expect(
      screen
        .getByRole("banner")
        .compareDocumentPosition(screen.getByRole("main")),
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("switches to English from the bar, with no Swahili left", () => {
    const { container } = render(
      <Layout>
        <p>screen</p>
      </Layout>,
    );

    fireEvent.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByRole("button", { name: "Kiswahili" })).toBeTruthy();
    expect(swahiliIn(container)).toEqual([]);
  });
});

describe("the bar once someone logs in", () => {
  it("names the device's shop and home side while nobody is logged in", () => {
    saveDevice(DAWA_LAPTOP);

    render(
      <AppFrame area="login">
        <p>screen</p>
      </AppFrame>,
    );

    expect(
      within(screen.getByRole("banner")).getByText("MPC · Dawa"),
    ).toBeTruthy();
  });

  it("names the person, and the side they work on in place of the device's", () => {
    // Neema works on Vyakula, and logs in at the Dawa laptop.
    saveDevice(DAWA_LAPTOP);

    render(
      <AppFrame area="login" person="Neema" side={{ name: "Vyakula" }}>
        <p>screen</p>
      </AppFrame>,
    );

    const bar = within(screen.getByRole("banner"));
    expect(bar.getByText("MPC · Vyakula")).toBeTruthy();
    expect(bar.getByText("Neema")).toBeTruthy();
  });

  it("names the shop of who is logged in, on a phone that knows no device", () => {
    // A manager's own phone never registers, so only the login says which shop it is at (UI-5).
    render(
      <AppFrame area="office" shop="MPC" person="Neema">
        <p>screen</p>
      </AppFrame>,
    );

    const bar = within(screen.getByRole("banner"));
    expect(bar.getByText("MPC")).toBeTruthy();
    expect(bar.getByText("Neema")).toBeTruthy();
  });

  it("puts a screen's own buttons in the bar, before the language button", () => {
    render(
      <AppFrame area="login" actions={<button type="button">Toka</button>}>
        <p>screen</p>
      </AppFrame>,
    );

    const buttons = within(screen.getByRole("banner")).getAllByRole("button");
    expect(buttons.map((button) => button.textContent)).toEqual([
      "Toka",
      "English",
    ]);
  });
});
