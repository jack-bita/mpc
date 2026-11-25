// void-meal-money.test.tsx — Batilisha (WAGE-7): the sheet that crosses out meal money typed wrong. It names the amount,
// the day and what it bought; a reason goes to the row's own route; an empty reason is said at once and nothing is sent;
// the server's refusals show beside the reason, or above the buttons; on the demo the reason is the ready one to tap;
// with no network the main button is held.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { answer, refusal, sent } from "@/test/fake-server";
import {
  MealMoneyAsked,
  mealMoneyIsAnswered,
  MonthsAsked,
  monthsAreAnswered,
  row,
} from "@/test/meals";
import { PayAsked, payIsAnswered } from "@/test/pay";
import { render } from "@/test/render";

import { VoidMealMoney } from "./void-meal-money";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

// A test that takes the network away puts it back after (navigator.onLine's spy).
afterEach(() => {
  vi.restoreAllMocks();
});

const MEAT = row({ amount: "30000.00", note: "Nyama" });
const VOID = `/api/v1/staffpay/meal-money/${MEAT.id}/void/`;
const CROSSED = {
  ...MEAT,
  voided: {
    by: "Baba",
    at: "2026-11-23T16:00:00Z",
    reason: "Sifuri moja zaidi",
  },
};

function openOn(line = MEAT, readyReasons: "wrong_amount"[] = []) {
  const onDone = vi.fn();
  const onClose = vi.fn();
  render(
    <VoidMealMoney
      row={line}
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
  screen.getByRole("dialog", { name: /^Batilisha TSh\s30,000$/ });
const reasonBox = () => within(sheet()).getByLabelText("Sababu");
const crossOut = () =>
  within(sheet()).getByRole("button", { name: "Batilisha" });

describe("Batilisha, of meal money", () => {
  it("names the amount, the day and what it bought", () => {
    openOn();

    expect(sheet().textContent).toContain("Jumatatu 23/11/2026 · Nyama");
  });

  it("names the day alone when nothing says what it bought", () => {
    openOn({ ...MEAT, note: "" });

    expect(sheet().textContent).toContain("Jumatatu 23/11/2026");
    expect(sheet().textContent).not.toContain("·");
  });

  it("sends the reason to the row's own route, then is done", async () => {
    answer("POST", VOID, { status: 200, body: CROSSED });
    const { onDone } = openOn();

    fireEvent.change(reasonBox(), { target: { value: "Sifuri moja zaidi" } });
    fireEvent.click(crossOut());

    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
    expect(await sentBodies()).toEqual([{ reason: "Sifuri moja zaidi" }]);
  });

  it.each([
    ["crossed out", { status: 200, body: CROSSED }],
    // The server crossed it out, and its answer was lost: the day behind the sheet must not go on counting the row
    // (WAGE-7's review).
    ["no answer", refusal(503, "server_error")],
  ])(
    "asks the days, the workers' months and the pay again: %s",
    async (_how, reply) => {
      answer("POST", VOID, reply);
      const meals = mealMoneyIsAnswered();
      const months = monthsAreAnswered();
      const payAsked = payIsAnswered();
      render(
        <>
          <MealMoneyAsked />
          <MonthsAsked />
          <PayAsked />
          <VoidMealMoney
            row={MEAT}
            readyReasons={[]}
            onDone={vi.fn()}
            onClose={vi.fn()}
            finalFocus={() => null}
          />
        </>,
      );
      await waitFor(() =>
        expect([meals(), months().worker, payAsked()]).toEqual([1, 1, [1, 1]]),
      );

      fireEvent.change(reasonBox(), { target: { value: "Sifuri moja zaidi" } });
      fireEvent.click(crossOut());

      await waitFor(() =>
        expect([meals(), months().worker, payAsked()]).toEqual([2, 2, [2, 2]]),
      );
    },
  );

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

    answer("POST", VOID, refusal(403, "permission_denied"));
    fireEvent.click(crossOut());
    expect(await within(sheet()).findByRole("alert")).toBeTruthy();
    expect(onDone).not.toHaveBeenCalled();
  });

  it("offers the ready reason on the demo, and sends its code", async () => {
    answer("POST", VOID, { status: 200, body: CROSSED });
    openOn(MEAT, ["wrong_amount"]);
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
