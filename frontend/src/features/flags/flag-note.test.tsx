// flag-note.test.tsx — Eleza, Imetatuliwa and Si tatizo, each a note in a sheet over the flag's page (CTRL-4): what each
// sends, what the page shows after, and every way it can be refused. Fake people and words.
import { QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import type { components } from "@/api/schema";
import { answer, refusal, sent } from "@/test/fake-server";
import { flag, flagNote, flagRoute, REVIEWER } from "@/test/flags";
import { render } from "@/test/render";

import { FlagScreen } from "./flag-page";
import { FLAGS } from "./flags";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

// A test that takes the network away puts it back after: navigator.onLine's spy, and the store's own note of it, which
// hears the window's events.
afterEach(() => {
  vi.restoreAllMocks();
  fireEvent(window, new Event("online"));
});

const ME = "/api/auth/me/";
const WORDS = "Nimezungumza naye.";

type Flag = components["schemas"]["Flag"];

/** The page of `one`; each action answers with the flag moved by a note of its own. */
function show(one: Flag = flag()) {
  let now = one;
  answer("GET", ME, { status: 200, body: REVIEWER });
  answer("GET", flagRoute(one.id), () => Response.json(now));
  for (const [route, status] of [
    ["explain", "explained"],
    ["resolve", "resolved"],
    ["dismiss", "dismissed"],
  ] as const)
    answer("POST", `${flagRoute(one.id)}${route}/`, async (request) => {
      const { id, text } = (await request.json()) as Record<string, string>;
      now = {
        ...now,
        status,
        notes: [...now.notes, flagNote({ id, step: status, text })],
      };
      return Response.json(now);
    });
  return {
    one,
    /** Someone else closes it, on another phone. */
    closeElsewhere: () => {
      now = { ...now, status: "dismissed" };
    },
  };
}

const button = (name: string) => screen.findByRole("button", { name });

async function openSheet(name: string): Promise<HTMLElement> {
  fireEvent.click(await button(name));
  return screen.findByRole("dialog");
}

function type(sheet: HTMLElement, words: string) {
  fireEvent.change(within(sheet).getByLabelText("Maelezo"), {
    target: { value: words },
  });
}

const save = (sheet: HTMLElement) =>
  within(sheet).getByRole("button", {
    name: /^(Hifadhi maelezo|Funga tofauti)$/,
  });

/** The notes the app sent: where each went, and what it held. */
async function notesSent(): Promise<
  { to: string; body: Record<string, string> }[]
> {
  return Promise.all(
    sent
      .filter((request) => request.method === "POST")
      .map(async (request) => ({
        to: new URL(request.url).pathname,
        body: (await request.clone().json()) as Record<string, string>,
      })),
  );
}

describe("the three buttons", () => {
  it.each([
    [
      "Eleza",
      "explain",
      "Eleza tofauti hii",
      "Maelezo yamehifadhiwa.",
      "Imeelezwa",
    ],
    [
      "Imetatuliwa",
      "resolve",
      "Imetatuliwa",
      "Tofauti imefungwa: imetatuliwa.",
      "Imetatuliwa",
    ],
    [
      "Si tatizo",
      "dismiss",
      "Si tatizo",
      "Tofauti imefungwa: si tatizo.",
      "Si tatizo",
    ],
  ])(
    "%s sends its note to its own route, and the page shows the flag as it now is",
    async (name, route, title, doneLine, status) => {
      const { one } = show();
      render(<FlagScreen id={one.id} />);
      const sheet = await openSheet(name);
      expect(within(sheet).getByRole("heading", { name: title })).toBeTruthy();

      type(sheet, WORDS);
      fireEvent.click(save(sheet));

      const line = await screen.findByText(doneLine);
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
      const [note] = await notesSent();
      expect(note?.to).toBe(`${flagRoute(one.id)}${route}/`);
      expect(note?.body.text).toBe(WORDS);
      // A UUIDv7, made on the phone (ADR-0007).
      expect(note?.body.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7/);
      const notes = screen.getByRole("region", { name: "Maelezo (1)" });
      expect(within(notes).getByText(WORDS)).toBeTruthy();
      expect(screen.getByText("Hali").nextElementSibling?.textContent).toBe(
        status,
      );
      // The keyboard on the line that says what it did: after a close, the buttons are gone.
      await waitFor(() =>
        expect(document.activeElement).toBe(line.closest('[tabindex="-1"]')),
      );
    },
  );

  it("goes on offering all three after an explanation, and none after a close", async () => {
    const { one } = show();
    render(<FlagScreen id={one.id} />);
    const explain = await openSheet("Eleza");
    type(explain, WORDS);
    fireEvent.click(save(explain));
    await screen.findByText("Maelezo yamehifadhiwa.");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const dismiss = await openSheet("Si tatizo");
    // A new sheet's line: the last one's is gone.
    expect(screen.queryByText("Maelezo yamehifadhiwa.")).toBeNull();
    type(dismiss, "Alikuja kuchukua vitu vyake.");
    fireEvent.click(save(dismiss));

    await screen.findByText("Tofauti imefungwa: si tatizo.");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    for (const name of ["Eleza", "Imetatuliwa", "Si tatizo"])
      expect(screen.queryByRole("button", { name })).toBeNull();
    expect(screen.getByRole("region", { name: "Maelezo (2)" })).toBeTruthy();
    // Two notes, each its own id.
    const [first, second] = await notesSent();
    expect(first?.body.id).not.toBe(second?.body.id);
  });

  it("offers Eleza alone to the one it names, and says who closes it", async () => {
    const { one } = show(flag({ names_you: true }));
    render(<FlagScreen id={one.id} />);

    expect(await button("Eleza")).toBeTruthy();
    for (const name of ["Imetatuliwa", "Si tatizo"])
      expect(screen.queryByRole("button", { name })).toBeNull();
    expect(
      screen.getByText(
        "Tofauti hii inakutaja, kwa hiyo mtu mwingine ndiye anayeifunga.",
      ),
    ).toBeTruthy();
  });

  it.each(["resolved", "dismissed"] as const)(
    "offers nothing on one that is %s, even to the one it names",
    async (status) => {
      const { one } = show(flag({ status, names_you: true }));
      render(<FlagScreen id={one.id} />);

      await screen.findByText("Hali");
      expect(screen.queryByRole("button", { name: "Eleza" })).toBeNull();
      expect(screen.queryByText(/^Tofauti hii inakutaja/)).toBeNull();
    },
  );

  it("marks the lists to be read again, as the flag may have moved between them", async () => {
    const { one } = show();
    const store = makeQueryClient();
    const list = [...FLAGS, "list", "waiting", null, null];
    store.setQueryData(list, { pages: [], pageParams: [] });
    render(
      <QueryClientProvider client={store}>
        <FlagScreen id={one.id} />
      </QueryClientProvider>,
    );
    const sheet = await openSheet("Imetatuliwa");
    type(sheet, WORDS);
    fireEvent.click(save(sheet));

    await screen.findByText("Tofauti imefungwa: imetatuliwa.");
    expect(store.getQueryState(list)?.isInvalidated).toBe(true);
  });
});

describe("the sheet", () => {
  it("says before a close that it is for good", async () => {
    const { one } = show();
    render(<FlagScreen id={one.id} />);

    for (const name of ["Imetatuliwa", "Si tatizo"]) {
      const sheet = await openSheet(name);
      expect(within(sheet).getByText(/haifunguliwi tena/)).toBeTruthy();
      fireEvent.click(within(sheet).getByRole("button", { name: "Ghairi" }));
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    }
    const explain = await openSheet("Eleza");
    expect(within(explain).getByText(/itaendelea kusubiri/)).toBeTruthy();
  });

  it("asks for words, and sends nothing without them", async () => {
    const { one } = show();
    render(<FlagScreen id={one.id} />);
    const sheet = await openSheet("Imetatuliwa");

    type(sheet, "   ");
    fireEvent.click(save(sheet));

    expect(within(sheet).getByText("Andika maelezo.")).toBeTruthy();
    expect(await notesSent()).toEqual([]);
  });

  it("sends the same id again after a lost answer, so one note is written", async () => {
    const { one } = show();
    const dropped = `${flagRoute(one.id)}resolve/`;
    answer("POST", dropped, () => {
      throw new TypeError("the network dropped");
    });
    render(<FlagScreen id={one.id} />);
    const sheet = await openSheet("Imetatuliwa");
    type(sheet, WORDS);
    fireEvent.click(save(sheet));
    await within(sheet).findByRole("alert");
    // The words are still there to send again.
    expect(
      within(sheet).getByLabelText<HTMLInputElement>("Maelezo").value,
    ).toBe(WORDS);

    fireEvent.click(save(sheet));
    await waitFor(async () => expect(await notesSent()).toHaveLength(2));
    const [first, second] = await notesSent();
    expect(second?.body).toEqual(first?.body);
  });

  it("never lets an older read put a closed flag back", async () => {
    // The first send is lost, so the page asks for the flag again; the answer is slow. The second send closes the flag.
    // Then the older answer lands, from before the close: the page goes on showing the closed flag.
    const { one } = show();
    const closing = `${flagRoute(one.id)}resolve/`;
    answer("POST", closing, () => {
      throw new TypeError("the network dropped");
    });
    render(<FlagScreen id={one.id} />);
    const sheet = await openSheet("Imetatuliwa");
    type(sheet, WORDS);
    let landLate: (older: Response) => void = () => {};
    answer(
      "GET",
      flagRoute(one.id),
      () =>
        new Promise<Response>((resolve) => {
          landLate = resolve;
        }),
    );
    fireEvent.click(save(sheet));
    await within(sheet).findByRole("alert");
    const closed = { ...one, status: "resolved" as const };
    answer("POST", closing, { status: 200, body: closed });
    const late = landLate;
    // Every read from here on answers the flag as it now is.
    answer("GET", flagRoute(one.id), { status: 200, body: closed });

    fireEvent.click(save(sheet));
    await screen.findByText("Tofauti imefungwa: imetatuliwa.");
    await act(async () => {
      late(Response.json(one));
      await new Promise((resolve) => setTimeout(resolve, 20));
    });

    expect(screen.getByText("Hali").nextElementSibling?.textContent).toBe(
      "Imetatuliwa",
    );
    expect(screen.queryByRole("button", { name: "Si tatizo" })).toBeNull();
  });

  it("forgets what was typed on Ghairi, and gives the keyboard back to its button", async () => {
    const { one } = show();
    render(<FlagScreen id={one.id} />);
    const sheet = await openSheet("Si tatizo");
    type(sheet, WORDS);

    fireEvent.click(within(sheet).getByRole("button", { name: "Ghairi" }));

    const opener = await button("Si tatizo");
    await waitFor(() => expect(document.activeElement).toBe(opener));
    const again = await openSheet("Si tatizo");
    expect(
      within(again).getByLabelText<HTMLInputElement>("Maelezo").value,
    ).toBe("");
    expect(await notesSent()).toEqual([]);
  });

  it("says someone closed it meanwhile, and leaves a page with no buttons", async () => {
    const { one, closeElsewhere } = show();
    render(<FlagScreen id={one.id} />);
    const sheet = await openSheet("Imetatuliwa");
    type(sheet, WORDS);
    closeElsewhere();
    answer("POST", `${flagRoute(one.id)}resolve/`, refusal(400, "flag.closed"));

    fireEvent.click(save(sheet));

    expect(
      await within(sheet).findByText("Tofauti hii imeshafungwa."),
    ).toBeTruthy();
    // The page behind reads the flag as it now is.
    await waitFor(() =>
      expect(screen.getByText("Hali").nextElementSibling?.textContent).toBe(
        "Si tatizo",
      ),
    );
    fireEvent.click(within(sheet).getByRole("button", { name: "Ghairi" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.queryByRole("button", { name: "Imetatuliwa" })).toBeNull();
    const line = screen.getByText("Tofauti hii imeshafungwa.");
    await waitFor(() =>
      expect(document.activeElement).toBe(line.closest('[tabindex="-1"]')),
    );
  });

  it("shows the server's refusal of the words beside their box, and any other above the buttons", async () => {
    const { one } = show();
    const route = `${flagRoute(one.id)}explain/`;
    answer(
      "POST",
      route,
      refusal(400, "invalid", {}, { text: ["flag.note_required"] }),
    );
    render(<FlagScreen id={one.id} />);
    const sheet = await openSheet("Eleza");
    type(sheet, WORDS);
    fireEvent.click(save(sheet));
    expect(await within(sheet).findByText("Andika maelezo.")).toBeTruthy();
    expect(within(sheet).queryByRole("alert")).toBeNull();

    // A field this sheet has no box for is about the whole note: above, never nowhere.
    answer("POST", route, refusal(400, "invalid", {}, { id: ["id.taken"] }));
    fireEvent.click(save(sheet));
    expect(await within(sheet).findByRole("alert")).toBeTruthy();
    expect(within(sheet).queryByText("Andika maelezo.")).toBeNull();
  });

  it("holds its main button with no network, and keeps Ghairi free", async () => {
    const { one } = show();
    render(<FlagScreen id={one.id} />);
    const sheet = await openSheet("Eleza");
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    fireEvent(window, new Event("offline"));

    await waitFor(() =>
      expect(save(sheet).hasAttribute("disabled")).toBe(true),
    );
    expect(
      within(sheet)
        .getByRole("button", { name: "Ghairi" })
        .hasAttribute("disabled"),
    ).toBe(false);
  });

  it("offers ready words on the demo, sends their code, and shows them in words", async () => {
    const { one } = show(
      flag({ ready_notes: ["asked_them", "checked_laptop", "honest_mistake"] }),
    );
    render(<FlagScreen id={one.id} />);
    const sheet = await openSheet("Si tatizo");
    expect(within(sheet).queryByRole("textbox")).toBeNull();
    fireEvent.click(save(sheet));
    expect(within(sheet).getByText("Andika maelezo.")).toBeTruthy();

    fireEvent.click(
      within(sheet).getByRole("radio", {
        name: "Walikosea, si kwa makusudi.",
      }),
    );
    fireEvent.click(save(sheet));

    const notes = await screen.findByRole("region", { name: "Maelezo (1)" });
    expect(within(notes).getByText("Walikosea, si kwa makusudi.")).toBeTruthy();
    expect((await notesSent()).at(-1)?.body.text).toBe("honest_mistake");
  });
});
