// void-advance.test.tsx — Batilisha (WAGE-8): the sheet that crosses out an advance typed wrong. It names the amount, the
// worker, the day and what it was for; a reason goes to the advance's own route; an empty reason is said at once and
// nothing is sent; the server's refusals show beside the reason, or above the buttons; on the demo the reason is the ready
// one to tap; with no network the main button is held.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  advance,
  advanceRoute,
  AdvancesAsked,
  advancesAreAnswered,
} from "@/test/advances";
import { answer, refusal, sent } from "@/test/fake-server";
import { PayAsked, payIsAnswered } from "@/test/pay";
import { render } from "@/test/render";

import { VoidAdvance } from "./void-advance";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

// A test that takes the network away puts it back after (navigator.onLine's spy).
afterEach(() => {
  vi.restoreAllMocks();
});

const SLIP = advance({ date: "2026-11-16", amount: "300000.00" });
const VOID = `${advanceRoute(SLIP.id)}void/`;
const CROSSED = {
  ...SLIP,
  voided: {
    by: "Baba",
    at: "2026-11-16T16:00:00Z",
    reason: "Sifuri moja zaidi",
  },
};

function openOn(line = SLIP, readyReasons: "wrong_amount"[] = []) {
  const onDone = vi.fn();
  const onClose = vi.fn();
  render(
    <VoidAdvance
      advance={line}
      readyReasons={readyReasons}
      onDone={onDone}
      onClose={onClose}
      finalFocus={() => null}
    />,
  );
  return { onDone, onClose };
}

async function sentBodies(): Promise<Record<string, unknown>[]> {
  return Promise.all(
    sent
      .filter((request) => request.method === "POST")
      .map((request) => request.json() as Promise<Record<string, unknown>>),
  );
}

/** The error beside a box: the one its aria-describedby names (field.tsx, choice.tsx). */
function errorOf(element: HTMLElement): string {
  const ids = element.getAttribute("aria-describedby")?.split(" ") ?? [];
  const error = ids.find((id) => id.endsWith("-error"));
  return error ? (document.getElementById(error)?.textContent ?? "") : "";
}

const sheet = () =>
  screen.getByRole("dialog", { name: /^Batilisha TSh\s300,000$/ });
const reasonBox = () => within(sheet()).getByLabelText("Sababu");
const crossOut = () =>
  within(sheet()).getByRole("button", { name: "Batilisha" });

describe("Batilisha, of an advance", () => {
  it("names the amount, the worker, the day and what it was for", () => {
    openOn();

    expect(sheet().textContent).toContain(
      "Juma · Jumatatu 16/11/2026 · Ada ya shule",
    );
  });

  it("names the worker and the day alone when nothing says what it was for", () => {
    openOn({ ...SLIP, note: "" });

    expect(sheet().textContent).toContain("Juma · Jumatatu 16/11/2026");
    expect(sheet().textContent).not.toContain("2026 ·");
  });

  it("sends the reason to the advance's own route, then is done", async () => {
    answer("POST", VOID, { status: 200, body: CROSSED });
    const { onDone } = openOn();

    fireEvent.change(reasonBox(), { target: { value: "Sifuri moja zaidi" } });
    fireEvent.click(crossOut());

    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
    expect(await sentBodies()).toEqual([{ reason: "Sifuri moja zaidi" }]);
  });

  it.each([
    ["crossed out", { status: 200, body: CROSSED }],
    // The server crossed it out, and its answer was lost: the page behind the sheet must not go on counting it.
    ["no answer", refusal(503, "server_error")],
  ])("asks the advances and the pay again: %s", async (_how, reply) => {
    answer("POST", VOID, reply);
    const asked = advancesAreAnswered();
    const payAsked = payIsAnswered();
    render(
      <>
        <AdvancesAsked />
        <PayAsked />
        <VoidAdvance
          advance={SLIP}
          readyReasons={[]}
          onDone={vi.fn()}
          onClose={vi.fn()}
          finalFocus={() => null}
        />
      </>,
    );
    await waitFor(() => expect([asked(), payAsked()]).toEqual([1, [1, 1]]));

    fireEvent.change(reasonBox(), { target: { value: "Sifuri moja zaidi" } });
    fireEvent.click(crossOut());

    await waitFor(() => expect([asked(), payAsked()]).toEqual([2, [2, 2]]));
  });

  it("says an empty reason at once, and sends nothing", async () => {
    openOn();

    fireEvent.change(reasonBox(), { target: { value: "   " } });
    fireEvent.click(crossOut());

    await waitFor(() => expect(errorOf(reasonBox())).toBe("Andika sababu."));
    expect(sent).toEqual([]);
  });

  it("shows the server's refusal beside the reason, and one of the whole request above the buttons", async () => {
    answer(
      "POST",
      VOID,
      refusal(400, "invalid", {}, { reason: ["demo.ready_reasons"] }),
    );
    const { onDone } = openOn();
    fireEvent.change(reasonBox(), { target: { value: "Sifuri moja zaidi" } });
    fireEvent.click(crossOut());
    await waitFor(() => expect(errorOf(reasonBox())).not.toBe(""));

    answer("POST", VOID, refusal(400, "advance.own"));
    fireEvent.click(crossOut());
    expect((await within(sheet()).findByRole("alert")).textContent).toContain(
      "Huwezi kuandika wala kubatilisha advansi yako mwenyewe.",
    );
    expect(onDone).not.toHaveBeenCalled();
  });

  it("shows only what the last try found, never the one before's refusal", async () => {
    answer("POST", VOID, refusal(403, "permission_denied"));
    openOn();
    fireEvent.change(reasonBox(), { target: { value: "Sifuri moja zaidi" } });
    fireEvent.click(crossOut());
    await within(sheet()).findByRole("alert");

    fireEvent.change(reasonBox(), { target: { value: "" } });
    fireEvent.click(crossOut());

    await waitFor(() => expect(errorOf(reasonBox())).toBe("Andika sababu."));
    expect(within(sheet()).queryByRole("alert")).toBeNull();
  });

  it("offers the ready reason on the demo, and sends its code", async () => {
    answer("POST", VOID, { status: 200, body: CROSSED });
    openOn(SLIP, ["wrong_amount"]);
    expect(screen.queryByRole("textbox")).toBeNull();

    fireEvent.click(crossOut());
    expect(await within(sheet()).findByText("Andika sababu.")).toBeTruthy();
    fireEvent.click(
      within(sheet()).getByRole("radio", { name: "Kiasi kimekosewa" }),
    );
    fireEvent.click(crossOut());

    await waitFor(async () =>
      expect(await sentBodies()).toEqual([{ reason: "wrong_amount" }]),
    );
  });

  it("closes on Ghairi with nothing sent", () => {
    const { onClose } = openOn();

    fireEvent.click(within(sheet()).getByRole("button", { name: "Ghairi" }));

    expect(onClose).toHaveBeenCalledOnce();
    expect(sent).toEqual([]);
  });

  it("holds the main button with no network, so nothing waits unsent", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    openOn();

    expect((crossOut() as HTMLButtonElement).disabled).toBe(true);
  });
});
