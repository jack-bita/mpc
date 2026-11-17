// closures-section.test.tsx — Siku duka limefungwa (ATT-9): the closures from today on, in the server's order,
// soonest first; a span written as its first and last day, one day as one date; a line when none is coming; the
// section in English; and why, when the server refuses the read. Then Ongeza: for the owner, who holds
// settings.manage on the whole shop, and nobody else; a closure saved from it shows in its place, and the page says so.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { setLanguage } from "@/i18n/language";
import { closure, closuresAnswer } from "@/test/closures";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { OWNER } from "@/test/settings";

import { ClosuresSection } from "./closures-section";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const CLOSURES = "/api/v1/shops/closures/";

// A seller on each side: reading the closures needs no key.
const SELLER = whoIsHere([
  { side: DAWA, permissions: ["sale.create"] },
  { side: VYAKULA, permissions: ["sale.create"] },
]);

// The card's example: the funeral, then the demo's next two public holidays, as the server sends them, soonest first.
const FUNERAL = closure();
const UHURU = closure({
  first_day: "2026-12-09",
  last_day: "2026-12-09",
  name: "Siku ya Uhuru",
});
const KRISMASI = closure({
  first_day: "2026-12-25",
  last_day: "2026-12-26",
  name: "Krismasi",
});

/** Each closure's line, its words run together as the screen shows them. Given 5 s, not Testing Library's 1, as the
 * first test of a file pays for the page's first load (settings-screen.test.tsx). */
async function linesShown(): Promise<string[]> {
  const list = await screen.findByRole("list", {}, { timeout: 5_000 });
  return within(list)
    .getAllByRole("listitem")
    .map((item) => item.textContent ?? "");
}

function tap(element: HTMLElement) {
  fireEvent.click(element);
}

function typeInto(box: HTMLElement, text: string) {
  fireEvent.change(box, { target: { value: text } });
}

/** How many times the page asked for the list. */
function reads(): number {
  return sent.filter(
    (request) =>
      request.method === "GET" && new URL(request.url).pathname === CLOSURES,
  ).length;
}

describe("Siku duka limefungwa", () => {
  it("lists each closure from today on, in the server's order, soonest first, with its name and its days", async () => {
    answer("GET", CLOSURES, {
      status: 200,
      body: closuresAnswer([FUNERAL, UHURU, KRISMASI]),
    });

    render(<ClosuresSection me={SELLER} />);

    expect(await linesShown()).toEqual([
      "Msiba wa bibi20/11/2026 – 24/11/2026",
      // One day is one date, not "09/12/2026 – 09/12/2026".
      "Siku ya Uhuru09/12/2026",
      "Krismasi25/12/2026 – 26/12/2026",
    ]);
    expect(
      screen.getByRole("heading", { level: 2, name: "Siku duka limefungwa" }),
    ).toBeTruthy();
  });

  it("says so when no closure is coming, so an empty space never reads as a page still waiting", async () => {
    answer("GET", CLOSURES, { status: 200, body: closuresAnswer() });

    render(<ClosuresSection me={SELLER} />);

    expect(
      await screen.findByText("Hakuna siku zijazo ambazo duka limefungwa."),
    ).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("says why when the server refuses the read", async () => {
    // A refusal the store doesn't try again (query-client.ts), so its sentence shows at once; a server's own problem
    // is tried again first.
    answer("GET", CLOSURES, refusal(403, "permission_denied"));

    render(<ClosuresSection me={SELLER} />);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Huna ruhusa ya kufanya hili.",
    );
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("speaks English for someone who reads English", async () => {
    setLanguage("en");
    answer("GET", CLOSURES, { status: 200, body: closuresAnswer([KRISMASI]) });

    render(<ClosuresSection me={OWNER} />);

    // The name is the one the owner typed; the words around it are the book's.
    expect(await linesShown()).toEqual(["Krismasi25/12/2026 – 26/12/2026"]);
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "Days the shop is closed",
      }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add" })).toBeTruthy();
  });
});

describe("Ongeza", () => {
  it("is there for the owner, who holds settings.manage on the whole shop", async () => {
    answer("GET", CLOSURES, { status: 200, body: closuresAnswer([UHURU]) });

    render(<ClosuresSection me={OWNER} />);

    expect(
      await screen.findByRole("button", { name: "Ongeza" }, { timeout: 5_000 }),
    ).toBeTruthy();
  });

  it("isn't there for a seller, who sees the same list (the card's first Done when)", async () => {
    answer("GET", CLOSURES, { status: 200, body: closuresAnswer([UHURU]) });

    render(<ClosuresSection me={SELLER} />);

    expect(await linesShown()).toEqual(["Siku ya Uhuru09/12/2026"]);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("isn't there for a manager given settings.manage on Dawa alone, as a closure closes both sides", async () => {
    answer("GET", CLOSURES, { status: 200, body: closuresAnswer([UHURU]) });

    render(
      <ClosuresSection
        me={whoIsHere([{ side: DAWA, permissions: ["settings.manage"] }])}
      />,
    );

    expect(await linesShown()).toEqual(["Siku ya Uhuru09/12/2026"]);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows the funeral in its place once saved, says so, and gives the keyboard back to Ongeza", async () => {
    // The list before the save holds Siku ya Uhuru alone; after it, the funeral comes first, as it is sooner.
    let saved = false;
    answer("GET", CLOSURES, () =>
      Response.json(closuresAnswer(saved ? [FUNERAL, UHURU] : [UHURU])),
    );
    answer("POST", CLOSURES, () => {
      saved = true;
      return Response.json(FUNERAL, { status: 201 });
    });

    render(<ClosuresSection me={OWNER} />);

    tap(
      await screen.findByRole("button", { name: "Ongeza" }, { timeout: 5_000 }),
    );
    typeInto(screen.getByLabelText("Kuanzia"), "2026-11-20");
    typeInto(screen.getByLabelText("Hadi"), "2026-11-24");
    typeInto(screen.getByLabelText("Jina"), "Msiba wa bibi");
    tap(screen.getByRole("button", { name: "Hifadhi" }));

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "Imehifadhiwa: Msiba wa bibi, 20/11/2026 – 24/11/2026.",
      ),
    );
    await waitFor(async () =>
      expect(await linesShown()).toEqual([
        "Msiba wa bibi20/11/2026 – 24/11/2026",
        "Siku ya Uhuru09/12/2026",
      ]),
    );
    expect(screen.queryByLabelText("Kuanzia")).toBeNull();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Ongeza" }),
    );
  });

  it("closes on Ghairi, gives the keyboard back to Ongeza, and asks for the list again", async () => {
    // A send whose answer was lost may have saved the closure: the owner who gives up should still see it.
    answer("GET", CLOSURES, { status: 200, body: closuresAnswer([UHURU]) });

    render(<ClosuresSection me={OWNER} />);

    tap(
      await screen.findByRole("button", { name: "Ongeza" }, { timeout: 5_000 }),
    );
    const before = reads();
    tap(screen.getByRole("button", { name: "Ghairi" }));

    expect(screen.queryByLabelText("Kuanzia")).toBeNull();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Ongeza" }),
    );
    await waitFor(() => expect(reads()).toBe(before + 1));
  });
});
