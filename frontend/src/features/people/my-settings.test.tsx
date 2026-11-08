// my-settings.test.tsx — Mipangilio yangu: a person sees their own language and font, and changes either
// with one tap; offline both wait for the network (UI-9, ADR-0039).
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DAWA, DAWA_LAPTOP_ANSWER, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";

import { MySettings } from "./my-settings";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const SETTINGS = "/api/auth/me/settings/";

// Neema, on her own phone, as she is saved now: Swahili, the default font.
const NEEMA = whoIsHere([{ side: DAWA, permissions: [] }]);

const radio = (name: string) => screen.getByRole("radio", { name });
const picked = (name: string) => radio(name).getAttribute("aria-checked");

/** What the screen sent to the settings route, each body as JSON. */
function changesSent(): Promise<unknown[]> {
  return Promise.all(
    sent
      .filter((request) => new URL(request.url).pathname === SETTINGS)
      .map((request) => request.clone().json()),
  );
}

/** The settings route answers as the server would: the person's two choices, with what was sent. */
function savesAsTheServerDoes() {
  answer("PATCH", SETTINGS, async (request) =>
    Response.json({
      language: NEEMA.user.language,
      font: NEEMA.user.font,
      ...((await request.json()) as object),
    }),
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Mipangilio yangu", () => {
  it("shows the person's own language and font", async () => {
    answer("GET", ME, { status: 200, body: NEEMA });

    render(<MySettings />);

    expect(
      await screen.findByRole("heading", { name: "Mipangilio yangu" }),
    ).toBeTruthy();
    expect(picked("Kiswahili")).toBe("true");
    expect(picked("English")).toBe("false");
    expect(picked("Herufi ya kawaida")).toBe("true");
    expect(picked("Herufi ya pili, rahisi kusoma")).toBe("false");
  });

  it("saves a tapped font at once, and sends only that one", async () => {
    // No Hifadhi button: the tap is the choice. The language is left out, so a tap in one tab never
    // sends back an old language from another.
    answer("GET", ME, { status: 200, body: NEEMA });
    savesAsTheServerDoes();
    render(<MySettings />);

    fireEvent.click(await screen.findByText("Herufi ya pili, rahisi kusoma"));

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe("Imehifadhiwa."),
    );
    expect(await changesSent()).toEqual([{ font: "second" }]);
    expect(picked("Herufi ya pili, rahisi kusoma")).toBe("true");
  });

  it("saves a tapped language the same way", async () => {
    answer("GET", ME, { status: 200, body: NEEMA });
    savesAsTheServerDoes();
    render(<MySettings />);

    fireEvent.click(await screen.findByText("English"));

    await waitFor(async () =>
      expect(await changesSent()).toEqual([{ language: "en" }]),
    );
  });

  it("keeps the saved answer, so every screen asking who is here sees the new choice", async () => {
    // The answer goes into the store's `me`, which the frame reads to follow the person (UI-9): no second
    // call to the server, and the choice shows as soon as it is saved.
    answer("GET", ME, { status: 200, body: NEEMA });
    savesAsTheServerDoes();
    render(<MySettings />);

    fireEvent.click(await screen.findByText("Herufi ya pili, rahisi kusoma"));

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe("Imehifadhiwa."),
    );
    const asked = sent.filter(
      (request) => new URL(request.url).pathname === ME,
    );
    expect(asked).toHaveLength(1);
  });

  it("shows the tap at once, while the server hears it", async () => {
    // The dot moves with the finger, not a moment later, and the status line says it is being saved.
    answer("GET", ME, { status: 200, body: NEEMA });
    answer("PATCH", SETTINGS, () => new Promise<Response>(() => undefined));
    render(<MySettings />);

    fireEvent.click(await screen.findByText("English"));

    await waitFor(() => expect(picked("English")).toBe("true"));
    expect(screen.getByRole("status").textContent).toBe("Inahifadhi…");
  });

  it("says why a change was refused, and shows what is still saved", async () => {
    // Suspended since the screen opened: the server refuses, the dot goes back, and she is told why.
    answer("GET", ME, { status: 200, body: NEEMA });
    answer("PATCH", SETTINGS, refusal(403, "staff.suspended"));
    render(<MySettings />);

    fireEvent.click(await screen.findByText("English"));

    expect(
      await screen.findByText("Umesimamishwa. Ongea na meneja au mmiliki."),
    ).toBeTruthy();
    expect(picked("Kiswahili")).toBe("true");
  });

  it("switches both off while there is no network", async () => {
    // Office screens need the internet: the office frame's banner says Inahitaji mtandao, and nothing
    // here can be tapped meanwhile, so no choice waits unsaved while it seems done.
    answer("GET", ME, { status: 200, body: NEEMA });
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

    render(<MySettings />);

    await screen.findByRole("heading", { name: "Mipangilio yangu" });
    for (const name of [
      "Kiswahili",
      "English",
      "Herufi ya kawaida",
      "Herufi ya pili, rahisi kusoma",
    ])
      expect(radio(name).hasAttribute("data-disabled")).toBe(true);
  });

  it("names each language in that language, and shows each font in itself", async () => {
    answer("GET", ME, { status: 200, body: NEEMA });

    render(<MySettings />);

    expect((await screen.findByText("English")).getAttribute("lang")).toBe(
      "en",
    );
    expect(screen.getByText("Herufi ya pili, rahisi kusoma").dataset.font).toBe(
      "second",
    );
  });

  it("goes back to the office's home page from a password's session", async () => {
    answer("GET", ME, { status: 200, body: NEEMA });

    render(<MySettings />);

    const back = await screen.findByRole("link", { name: "Rudi" });
    // The end slash comes from next.config.ts (trailingSlash), which a test doesn't read.
    expect(back.getAttribute("href")).toMatch(/^\/office\/?$/);
  });

  it("goes back to the PIN screen's welcome from a PIN's session at a device", async () => {
    // Asha came from the home page of the counter laptop, where she logged in by PIN.
    answer("GET", ME, {
      status: 200,
      body: {
        ...NEEMA,
        device: DAWA_LAPTOP_ANSWER.device,
        home_side: DAWA_LAPTOP_ANSWER.home_side,
      },
    });

    render(<MySettings />);

    const back = await screen.findByRole("link", { name: "Rudi" });
    expect(back.getAttribute("href")).toBe("/");
  });

  it("says to wait while it asks who is here, so the page is never blank", () => {
    answer("GET", ME, () => new Promise<Response>(() => undefined));

    render(<MySettings />);

    expect(screen.getByRole("status").textContent).toBe("Subiri kidogo…");
  });
});
