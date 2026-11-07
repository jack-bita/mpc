// pin-login.test.tsx — logging in by PIN at a shop's laptop: pick yourself, type your PIN, and the server
// answers (UI-4, 03 §5.9). The picker and the pad have tests of their own; these follow the whole way, with
// the fake server answering as AUTH-4's route does.
import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import { ApiRefusal } from "@/api/refusal";
import { DeviceCheck } from "@/features/devices/device-check";
import { savedBlocked } from "@/features/devices/this-device";
import { setLanguage } from "@/i18n/language";
import { DAWA_LAPTOP_ANSWER } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { swahiliIn } from "@/test/language";
import { render } from "@/test/render";

import { PinLogin } from "./pin-login";
import type { PinScreenStaff } from "./staff-picker";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const STAFF = "/api/devices/v1/staff/";
const PIN_LOGIN = "/api/auth/pin-login/";
const DEVICE_ME = "/api/devices/v1/me/";

// Fake people: made-up names.
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

/** The laptop's two people, and how the PIN login answers. */
function theShop(login: Parameters<typeof answer>[2]) {
  answer("GET", STAFF, { status: 200, body: [ASHA, JUMA] });
  answer("POST", PIN_LOGIN, login);
}

/** Asha taps her tile, then types `pin` on the pad. */
async function ashaTypes(pin: string) {
  fireEvent.click(
    await screen.findByRole("button", { name: "Asha Mfano Asha" }),
  );
  for (const digit of pin)
    fireEvent.click(screen.getByRole("button", { name: digit }));
}

describe("the pin login", () => {
  it("asks the person picked for their PIN, under their name", async () => {
    theShop({ status: 204 });
    render(<PinLogin />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Asha Mfano Asha" }),
    );

    expect(
      screen.getByRole("heading", { level: 1, name: "Asha Mfano" }),
    ).toBeDefined();
    expect(screen.getByText("Andika PIN yako")).toBeDefined();
    expect(screen.queryByRole("heading", { name: "Wewe ni nani?" })).toBeNull();
  });

  it("sends who and the PIN, then forgets the last person's answers", async () => {
    theShop({ status: 204 });
    // The store as the last person left it: a list from their last screen (UI-2's note on UI-4).
    const store = makeQueryClient();
    store.setQueryData(["devices", "list"], ["Laptop Dawa"]);
    render(
      <QueryClientProvider client={store}>
        <PinLogin />
      </QueryClientProvider>,
    );

    await ashaTypes("4829");

    await vi.waitFor(() =>
      expect(store.getQueryData(["devices", "list"])).toBeUndefined(),
    );
    const login = sent.find((request) => request.method === "POST");
    expect(new URL(login?.url ?? "").pathname).toBe(PIN_LOGIN);
    expect(await login?.json()).toEqual({ staff: ASHA.id, pin: "4829" });
  });

  it("says a wrong PIN is wrong, with the pad ready for the next try", async () => {
    theShop(refusal(400, "pin.wrong"));
    render(<PinLogin />);

    await ashaTypes("4830");

    expect(await screen.findByText("PIN si sahihi.")).toBeDefined();
    expect(screen.getByText("Umeandika tarakimu 0 kati ya 4")).toBeDefined();
    // She types again, and it is sent again.
    for (const digit of "4829")
      fireEvent.click(screen.getByRole("button", { name: digit }));
    await vi.waitFor(() =>
      expect(sent.filter((request) => request.method === "POST")).toHaveLength(
        2,
      ),
    );
  });

  it("says how many minutes a locked person waits", async () => {
    // The fifth wrong PIN locks her on this laptop for a minute, doubling each time (AUTH-4): the server
    // sends the wait in seconds, the screen says minutes.
    theShop(refusal(400, "pin.locked", { wait: 300 }));
    render(<PinLogin />);

    await ashaTypes("4830");

    expect(
      await screen.findByText(
        "PIN zimekosewa mara nyingi. Jaribu tena baada ya dakika 5.",
      ),
    ).toBeDefined();
  });

  it("tells a suspended person why", async () => {
    theShop(refusal(403, "staff.suspended"));
    render(<PinLogin />);

    await ashaTypes("4829");

    expect(
      await screen.findByText("Umesimamishwa. Ongea na meneja au mmiliki."),
    ).toBeDefined();
  });

  it("takes no key and no Rudi while the PIN is on its way", async () => {
    // A slow 3G answer: nothing the person taps meanwhile may send a second PIN, nor leave the step, as
    // the answer could still log her in behind the picker.
    theShop(() => new Promise<Response>(() => {}));
    render(<PinLogin />);

    await ashaTypes("4829");

    await vi.waitFor(() =>
      expect(
        (screen.getByRole("button", { name: "1" }) as HTMLButtonElement)
          .disabled,
      ).toBe(true),
    );
    expect(
      (screen.getByRole("button", { name: "Rudi" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("goes back to the picker with Rudi, and forgets the last refusal", async () => {
    // Juma tapped Asha's tile by mistake and typed his own PIN.
    theShop(refusal(400, "pin.wrong"));
    render(<PinLogin />);
    await ashaTypes("4830");
    await screen.findByText("PIN si sahihi.");

    fireEvent.click(screen.getByRole("button", { name: "Rudi" }));

    expect(
      screen.getByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Juma Mfano Juma" }));
    expect(screen.queryByText("PIN si sahihi.")).toBeNull();
  });

  it("shows why the last session ended above the picker, until someone is picked", async () => {
    // `me` refused the last session: the person was suspended while logged in (AUTH-4).
    theShop({ status: 204 });
    const ended = new ApiRefusal(403, {
      code: "staff.suspended",
      message: "",
      fields: {},
      params: {},
    });
    render(<PinLogin notice={ended} />);

    expect(
      await screen.findByText("Umesimamishwa. Ongea na meneja au mmiliki."),
    ).toBeDefined();
    // The tiles come a moment after the notice, with the server's answer.
    fireEvent.click(
      await screen.findByRole("button", { name: "Juma Mfano Juma" }),
    );
    expect(
      screen.queryByText("Umesimamishwa. Ongea na meneja au mmiliki."),
    ).toBeNull();
  });

  it("tells the home page when a tile is tapped, so it can drop the notice for good", async () => {
    theShop({ status: 204 });
    const picked = vi.fn();
    render(<PinLogin onPick={picked} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Juma Mfano Juma" }),
    );

    expect(picked).toHaveBeenCalledOnce();
  });

  it("locks the app when the server says this laptop is blocked", async () => {
    // Sent through the store, so the device's check hears of the block and the lock comes at once
    // (noticeBlock, UI-3): a call sent around the store would leave the laptop open.
    answer("GET", DEVICE_ME, { status: 200, body: DAWA_LAPTOP_ANSWER });
    theShop(refusal(401, "device.blocked"));
    render(
      <>
        <DeviceCheck />
        <PinLogin />
      </>,
    );

    await ashaTypes("4829");

    await vi.waitFor(() => expect(savedBlocked()).toBe(true));
  });

  it("speaks English after the switch, with no Swahili left", async () => {
    setLanguage("en");
    theShop(refusal(400, "pin.wrong"));
    const { container } = render(<PinLogin />);

    await ashaTypes("4830");

    expect(await screen.findByText("Wrong PIN.")).toBeDefined();
    expect(screen.getByText("Type your PIN")).toBeDefined();
    expect(screen.getByRole("button", { name: "Back" })).toBeDefined();
    expect(swahiliIn(container)).toEqual([]);
  });
});
