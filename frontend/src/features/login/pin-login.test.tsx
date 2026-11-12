// pin-login.test.tsx — logging in by PIN at a shop's laptop: pick yourself, type your PIN, and the server
// answers (UI-4, 03 §5.9). The picker and the pad have tests of their own; these follow the whole way, with
// the fake server answering as AUTH-4's route does.
import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import { ApiRefusal } from "@/api/refusal";
import { DeviceCheck } from "@/features/devices/device-check";
import { savedBlocked } from "@/features/devices/this-device";
import { setLanguage } from "@/i18n/language";
import { saveDevice } from "@/features/devices/this-device";
import { DAWA_LAPTOP, DAWA_LAPTOP_ANSWER } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { swahiliIn } from "@/test/language";
import { staffRow, theLaptopKnows } from "@/test/laptop";
import { FEW_TURNS } from "@/test/pins";
import { render } from "@/test/render";

import { checkPinOffline, rememberPin } from "@/offline/pin";
import { shopDatabase } from "@/offline/this-shop";

import { PinLogin } from "./pin-login";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const PIN_LOGIN = "/api/auth/pin-login/";
const DEVICE_ME = "/api/devices/v1/me/";

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

/** The Dawa laptop, registered, with its two people on it (their tiles come from its own copy, SYNC-10),
 * and how the PIN login answers. */
