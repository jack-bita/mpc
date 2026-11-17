// closures-section.test.tsx — Siku duka limefungwa (ATT-9): the closures from today on, in the server's order,
// soonest first; a span written as its first and last day, one day as one date; a line when none is coming; the
// section in English; and why, when the server refuses the read. Then the buttons: Ongeza, Ondoa and Badilisha siku ya
// mwisho, for the owner, who holds settings.manage on the whole shop, and nobody else, Ondoa only beside a closure not
// yet begun; a closure saved shows in its place, one removed leaves the list, a moved one shows its new days, and the
// page says each.
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
// On the shop's today of the tests, Sunday 15 Nov 2026: a funeral that began on the 13th, and a closure that starts
// today.
const BEGUN = closure({ first_day: "2026-11-13", last_day: "2026-11-17" });
const STARTS_TODAY = closure({
  first_day: "2026-11-15",
  last_day: "2026-11-15",
  name: "Ukarabati wa duka",
});

/** Each closure's name and days, run together as the screen shows them, without its buttons' words. Given 5 s, not
 * Testing Library's 1, as the first test of a file pays for the page's first load (settings-screen.test.tsx). */
async function linesShown(): Promise<string[]> {
  const list = await screen.findByRole("list", {}, { timeout: 5_000 });
  return within(list)
    .getAllByRole("listitem")
    .map((item) => item.querySelector("p")?.textContent ?? "");
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
    // No Ongeza, and no Ondoa beside Siku ya Uhuru, which hasn't begun.
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
    // The first read, and the one Ongeza asks for as it opens (ATT-9's review).
    await waitFor(() => expect(reads()).toBe(2));
    tap(screen.getByRole("button", { name: "Ghairi" }));

    expect(screen.queryByLabelText("Kuanzia")).toBeNull();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Ongeza" }),
    );
    await waitFor(() => expect(reads()).toBe(3));
  });
  it("reads the list again when the days clash, so the closure they clash with shows (ATT-9's review)", async () => {
    // 20 to 24 November was saved, but its answer was lost, so the page doesn't show it. The owner changes Hadi to the
    // 22nd and taps Hifadhi again, under a new id: the server says the days clash, with his own funeral.
    let reads = 0;
    answer("GET", CLOSURES, () => {
      reads += 1;
      return Response.json(
        closuresAnswer(reads === 1 ? [UHURU] : [FUNERAL, UHURU]),
      );
    });
    answer("POST", CLOSURES, refusal(400, "closure.overlaps"));

    render(<ClosuresSection me={OWNER} />);

    tap(
      await screen.findByRole("button", { name: "Ongeza" }, { timeout: 5_000 }),
    );
    typeInto(screen.getByLabelText("Kuanzia"), "2026-11-20");
    typeInto(screen.getByLabelText("Hadi"), "2026-11-22");
    typeInto(screen.getByLabelText("Jina"), "Msiba wa bibi");
    tap(screen.getByRole("button", { name: "Hifadhi" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Duka tayari limefungwa katika moja ya siku hizi.",
    );
    await waitFor(async () =>
      expect(await linesShown()).toEqual([
        "Msiba wa bibi20/11/2026 – 24/11/2026",
        "Siku ya Uhuru09/12/2026",
      ]),
    );
  });
});

