// my-settings.test.tsx — Mipangilio yangu: a person sees their own language and font, and changes either
// with one tap; offline both wait for the network (UI-9, ADR-0039).
import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import { OfficeFrame } from "@/features/office/office-frame";
import { WHO_IS_HERE, type WhoIsHere } from "@/features/people/who-is-here";
import { DAWA, DAWA_LAPTOP_ANSWER, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { swahiliIn } from "@/test/language";
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

  it("keeps a saved choice when a slower answer to who is here lands after it", async () => {
    // On 3G: Asha comes back to the tab, which asks who is here again, and the server reads her old row
    // for it. She taps the second font, which the server saves and answers first. The slower answer, with
    // her old font, must not undo it: the dot and the page would go back while the server holds "second".
    let reads = 0;
    let late: (answer: Response) => void = () => undefined;
    answer("GET", ME, () => {
      reads += 1;
      if (reads === 1) return Response.json(NEEMA);
      return new Promise<Response>((resolve) => {
        late = resolve;
      });
    });
    savesAsTheServerDoes();
    const store = makeQueryClient();
    render(
      <QueryClientProvider client={store}>
        <MySettings />
      </QueryClientProvider>,
    );
    await screen.findByText("Herufi ya pili, rahisi kusoma");
    void store.refetchQueries({ queryKey: WHO_IS_HERE });
    await waitFor(() => expect(reads).toBe(2));

    fireEvent.click(screen.getByText("Herufi ya pili, rahisi kusoma"));
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe("Imehifadhiwa."),
    );
    await act(async () => {
      late(Response.json(NEEMA));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(store.getQueryData<WhoIsHere>(WHO_IS_HERE)?.user.font).toBe(
      "second",
    );
    expect(picked("Herufi ya pili, rahisi kusoma")).toBe("true");
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

  it("changes the whole app at once, inside the office's frame", async () => {
    // The card's first case, on this side: she picks the second font, it is saved on her, and the page
    // follows with no reload. Another device shows it at her next login there, from `me`
    // (follow-the-person.test.tsx, and test_me_answers_the_persons_choices on the server).
    answer("GET", ME, { status: 200, body: NEEMA });
    savesAsTheServerDoes();
    render(
      <OfficeFrame>
        <MySettings />
      </OfficeFrame>,
    );

    fireEvent.click(await screen.findByText("Herufi ya pili, rahisi kusoma"));
    await waitFor(() =>
      expect(document.documentElement.dataset.font).toBe("second"),
    );

    fireEvent.click(screen.getByText("English"));
    expect(
      await screen.findByRole("heading", { name: "My settings" }),
    ).toBeTruthy();
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

  it("shows two quick taps at once, while both wait their turn", async () => {
    // Asha taps the second font, then English, on a slow network. The changes go one at a time, in order
    // (CHANGES_IN_ORDER): the second waits for the first. Both dots show what she tapped meanwhile, not
    // only the last one.
    const waiting: ((answer: Response) => void)[] = [];
    answer("GET", ME, { status: 200, body: NEEMA });
    answer(
      "PATCH",
      SETTINGS,
      (request) =>
        new Promise<Response>((resolve) => {
          void request
            .json()
            .then((change: object) =>
              waiting.push(() =>
                resolve(Response.json({ ...NEEMA.user, ...change })),
              ),
            );
        }),
    );
    render(<MySettings />);

    fireEvent.click(await screen.findByText("Herufi ya pili, rahisi kusoma"));
    fireEvent.click(screen.getByText("English"));

    await waitFor(() => expect(picked("English")).toBe("true"));
    expect(picked("Herufi ya pili, rahisi kusoma")).toBe("true");
    expect(screen.getByRole("status").textContent).toBe("Inahifadhi…");
  });

  it("never puts a late answer into the next person's record", async () => {
    // Neema taps, and before the answer lands the store's `me` is someone else's: the answer is hers, so
    // it must not change Juma's record (onSuccess checks whose it is).
    const juma: WhoIsHere = {
      ...NEEMA,
      user: { ...NEEMA.user, id: "019a5e00-0000-7000-8000-0000000000b2" },
    };
    let land: () => void = () => undefined;
    answer("GET", ME, { status: 200, body: NEEMA });
    answer(
      "PATCH",
      SETTINGS,
      () =>
        new Promise<Response>((resolve) => {
          land = () =>
            resolve(Response.json({ ...NEEMA.user, font: "second" }));
        }),
    );
    const store = makeQueryClient();
    render(
      <QueryClientProvider client={store}>
        <MySettings />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByText("Herufi ya pili, rahisi kusoma"));
    await waitFor(() =>
      expect(sent.some((r) => r.method === "PATCH")).toBe(true),
    );

    act(() => {
      store.setQueryData(WHO_IS_HERE, juma);
    });
    await act(async () => {
      land();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(store.getQueryData<WhoIsHere>(WHO_IS_HERE)?.user).toEqual(juma.user);
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

  it("speaks English to someone who reads it, with no Swahili left", async () => {
    // language.test.tsx opens every page in English, but there `me` never answers, so it sees only this
    // screen's waiting line: here the whole screen, inside the office's frame, which opens her language.
    answer("GET", ME, {
      status: 200,
      body: { ...NEEMA, user: { ...NEEMA.user, language: "en" } },
    });

    const { container } = render(
      <OfficeFrame>
        <MySettings />
      </OfficeFrame>,
    );

    expect(
      await screen.findByRole("heading", { name: "My settings" }),
    ).toBeTruthy();
    expect(screen.getByRole("radiogroup", { name: "Font" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Back" })).toBeTruthy();
    // One word the checker can't tell apart: "English", the row naming that language. The Swahili book has
    // the same word, as the bar button's label (language.switch), so the checker counts it. It is the row's,
    // marked as English on purpose, and the bar has no language button while she is logged in.
    expect(swahiliIn(container)).toEqual(["English"]);
    expect(screen.getByText("English").getAttribute("lang")).toBe("en");
  });

  it("says to wait while it asks who is here, so the page is never blank", () => {
    answer("GET", ME, () => new Promise<Response>(() => undefined));

    render(<MySettings />);

    expect(screen.getByRole("status").textContent).toBe("Subiri kidogo…");
  });
});
