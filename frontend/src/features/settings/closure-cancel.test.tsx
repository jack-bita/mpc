// closure-cancel.test.tsx — Ondoa (ATT-9): take a closure off before its first day, with a reason. The question says
// which closure and what happens; the reason goes to the closure's own cancel route; an empty one is said at once and
// nothing is sent; a cancel sent again, whose first answer was lost, is read as done (closure.not_active, ATT-8's
// review); the server's other refusals show above the buttons.
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { closure } from "@/test/closures";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";

import { ClosureCancel } from "./closure-cancel";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

// A test that takes the network away puts it back after (navigator.onLine's spy).
afterEach(() => {
  vi.restoreAllMocks();
});

const KRISMASI = closure({
  first_day: "2026-12-25",
  last_day: "2026-12-26",
  name: "Krismasi",
});
const CANCEL = `/api/v1/shops/closures/${KRISMASI.id}/cancel/`;

/** The form, opened on Krismasi. */
function openOn() {
  const onCancelled = vi.fn();
  const onCancel = vi.fn();
  render(
    <ClosureCancel
      closure={KRISMASI}
      onCancelled={onCancelled}
      onCancel={onCancel}
    />,
  );
  return { onCancelled, onCancel };
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

const reasonBox = () => screen.getByLabelText("Sababu");
// The form's answer: its name is its word, and its question is its description (aria-describedby).
const ondoa = () => screen.getByRole("button", { name: "Ondoa" });

describe("Ondoa", () => {
  it("asks which closure, and says the shop opens on its days, before the owner presses it", () => {
    openOn();

    expect(
      screen.getByText(
        "Ondoa Krismasi, 25/12/2026 – 26/12/2026? Duka litakuwa wazi siku hizo.",
      ),
    ).toBeTruthy();
    // Its answer names the question, so a screen reader says what it removes (side-switch.tsx).
    expect(ondoa().getAttribute("aria-describedby")).toBe(
      screen.getByText(/^Ondoa Krismasi/).id,
    );
    expect(document.activeElement).toBe(reasonBox());
  });

  it("sends the reason to the closure's own cancel route (the card's third Done when)", async () => {
    answer("POST", CANCEL, {
      status: 200,
      body: { ...KRISMASI, status: "cancelled" },
    });
    const { onCancelled } = openOn();

    typeInto(reasonBox(), "Tutafungua siku ya Krismasi");
    tap(ondoa());

    await waitFor(() => expect(onCancelled).toHaveBeenCalled());
    expect(await sentBodies()).toEqual([
      { reason: "Tutafungua siku ya Krismasi" },
    ]);
  });

  it("says an empty reason at once, beside its box, and sends nothing", async () => {
    // Spaces alone are no reason, as the server says too (rule 7: who, when and why).
    openOn();

    typeInto(reasonBox(), "   ");
    tap(ondoa());

    expect(errorOf(reasonBox())).toBe("Andika sababu.");
    expect(await sentBodies()).toEqual([]);
  });

  it("reads a cancel sent again, whose first answer was lost, as done (ATT-8's review)", async () => {
    // The first cancel reached the server, but its answer was lost on the way back. The owner taps Ondoa again: the
    // closure is already cancelled, and the server says so.
    let tries = 0;
    answer("POST", CANCEL, () => {
      tries += 1;
      if (tries === 1) throw new TypeError("Failed to fetch");
      return Response.json(refusal(400, "closure.not_active").body, {
        status: 400,
      });
    });
    const { onCancelled } = openOn();

    typeInto(reasonBox(), "Tutafungua siku ya Krismasi");
    tap(ondoa());
    await screen.findByRole("alert");
    tap(ondoa());

    await waitFor(() => expect(onCancelled).toHaveBeenCalled());
    // Done, not refused: no sentence says it failed.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a closure already begun above the buttons, as no box is wrong", async () => {
    // Its first day came while the page was open: that day stays closed, and only the last day can move.
    answer("POST", CANCEL, refusal(400, "closure.started"));
    const { onCancelled } = openOn();

    typeInto(reasonBox(), "Tutafungua");
    tap(ondoa());

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Siku hizi zimeshaanza. Badilisha siku ya mwisho badala yake.",
    );
    expect(onCancelled).not.toHaveBeenCalled();
  });

  it("shows the server's refusal of the reason beside its box", async () => {
    answer(
      "POST",
      CANCEL,
      refusal(400, "invalid", {}, { reason: ["closure.reason_required"] }),
    );
    openOn();

    typeInto(reasonBox(), "Tutafungua");
    tap(ondoa());

    await waitFor(() => expect(errorOf(reasonBox())).toBe("Andika sababu."));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("switches Ondoa off while there is no network, so nothing waits unsent while it looks done", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

    openOn();

    expect(ondoa()).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "Ghairi" })).toHaveProperty(
      "disabled",
      false,
    );
  });

  it("closes on Ghairi, with nothing sent", async () => {
    const { onCancel } = openOn();

    typeInto(reasonBox(), "Tutafungua");
    tap(screen.getByRole("button", { name: "Ghairi" }));

    expect(onCancel).toHaveBeenCalled();
    expect(await sentBodies()).toEqual([]);
  });
});
