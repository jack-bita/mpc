// closure-last-day.test.tsx — Badilisha siku ya mwisho (ATT-9): move a closure's last day, earlier or later, with a
// reason. The box starts at its last day now and offers nothing before the later of its first day and yesterday; the
// new day and the reason go to the closure's own route; what the form can see is said at once, beside its box, and
// nothing is sent; the server's refusals show beside their box, or above the buttons; and a closure someone else
// cancelled meanwhile is handed to the section.
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { closure } from "@/test/closures";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { TODAY } from "@/test/settings";

import { ClosureLastDay } from "./closure-last-day";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

// A test that takes the network away puts it back after (navigator.onLine's spy).
afterEach(() => {
  vi.restoreAllMocks();
});

// On the shop's today of the tests, Sunday 15 Nov 2026: the card's funeral, 20 to 24 November, not yet begun; and one
// that began on the 13th and runs to the 17th.
const FUNERAL = closure();
const BEGUN = closure({ first_day: "2026-11-13", last_day: "2026-11-17" });

/** The closure's own route for its last day. */
const routeOf = (one: components["schemas"]["Closure"]) =>
  `/api/v1/shops/closures/${one.id}/last-day/`;

/** The form, opened on a closure. */
function openOn(one = FUNERAL) {
  const onMoved = vi.fn();
  const onGone = vi.fn();
  const onCancel = vi.fn();
  render(
    <ClosureLastDay
      closure={one}
      today={TODAY}
      onMoved={onMoved}
      onGone={onGone}
      onCancel={onCancel}
    />,
  );
  return { onMoved, onGone, onCancel };
}

/** What the app sent, each as the server would read it. */
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

function typeInto(box: HTMLElement, text: string) {
  fireEvent.change(box, { target: { value: text } });
}

function tap(element: HTMLElement) {
  fireEvent.click(element);
}

const dayBox = () => screen.getByLabelText("Siku mpya ya mwisho");
const reasonBox = () => screen.getByLabelText("Sababu");
const save = () => screen.getByRole("button", { name: "Hifadhi" });