describe("Ondoa", () => {
  it("is beside each closure not yet begun, today's included, and not beside one begun (the card's third Done when)", async () => {
    answer("GET", CLOSURES, {
      status: 200,
      body: closuresAnswer([BEGUN, STARTS_TODAY, UHURU]),
    });

    render(<ClosuresSection me={OWNER} />);

    await linesShown();
    // Each names its closure, as a list of Ondoa buttons reads to a screen reader as nothing.
    expect(
      screen
        .getAllByRole("button", { name: /^Ondoa: / })
        .map((button) => button.getAttribute("aria-label")),
    ).toEqual(["Ondoa: Ukarabati wa duka", "Ondoa: Siku ya Uhuru"]);
  });

  it("takes the closure off the list once removed, says so, and gives the keyboard to the section's heading", async () => {
    let cancelled = false;
    answer("GET", CLOSURES, () =>
      Response.json(closuresAnswer(cancelled ? [KRISMASI] : [UHURU, KRISMASI])),
    );
    answer("POST", `${CLOSURES}${UHURU.id}/cancel/`, () => {
      cancelled = true;
      return Response.json({ ...UHURU, status: "cancelled" });
    });

    render(<ClosuresSection me={OWNER} />);

    tap(
      await screen.findByRole(
        "button",
        { name: "Ondoa: Siku ya Uhuru" },
        { timeout: 5_000 },
      ),
    );
    typeInto(screen.getByLabelText("Sababu"), "Tutafanya kazi siku hiyo");
    tap(screen.getByRole("button", { name: "Ondoa" }));

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "Imeondolewa: Siku ya Uhuru, 09/12/2026.",
      ),
    );
    await waitFor(async () =>
      expect(await linesShown()).toEqual(["Krismasi25/12/2026 – 26/12/2026"]),
    );
    // Its line and its button are gone: the keyboard goes to the nearest place still on the page.
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { level: 2, name: "Siku duka limefungwa" }),
    );
  });

  it("says it was already removed, in the server's sentence, and reads the list again, when the server says so (ATT-9's review)", async () => {
    // Another manager, or this owner's own tap whose answer was lost, cancelled it a moment before: it is removed
    // either way, but this owner's reason may not be the one kept, so the page doesn't say "Imeondolewa" as for its own.
    let reads = 0;
    answer("GET", CLOSURES, () => {
      reads += 1;
      return Response.json(closuresAnswer(reads === 1 ? [UHURU] : []));
    });
    answer(
      "POST",
      `${CLOSURES}${UHURU.id}/cancel/`,
      refusal(400, "closure.not_active"),
    );

    render(<ClosuresSection me={OWNER} />);

    tap(
      await screen.findByRole(
        "button",
        { name: "Ondoa: Siku ya Uhuru" },
        { timeout: 5_000 },
      ),
    );
    typeInto(screen.getByLabelText("Sababu"), "Tutafanya kazi siku hiyo");
    tap(screen.getByRole("button", { name: "Ondoa" }));

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "Siku hizi za kufunga duka zimeshaondolewa.",
      ),
    );
    expect(
      await screen.findByText("Hakuna siku zijazo ambazo duka limefungwa."),
    ).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("takes the closure off the page at once, even when the list can't be read again after (ATT-9's review)", async () => {
    // The network drops right after the cancel: the list's second read fails. The cancelled closure must not stay on
    // the page with its buttons.
    let reads = 0;
    answer("GET", CLOSURES, () => {
      reads += 1;
      return reads === 1
        ? Response.json(closuresAnswer([UHURU, KRISMASI]))
        : Response.json(refusal(403, "permission_denied").body, {
            status: 403,
          });
    });
    answer("POST", `${CLOSURES}${UHURU.id}/cancel/`, {
      status: 200,
      body: { ...UHURU, status: "cancelled" },
    });

    render(<ClosuresSection me={OWNER} />);

    tap(
      await screen.findByRole(
        "button",
        { name: "Ondoa: Siku ya Uhuru" },
        { timeout: 5_000 },
      ),
    );
    typeInto(screen.getByLabelText("Sababu"), "Tutafanya kazi siku hiyo");
    tap(screen.getByRole("button", { name: "Ondoa" }));

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "Imeondolewa: Siku ya Uhuru, 09/12/2026.",
      ),
    );
    expect(await linesShown()).toEqual(["Krismasi25/12/2026 – 26/12/2026"]);
    expect(
      screen.queryByRole("button", { name: "Ondoa: Siku ya Uhuru" }),
    ).toBeNull();
  });

  it("closes on Ghairi, and gives the keyboard back to the closure's Ondoa", async () => {
    answer("GET", CLOSURES, { status: 200, body: closuresAnswer([UHURU]) });

    render(<ClosuresSection me={OWNER} />);

    tap(
      await screen.findByRole(
        "button",
        { name: "Ondoa: Siku ya Uhuru" },
        { timeout: 5_000 },
      ),
    );
    tap(screen.getByRole("button", { name: "Ghairi" }));

    expect(screen.queryByLabelText("Sababu")).toBeNull();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Ondoa: Siku ya Uhuru" }),
    );
  });
});

