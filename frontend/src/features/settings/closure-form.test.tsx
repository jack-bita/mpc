// closure-form.test.tsx — Ongeza (ATT-9): close the shop from a first day to a last. The funeral's five days go under
// the form's own id; Hadi left empty is one day; Kuanzia starts empty and offers no day before today; what the form
// can see is said at once, beside its box, and nothing is sent; the server's refusals show beside their boxes, and a
// clash with another closure above the buttons; a try sent again keeps its id, a changed one gets a new id (ADR-0007).
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { closure } from "@/test/closures";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { TODAY } from "@/test/settings";

import { ClosureForm } from "./closure-form";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const CLOSURES = "/api/v1/shops/closures/";

// A test that takes the network away puts it back after (navigator.onLine's spy).
afterEach(() => {
  vi.restoreAllMocks();
});

/** The form, opened on the shop's today of settings.ts, Sunday 15 Nov 2026. */
function openForm() {
  const onSaved = vi.fn();
  const onCancel = vi.fn();
  render(<ClosureForm today={TODAY} onSaved={onSaved} onCancel={onCancel} />);
  return { onSaved, onCancel };
}

/** What the app sent to add a closure, as the server would read it. */
async function sentBodies(): Promise<Record<string, unknown>[]> {
  return Promise.all(
    sent
      .filter((request) => request.method === "POST")
      .map((request) => request.json() as Promise<Record<string, unknown>>),
  );
}

/** The error beside a box: the one its aria-describedby names, after its hint (field.tsx). */
function errorOf(box: HTMLElement): string {
  const ids = box.getAttribute("aria-describedby")?.split(" ") ?? [];
  const error = ids.find((id) => id.endsWith("-error"));
  return error ? (document.getElementById(error)?.textContent ?? "") : "";
}

/** Types `text` into a box, in place of what was there. A date box takes the day as "2026-11-20". */
function typeInto(box: HTMLElement, text: string) {
  fireEvent.change(box, { target: { value: text } });
}

function tap(element: HTMLElement) {
  fireEvent.click(element);
}

const fromBox = () => screen.getByLabelText("Kuanzia");
const toBox = () => screen.getByLabelText("Hadi");
const nameBox = () => screen.getByLabelText("Jina");
const save = () => screen.getByRole("button", { name: "Hifadhi" });

/** The funeral of the card's example, typed in: 20 to 24 November, Msiba wa bibi. */
function typeTheFuneral() {
  typeInto(fromBox(), "2026-11-20");
  typeInto(toBox(), "2026-11-24");
  typeInto(nameBox(), "Msiba wa bibi");
}