describe("Badilisha siku ya mwisho", () => {
  it("starts at the last day now, says it, and offers nothing before the first day", () => {
    openOn();

    expect(dayBox()).toHaveProperty("value", "2026-11-24");
    expect(dayBox().getAttribute("min")).toBe("2026-11-20");
    expect(
      screen.getByText("Sasa ni 24/11/2026. Inaweza kuwa mapema au baadaye."),
    ).toBeTruthy();
    expect(document.activeElement).toBe(dayBox());
  });

  it("offers nothing before yesterday for a closure already begun, as yesterday opens the shop from today", () => {
    openOn(BEGUN);

    expect(dayBox().getAttribute("min")).toBe("2026-11-14");
  });

  it("sends the funeral's new last day, the 22nd, with the reason (the card's fourth Done when)", async () => {
    // The family finished on the 22nd: the shop opens on the 23rd.
    const moved = { ...FUNERAL, last_day: "2026-11-22" };
    answer("POST", routeOf(FUNERAL), { status: 200, body: moved });
    const { onMoved } = openOn();

    typeInto(dayBox(), "2026-11-22");
    typeInto(reasonBox(), "Familia imemaliza mapema");
    tap(save());

    await waitFor(() => expect(onMoved).toHaveBeenCalledWith(moved));
    expect(await sentBodies()).toEqual([
      { last_day: "2026-11-22", reason: "Familia imemaliza mapema" },
    ]);
  });

  it("sends a later last day too, as a funeral can run longer", async () => {
    answer("POST", routeOf(FUNERAL), {
      status: 200,
      body: { ...FUNERAL, last_day: "2026-11-26" },
    });
    const { onMoved } = openOn();

    typeInto(dayBox(), "2026-11-26");
    typeInto(reasonBox(), "Msiba umeongezeka siku mbili");
    tap(save());

    await waitFor(() => expect(onMoved).toHaveBeenCalled());
    const [body] = await sentBodies();
    expect(body?.last_day).toBe("2026-11-26");
  });

  it("sends yesterday for a closure already begun, which opens the shop from today", async () => {
    answer("POST", routeOf(BEGUN), {
      status: 200,
      body: { ...BEGUN, last_day: "2026-11-14" },
    });
    const { onMoved } = openOn(BEGUN);

    typeInto(dayBox(), "2026-11-14");
    typeInto(reasonBox(), "Familia imemaliza jana");
    tap(save());

    await waitFor(() => expect(onMoved).toHaveBeenCalled());
  });

  it("says a day before the first and an empty reason at once, beside their boxes, and sends nothing", async () => {
    openOn();

    typeInto(dayBox(), "2026-11-19");
    typeInto(reasonBox(), "   ");
    tap(save());

    expect(errorOf(dayBox())).toBe(
      "Siku ya mwisho iko kabla ya siku ya kwanza.",
    );
    expect(errorOf(reasonBox())).toBe("Andika sababu.");
    expect(await sentBodies()).toEqual([]);
  });

  it("says a last day that would open a past day again, and an empty box, and sends nothing", async () => {
    // The 13th as the last day would open the 14th again, already past.
    openOn(BEGUN);

    typeInto(dayBox(), "2026-11-13");
    typeInto(reasonBox(), "Kosa");
    tap(save());
    expect(errorOf(dayBox())).toBe("Siku iliyoshapita haiwezi kubadilishwa.");

    typeInto(dayBox(), "");
    tap(save());
    expect(errorOf(dayBox())).toBe("Jaza sehemu hii.");
    expect(await sentBodies()).toEqual([]);
  });

  it("says the last day it already has beside its box, and sends nothing, as the server would change nothing (ATT-9's review)", async () => {
    // The owner types a reason and taps Hifadhi without picking a new day: the server would keep no reason, and the
    // page would have said the last day changed.
    const { onMoved } = openOn();

    typeInto(reasonBox(), "Familia imemaliza mapema");
    tap(save());

    expect(errorOf(dayBox())).toBe(
      "Hii tayari ndiyo siku ya mwisho. Chagua siku nyingine.",
    );
    expect(await sentBodies()).toEqual([]);
    expect(onMoved).not.toHaveBeenCalled();
  });

  it("shows the server's refusal of the day beside its box, as the demo's of a change of today", async () => {
    answer(
      "POST",
      routeOf(BEGUN),
      refusal(
        400,
        "invalid",
        {},
        { last_day: ["demo.closures_from_tomorrow"] },
      ),
    );
    openOn(BEGUN);

    typeInto(dayBox(), "2026-11-14");
    typeInto(reasonBox(), "Familia imemaliza jana");
    tap(save());

    await waitFor(() =>
      expect(errorOf(dayBox())).toBe(
        "Kwenye demo, ni siku za kuanzia kesho tu zinazoweza kufungwa au kufunguliwa, ili kila mgeni wa leo akute duka lilivyo.",
      ),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a clash with another closure above the buttons", async () => {
    // Moved later into Krismasi's days, the database's rule refuses it, of no one field.
    answer("POST", routeOf(FUNERAL), refusal(400, "closure.overlaps"));
    const { onMoved } = openOn();

    typeInto(dayBox(), "2026-12-26");
    typeInto(reasonBox(), "Msiba umeongezeka");
    tap(save());

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Duka tayari limefungwa katika moja ya siku hizi.",
    );
    expect(onMoved).not.toHaveBeenCalled();
  });

  it("says a clash above the buttons and a box's refusal beside it, both at once (ATT-9's review)", async () => {
    answer(
      "POST",
      routeOf(BEGUN),
      refusal(
        400,
        "closure.overlaps",
        {},
        { last_day: ["demo.closures_from_tomorrow"] },
      ),
    );
    openOn(BEGUN);

    typeInto(dayBox(), "2026-11-20");
    typeInto(reasonBox(), "Msiba umeongezeka");
    tap(save());

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Duka tayari limefungwa katika moja ya siku hizi.",
    );
    expect(errorOf(dayBox())).toBe(
      "Kwenye demo, ni siku za kuanzia kesho tu zinazoweza kufungwa au kufunguliwa, ili kila mgeni wa leo akute duka lilivyo.",
    );
  });

  it("hands a closure someone else cancelled meanwhile to the section, which says so", async () => {
    answer("POST", routeOf(FUNERAL), refusal(400, "closure.not_active"));
    const { onGone, onMoved } = openOn();

    typeInto(dayBox(), "2026-11-22");
    typeInto(reasonBox(), "Familia imemaliza mapema");
    tap(save());

    await waitFor(() => expect(onGone).toHaveBeenCalled());
    expect(onMoved).not.toHaveBeenCalled();
  });

  it("switches Hifadhi off while there is no network, so nothing waits unsent while it looks saved", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

    openOn();

    expect(save()).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "Ghairi" })).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("closes on Ghairi, with nothing sent", async () => {
    const { onCancel } = openOn();

    typeInto(dayBox(), "2026-11-22");
    tap(screen.getByRole("button", { name: "Ghairi" }));

    expect(onCancel).toHaveBeenCalled();
    expect(await sentBodies()).toEqual([]);
  });
});