describe("Badilisha siku ya mwisho", () => {
  /** Opens the form of a closure, found by its button's name. */
  async function openLastDayOf(name: string) {
    tap(
      await screen.findByRole(
        "button",
        { name: `Badilisha siku ya mwisho: ${name}` },
        { timeout: 5_000 },
      ),
    );
  }

  it("reads the list again when a later last day clashes, so the closure it clashes with shows (ATT-9's review)", async () => {
    // Another manager closed the 26th meanwhile; the owner moves the funeral's last day to the 27th.
    const added = closure({
      first_day: "2026-11-26",
      last_day: "2026-11-26",
      name: "Ukarabati wa duka",
    });
    let reads = 0;
    answer("GET", CLOSURES, () => {
      reads += 1;
      return Response.json(
        closuresAnswer(reads === 1 ? [FUNERAL] : [FUNERAL, added]),
      );
    });
    answer(
      "POST",
      `${CLOSURES}${FUNERAL.id}/last-day/`,
      refusal(400, "closure.overlaps"),
    );

    render(<ClosuresSection me={OWNER} />);

    await openLastDayOf("Msiba wa bibi");
    typeInto(screen.getByLabelText("Siku mpya ya mwisho"), "2026-11-27");
    typeInto(screen.getByLabelText("Sababu"), "Msiba umeongezeka");
    tap(screen.getByRole("button", { name: "Hifadhi" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Duka tayari limefungwa katika moja ya siku hizi.",
    );
    await waitFor(async () =>
      expect(await linesShown()).toEqual([
        "Msiba wa bibi20/11/2026 – 24/11/2026",
        "Ukarabati wa duka26/11/2026",
      ]),
    );
  });

  it("shows the moved days at once, even when the list can't be read again after (ATT-9's review)", async () => {
    const moved = { ...FUNERAL, last_day: "2026-11-22" };
    let reads = 0;
    answer("GET", CLOSURES, () => {
      reads += 1;
      return reads === 1
        ? Response.json(closuresAnswer([FUNERAL]))
        : Response.json(refusal(403, "permission_denied").body, {
            status: 403,
          });
    });
    answer("POST", `${CLOSURES}${FUNERAL.id}/last-day/`, {
      status: 200,
      body: moved,
    });

    render(<ClosuresSection me={OWNER} />);

    await openLastDayOf("Msiba wa bibi");
    typeInto(screen.getByLabelText("Siku mpya ya mwisho"), "2026-11-22");
    typeInto(screen.getByLabelText("Sababu"), "Familia imemaliza mapema");
    tap(screen.getByRole("button", { name: "Hifadhi" }));

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "Siku ya mwisho imebadilishwa: Msiba wa bibi, 20/11/2026 – 22/11/2026.",
      ),
    );
    expect(await linesShown()).toEqual([
      "Msiba wa bibi20/11/2026 – 22/11/2026",
    ]);
  });

  it("is beside every closure for the owner, begun or not", async () => {
    answer("GET", CLOSURES, {
      status: 200,
      body: closuresAnswer([BEGUN, STARTS_TODAY, UHURU]),
    });

    render(<ClosuresSection me={OWNER} />);

    await linesShown();
    expect(
      screen
        .getAllByRole("button", { name: /^Badilisha siku ya mwisho: / })
        .map((button) => button.getAttribute("aria-label")),
    ).toEqual([
      "Badilisha siku ya mwisho: Msiba wa bibi",
      "Badilisha siku ya mwisho: Ukarabati wa duka",
      "Badilisha siku ya mwisho: Siku ya Uhuru",
    ]);
  });

  it("shows the funeral's new days once moved, says so, and gives the keyboard back to its button (the card's fourth Done when)", async () => {
    const moved = { ...FUNERAL, last_day: "2026-11-22" };
    let saved = false;
    answer("GET", CLOSURES, () =>
      Response.json(closuresAnswer([saved ? moved : FUNERAL])),
    );
    answer("POST", `${CLOSURES}${FUNERAL.id}/last-day/`, () => {
      saved = true;
      return Response.json(moved);
    });

    render(<ClosuresSection me={OWNER} />);

    await openLastDayOf("Msiba wa bibi");
    // One form at a time: the line's buttons step aside while it is open.
    expect(screen.queryByRole("button", { name: /^Ondoa: / })).toBeNull();
    typeInto(screen.getByLabelText("Siku mpya ya mwisho"), "2026-11-22");
    typeInto(screen.getByLabelText("Sababu"), "Familia imemaliza mapema");
    tap(screen.getByRole("button", { name: "Hifadhi" }));

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "Siku ya mwisho imebadilishwa: Msiba wa bibi, 20/11/2026 – 22/11/2026.",
      ),
    );
    await waitFor(async () =>
      expect(await linesShown()).toEqual([
        "Msiba wa bibi20/11/2026 – 22/11/2026",
      ]),
    );
    expect(document.activeElement).toBe(
      screen.getByRole("button", {
        name: "Badilisha siku ya mwisho: Msiba wa bibi",
      }),
    );
  });

  it("takes a closure off the list once its last day moves to yesterday, and gives the keyboard to the heading", async () => {
    // The funeral that began on the 13th ended yesterday: the shop opens today, and the closure is over.
    const ended = { ...BEGUN, last_day: "2026-11-14" };
    let saved = false;
    answer("GET", CLOSURES, () =>
      Response.json(closuresAnswer(saved ? [UHURU] : [BEGUN, UHURU])),
    );
    answer("POST", `${CLOSURES}${BEGUN.id}/last-day/`, () => {
      saved = true;
      return Response.json(ended);
    });

    render(<ClosuresSection me={OWNER} />);

    await openLastDayOf("Msiba wa bibi");
    typeInto(screen.getByLabelText("Siku mpya ya mwisho"), "2026-11-14");
    typeInto(screen.getByLabelText("Sababu"), "Familia imemaliza jana");
    tap(screen.getByRole("button", { name: "Hifadhi" }));

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "Siku ya mwisho imebadilishwa: Msiba wa bibi, 13/11/2026 – 14/11/2026.",
      ),
    );
    await waitFor(async () =>
      expect(await linesShown()).toEqual(["Siku ya Uhuru09/12/2026"]),
    );
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { level: 2, name: "Siku duka limefungwa" }),
    );
  });

  it("says a closure someone else cancelled meanwhile is gone, and reads the list again", async () => {
    let reads = 0;
    answer("GET", CLOSURES, () => {
      reads += 1;
      return Response.json(closuresAnswer(reads === 1 ? [FUNERAL] : []));
    });
    answer(
      "POST",
      `${CLOSURES}${FUNERAL.id}/last-day/`,
      refusal(400, "closure.not_active"),
    );

    render(<ClosuresSection me={OWNER} />);

    await openLastDayOf("Msiba wa bibi");
    typeInto(screen.getByLabelText("Siku mpya ya mwisho"), "2026-11-22");
    typeInto(screen.getByLabelText("Sababu"), "Familia imemaliza mapema");
    tap(screen.getByRole("button", { name: "Hifadhi" }));

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "Siku hizi za kufunga duka zimeshaondolewa.",
      ),
    );
    expect(
      await screen.findByText("Hakuna siku zijazo ambazo duka limefungwa."),
    ).toBeTruthy();
  });

  it("closes on Ghairi, gives the keyboard back to its button, and asks for the list again", async () => {
    answer("GET", CLOSURES, { status: 200, body: closuresAnswer([UHURU]) });

    render(<ClosuresSection me={OWNER} />);

    await openLastDayOf("Siku ya Uhuru");
    // The first read, and the one the form asks for as it opens (ATT-9's review).
    await waitFor(() => expect(reads()).toBe(2));
    tap(screen.getByRole("button", { name: "Ghairi" }));

    expect(screen.queryByLabelText("Siku mpya ya mwisho")).toBeNull();
    expect(document.activeElement).toBe(
      screen.getByRole("button", {
        name: "Badilisha siku ya mwisho: Siku ya Uhuru",
      }),
    );
    await waitFor(() => expect(reads()).toBe(3));
  });
});