describe("Ongeza", () => {
  it("sends the funeral's five days and its name under the form's own id (the card's second Done when)", async () => {
    const funeral = closure();
    answer("POST", CLOSURES, { status: 201, body: funeral });
    const { onSaved } = openForm();

    typeTheFuneral();
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(funeral));
    const [body] = await sentBodies();
    expect(body).toEqual({
      id: expect.stringMatching(/^[0-9a-f-]{36}$/),
      first_day: "2026-11-20",
      last_day: "2026-11-24",
      name: "Msiba wa bibi",
    });
  });

  it("sends one day when Hadi is left empty, so a public holiday needs one date", async () => {
    answer("POST", CLOSURES, {
      status: 201,
      body: closure({ first_day: "2026-12-09", last_day: "2026-12-09" }),
    });
    const { onSaved } = openForm();

    typeInto(fromBox(), "2026-12-09");
    typeInto(nameBox(), "  Siku ya Uhuru ");
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [body] = await sentBodies();
    // The spaces around the name off, as the server keeps it.
    expect(body).toMatchObject({
      first_day: "2026-12-09",
      last_day: "2026-12-09",
      name: "Siku ya Uhuru",
    });
  });

  it("starts Kuanzia and Hadi empty, offers no day before today, and starts the keyboard in Kuanzia", () => {
    openForm();

    expect(fromBox()).toHaveProperty("value", "");
    expect(toBox()).toHaveProperty("value", "");
    expect(fromBox().getAttribute("min")).toBe(TODAY);
    expect(toBox().getAttribute("min")).toBe(TODAY);
    expect(document.activeElement).toBe(fromBox());
  });

  it("offers Hadi nothing before Kuanzia's day once one is picked", () => {
    openForm();

    typeInto(fromBox(), "2026-11-20");

    expect(toBox().getAttribute("min")).toBe("2026-11-20");
  });

  it("says an empty Kuanzia and an empty name at once, beside their boxes, and sends nothing", async () => {
    openForm();

    typeInto(nameBox(), "   ");
    tap(save());

    expect(errorOf(fromBox())).toBe("Jaza sehemu hii.");
    expect(errorOf(nameBox())).toBe("Andika jina, kwa mfano Krismasi.");
    // Hadi waits for a first day to compare with: nothing beside it yet.
    expect(errorOf(toBox())).toBe("");
    expect(await sentBodies()).toEqual([]);
  });

  it("says a day before today, and a last day before the first, typed by hand, and sends nothing", async () => {
    openForm();

    typeInto(fromBox(), "2026-11-14");
    typeInto(toBox(), "2026-11-13");
    typeInto(nameBox(), "Msiba wa bibi");
    tap(save());

    expect(errorOf(fromBox())).toBe("Siku iliyoshapita haiwezi kubadilishwa.");
    expect(errorOf(toBox())).toBe(
      "Siku ya mwisho iko kabla ya siku ya kwanza.",
    );
    expect(await sentBodies()).toEqual([]);
  });

  it("shows the server's refusal beside its box, as the demo's of a closure from today", async () => {
    // On the demo a person's closure starts tomorrow or later, so every visitor today finds the shop as it is (ATT-8).
    answer(
      "POST",
      CLOSURES,
      refusal(
        400,
        "invalid",
        {},
        { first_day: ["demo.closures_from_tomorrow"] },
      ),
    );
    openForm();

    typeInto(fromBox(), TODAY);
    typeInto(nameBox(), "Msiba wa bibi");
    tap(save());

    await waitFor(() =>
      expect(errorOf(fromBox())).toBe(
        "Kwenye demo, ni siku za kuanzia kesho tu zinazoweza kufungwa au kufunguliwa, ili kila mgeni wa leo akute duka lilivyo.",
      ),
    );
    // Said beside its box only: no second alert repeats it in other words.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a clash with another closure above the buttons, as it is about the days together and no one box", async () => {
    // Krismasi already closes 25 and 26 December; a funeral from the 26th shares a day with it.
    answer("POST", CLOSURES, refusal(400, "closure.overlaps"));
    openForm();

    typeInto(fromBox(), "2026-12-26");
    typeInto(toBox(), "2026-12-28");
    typeInto(nameBox(), "Msiba wa bibi");
    tap(save());

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Duka tayari limefungwa katika moja ya siku hizi.",
    );
  });

  it("says a refusal of a field it has no box for in that field's own sentence", async () => {
    // A newer server, with a field this app doesn't know: the general "check the marked boxes" would send the owner
    // looking for a mark no box has (setting-form.tsx).
    answer(
      "POST",
      CLOSURES,
      refusal(400, "invalid", {}, { status: ["closure.status_unknown"] }),
    );
    openForm();

    typeTheFuneral();
    tap(save());

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Hali hii ya siku za kufunga duka haijulikani.",
    );
  });

  it("sends a try again under the same id, so a lost answer never makes a second closure", async () => {
    // The first send's answer is lost on the way back; the owner taps Hifadhi again.
    let tries = 0;
    answer("POST", CLOSURES, () => {
      tries += 1;
      if (tries === 1) throw new TypeError("Failed to fetch");
      return Response.json(closure(), { status: 201 });
    });
    const { onSaved } = openForm();

    typeTheFuneral();
    tap(save());
    await screen.findByRole("alert");
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [first, second] = await sentBodies();
    expect(second?.id).toBe(first?.id);
  });

  it("sends a changed last day under a new id, so the server never answers with the old closure", async () => {
    // The first send, 20 to 24 November, never reaches the server: the network drops on the way. The owner makes it end
    // on the 22nd and taps Hifadhi again. Had the first been saved, the old id would bring back the stored 24th, and the
    // page would say saved for the 22nd; under a new id it clashes with it instead, which closures-section.test.tsx
    // shows (ATT-9's review).
    let tries = 0;
    answer("POST", CLOSURES, () => {
      tries += 1;
      if (tries === 1) throw new TypeError("Failed to fetch");
      return Response.json(closure({ last_day: "2026-11-22" }), {
        status: 201,
      });
    });
    const { onSaved } = openForm();

    typeTheFuneral();
    tap(save());
    await screen.findByRole("alert");
    typeInto(toBox(), "2026-11-22");
    tap(save());

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [first, second] = await sentBodies();
    expect([first?.last_day, second?.last_day]).toEqual([
      "2026-11-24",
      "2026-11-22",
    ]);
    expect(second?.id).not.toBe(first?.id);
  });

  it("switches Hifadhi off while there is no network, so nothing waits unsent while it looks saved", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

    openForm();

    expect(save()).toHaveProperty("disabled", true);
    // Ghairi still closes it.
    expect(screen.getByRole("button", { name: "Ghairi" })).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("closes on Ghairi, with nothing sent", async () => {
    const { onCancel } = openForm();

    typeTheFuneral();
    tap(screen.getByRole("button", { name: "Ghairi" }));

    expect(onCancel).toHaveBeenCalled();
    expect(await sentBodies()).toEqual([]);
  });
});