async function theShop(login: Parameters<typeof answer>[2]) {
  saveDevice(DAWA_LAPTOP);
  await theLaptopKnows(ASHA, JUMA);
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
    await theShop({ status: 204 });
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

  it("moves the keyboard to each step's heading, and back to it after a refusal", async () => {
    // The tile tapped, Rudi and a key switched off while the PIN is away all leave the page: focus would
    // fall to nothing, and a screen reader would say nothing of the new step (UI-3 did this for its forms).
    await theShop(refusal(400, "pin.wrong"));
    render(<PinLogin />);

    await ashaTypes("4830");
    await screen.findByText("PIN si sahihi.");
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { level: 1, name: "Asha Mfano" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Rudi" }));
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    );
  });

  it("sends who and the PIN, then forgets the last person's answers", async () => {
    await theShop({ status: 204 });
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
    await theShop(refusal(400, "pin.wrong"));
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

  it("keeps no PIN once the server has answered", async () => {
    // Juma tapped Asha's tile by mistake and typed his own PIN: wrong for her, but his real one. Kept, it
    // would sit in the laptop's memory, readable in the browser's tools, after he walks away.
    await theShop(refusal(400, "pin.wrong"));
    const store = makeQueryClient();
    render(
      <QueryClientProvider client={store}>
        <PinLogin />
      </QueryClientProvider>,
    );

    await ashaTypes("4830");
    await screen.findByText("PIN si sahihi.");

    const held = () =>
      JSON.stringify(
        store
          .getMutationCache()
          .getAll()
          .map((change) => change.state.variables),
      );
    expect(held()).not.toContain("4830");
    // Rudi, and the try itself is let go of: the store's list of changes is empty.
    fireEvent.click(screen.getByRole("button", { name: "Rudi" }));
    await vi.waitFor(() =>
      expect(store.getMutationCache().getAll()).toEqual([]),
    );
  });

  it("says how many minutes a locked person waits", async () => {
    // The fifth wrong PIN locks her on this laptop for a minute, doubling each time (AUTH-4): the server
    // sends the wait in seconds, the screen says minutes.
    await theShop(refusal(400, "pin.locked", { wait: 300 }));
    render(<PinLogin />);

    await ashaTypes("4830");

    expect(
      await screen.findByText(
        "PIN zimekosewa mara nyingi. Jaribu tena baada ya dakika 5.",
      ),
    ).toBeDefined();
  });

  it("tells a suspended person why", async () => {
    await theShop(refusal(403, "staff.suspended"));
    render(<PinLogin />);

    await ashaTypes("4829");

    expect(
      await screen.findByText("Umesimamishwa. Ongea na meneja au mmiliki."),
    ).toBeDefined();
  });

  it("takes no key and no Rudi while the PIN is on its way", async () => {
    // A slow 3G answer: nothing the person taps meanwhile may send a second PIN, nor leave the step, as
    // the answer could still log her in behind the picker.
    await theShop(() => new Promise<Response>(() => {}));
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
    await theShop(refusal(400, "pin.wrong"));
    render(<PinLogin />);
    await ashaTypes("4830");
    await screen.findByText("PIN si sahihi.");

    fireEvent.click(screen.getByRole("button", { name: "Rudi" }));

    expect(
      screen.getByRole("heading", { level: 1, name: "Wewe ni nani?" }),
    ).toBeDefined();
    // The tiles come a moment after the question: the picker reads the laptop's copy again.
    fireEvent.click(
      await screen.findByRole("button", { name: "Juma Mfano Juma" }),
    );
    expect(screen.queryByText("PIN si sahihi.")).toBeNull();
  });

  it("shows why the last session ended above the picker, until someone is picked", async () => {
    // `me` refused the last session: the person was suspended while logged in (AUTH-4).
    await theShop({ status: 204 });
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
    await theShop({ status: 204 });
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
    await theShop(refusal(401, "device.blocked"));
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
    await theShop(refusal(400, "pin.wrong"));
    const { container } = render(<PinLogin />);

    await ashaTypes("4830");

    expect(await screen.findByText("Wrong PIN.")).toBeDefined();
    expect(screen.getByText("Type your PIN")).toBeDefined();
    expect(screen.getByRole("button", { name: "Back" })).toBeDefined();
    expect(swahiliIn(container)).toEqual([]);
  });
});

describe("the pin login with no network (SYNC-10)", () => {
  const db = () => shopDatabase(DAWA_LAPTOP.shop.id);
  // Asha logged in here online before, with 2580: the laptop saved its check of it.
  const ashaWasHereOnline = () => rememberPin(db(), ASHA.id, "2580", FEW_TURNS);
  const noNetwork = () =>
    vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(false);
  const posts = () => sent.filter((request) => request.method === "POST");

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lets in someone who logged in once online here, and sends nothing", async () => {
    await theShop({ status: 204 });
    await ashaWasHereOnline();
    noNetwork();
    const arrived = vi.fn();
    render(<PinLogin onOffline={arrived} />);

    await ashaTypes("2580");

    // Handed to the home page, which starts her local session.
    await vi.waitFor(() =>
      expect(arrived).toHaveBeenCalledWith(
        expect.objectContaining({ id: ASHA.id }),
      ),
    );
    expect(posts()).toEqual([]);
  });

  it("tells someone who never logged in here online to do that once", async () => {
    await theShop({ status: 204 });
    noNetwork();
    render(<PinLogin onOffline={vi.fn()} />);

    await ashaTypes("2580");

    expect(
      await screen.findByText(
        "Kompyuta hii haiwezi kuthibitisha PIN yako bila mtandao bado. Ingia mara moja hapa mtandao ukiwepo, kisha utaweza kuingia hata bila mtandao.",
      ),
    ).toBeDefined();
  });

  it("says a wrong PIN is wrong, in the server's words", async () => {
    await theShop({ status: 204 });
    await ashaWasHereOnline();
    noNetwork();
    const arrived = vi.fn();
    render(<PinLogin onOffline={arrived} />);

    await ashaTypes("2581");

    expect(await screen.findByText("PIN si sahihi.")).toBeDefined();
    expect(arrived).not.toHaveBeenCalled();
  });

  it("locks her for a minute after five wrong PINs", async () => {
    await theShop({ status: 204 });
    await ashaWasHereOnline();
    noNetwork();
    render(<PinLogin onOffline={vi.fn()} />);

    await ashaTypes("2581");
    for (let tries = 2; tries <= 5; tries++) {
      // The pad comes back after each answer: wait for it, then type again.
      await vi.waitFor(() =>
        expect(
          (screen.getByRole("button", { name: "2" }) as HTMLButtonElement)
            .disabled,
        ).toBe(false),
      );
      for (const digit of "2581")
        fireEvent.click(screen.getByRole("button", { name: digit }));
    }

    expect(
      await screen.findByText(
        "PIN zimekosewa mara nyingi. Jaribu tena baada ya dakika 1.",
      ),
    ).toBeDefined();
  });

  it("checks on the laptop when the home page says the server is away", async () => {
    // The network is on, but `me` got no answer, or a logout waits unheard: nothing is sent.
    await theShop({ status: 204 });
    await ashaWasHereOnline();
    const arrived = vi.fn();
    render(<PinLogin serverAway onOffline={arrived} />);

    await ashaTypes("2580");

    await vi.waitFor(() => expect(arrived).toHaveBeenCalledOnce());
    expect(posts()).toEqual([]);
  });

  it("checks on the laptop when the server gives no answer", async () => {
    // The network went as the PIN was sent.
    await theShop(() => {
      throw new TypeError("Failed to fetch");
    });
    await ashaWasHereOnline();
    const arrived = vi.fn();
    render(<PinLogin onOffline={arrived} />);

    await ashaTypes("2580");

    await vi.waitFor(() => expect(arrived).toHaveBeenCalledOnce());
  });

  it("checks on the laptop when the server is broken", async () => {
    // A deploy's 502, as the server restarts.
    await theShop(refusal(502, "server_error"));
    await ashaWasHereOnline();
    const arrived = vi.fn();
    render(<PinLogin onOffline={arrived} />);

    await ashaTypes("2580");

    await vi.waitFor(() => expect(arrived).toHaveBeenCalledOnce());
  });

  it("keeps the server's no, never asking the laptop", async () => {
    // A manager gave Asha a new PIN; this laptop hasn't pulled it yet. The server knows best: 2580 is wrong.
    await theShop(refusal(400, "pin.wrong"));
    await ashaWasHereOnline();
    const arrived = vi.fn();
    render(<PinLogin onOffline={arrived} />);

    await ashaTypes("2580");

    expect(await screen.findByText("PIN si sahihi.")).toBeDefined();
    expect(arrived).not.toHaveBeenCalled();
  });

  it("saves the laptop's check of a PIN the server said yes to", async () => {
    // Her first online login here: from now on she can log in on this laptop with no network.
    await theShop({ status: 204 });
    render(<PinLogin />);

    await ashaTypes("2580");

    // Made at the real cost, after the answer, so she never waits for it.
    await vi.waitFor(
      async () => expect(await db().pin_checks.get(ASHA.id)).toBeDefined(),
      { timeout: 3000 },
    );
    expect(await checkPinOffline(db(), ASHA.id, "2580")).toMatchObject({
      id: ASHA.id,
    });
  });

  it("keeps no PIN once the laptop has answered", async () => {
    await theShop({ status: 204 });
    await ashaWasHereOnline();
    noNetwork();
    const store = makeQueryClient();
    render(
      <QueryClientProvider client={store}>
        <PinLogin onOffline={vi.fn()} />
      </QueryClientProvider>,
    );

    await ashaTypes("2581");
    await screen.findByText("PIN si sahihi.");

    expect(
      JSON.stringify(
        store
          .getMutationCache()
          .getAll()
          .map((change) => change.state.variables),
      ),
    ).not.toContain("2581");
  });
});