describe("a page left open", () => {
  it("reads the list again as a form opens, so a page left open overnight takes the shop's new today (ATT-9's review)", async () => {
    // The page was read on Sunday the 15th and left open; the owner taps Ongeza on Monday morning.
    let reads = 0;
    answer("GET", CLOSURES, () => {
      reads += 1;
      return Response.json(
        reads === 1
          ? closuresAnswer([UHURU])
          : { ...closuresAnswer([UHURU]), today: "2026-11-16" },
      );
    });

    render(<ClosuresSection me={OWNER} />);

    tap(
      await screen.findByRole("button", { name: "Ongeza" }, { timeout: 5_000 }),
    );

    await waitFor(() =>
      expect(screen.getByLabelText("Kuanzia").getAttribute("min")).toBe(
        "2026-11-16",
      ),
    );
  });

  it("says a closure is gone, and gives the keyboard to the heading, when a read finds it removed while its form is open (ATT-9's review)", async () => {
    // Another manager removed Siku ya Uhuru a moment before the owner tapped its Ondoa: the read the form asks for as
    // it opens no longer has it.
    let reads = 0;
    answer("GET", CLOSURES, () => {
      reads += 1;
      return Response.json(
        closuresAnswer(reads === 1 ? [UHURU, KRISMASI] : [KRISMASI]),
      );
    });

    render(<ClosuresSection me={OWNER} />);

    tap(
      await screen.findByRole(
        "button",
        { name: "Ondoa: Siku ya Uhuru" },
        { timeout: 5_000 },
      ),
    );

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "Siku ya Uhuru: siku hizi hazipo tena kwenye orodha.",
      ),
    );
    expect(screen.queryByLabelText("Sababu")).toBeNull();
    expect(await linesShown()).toEqual(["Krismasi25/12/2026 – 26/12/2026"]);
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { level: 2, name: "Siku duka limefungwa" }),
    );
  });
});
