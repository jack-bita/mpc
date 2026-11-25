// record-meal-money.test.tsx — Andika hela ya chakula (WAGE-7): the button, and the sheet that types what the meals of a
// day cost; what the sheet sees itself is said at once, beside its box, and nothing is sent; the server's refusals show
// beside theirs; a try sent again carries the same id; and once saved, a line says what was written, with the keyboard
// on it.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { answer, refusal, sent } from "@/test/fake-server";
import {
  MealMoneyAsked,
  mealMoneyIsAnswered,
  MonthsAsked,
  monthsAreAnswered,
  row,
  TODAY,
} from "@/test/meals";
import { PayAsked, payIsAnswered } from "@/test/pay";
import { render } from "@/test/render";

import { RecordMealMoney } from "./record-meal-money";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

// A test that takes the network away puts it back after (navigator.onLine's spy).
afterEach(() => {
  vi.restoreAllMocks();
});

const MEAL_MONEY = "/api/v1/staffpay/meal-money/";

/** What the app sent, each as the server would read it. */
async function sentBodies(): Promise<Record<string, unknown>[]> {
  return Promise.all(
    sent
      .filter((request) => request.method === "POST")
      .map((request) => request.json() as Promise<Record<string, unknown>>),
  );
}

/** The error beside a box: the one its aria-describedby names (field.tsx). */
function errorOf(element: HTMLElement): string {
  const ids = element.getAttribute("aria-describedby")?.split(" ") ?? [];
  const error = ids.find((id) => id.endsWith("-error"));
  return error ? (document.getElementById(error)?.textContent ?? "") : "";
}

const button = () =>
  screen.getByRole("button", { name: "Andika hela ya chakula" });
const sheet = () =>
  screen.getByRole("dialog", { name: "Andika hela ya chakula" });
const box = (label: string) => within(sheet()).getByLabelText(label);
const value = (label: string) => (box(label) as HTMLInputElement).value;
const save = () => within(sheet()).getByRole("button", { name: "Hifadhi" });

function type(label: string, typed: string) {
  fireEvent.change(box(label), { target: { value: typed } });
}

function openSheet(day: string = TODAY) {
  render(<RecordMealMoney day={day} today={TODAY} />);
  fireEvent.click(button());
}

describe("Andika hela ya chakula", () => {
  it("sends the day, the amount and what it bought, then says what was written", async () => {
    answer("POST", MEAL_MONEY, async (request) => {
      const body = (await request.clone().json()) as Record<string, string>;
      return Response.json(
        row({ id: body.id, date: body.date, amount: "9000.00" }),
        { status: 201 },
      );
    });
    openSheet();
    expect(value("Siku")).toBe(TODAY);

    type("Kiasi (TSh)", "9,000");
    type("Maelezo (si lazima)", "Unga na maharage");
    fireEvent.click(save());

    const said = await screen.findByText(
      "Imeandikwa: TSh 9,000, Jumanne 24/11/2026.",
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    const [body, ...more] = await sentBodies();
    expect(more).toEqual([]);
    expect(body).toEqual({
      id: expect.stringMatching(/^[0-9a-f]{8}-[0-9a-f]{4}-7/),
      date: TODAY,
      amount: "9000",
      note: "Unga na maharage",
    });
    // The keyboard is on the line, so a screen reader says what was written.
    await waitFor(() =>
      expect(document.activeElement?.contains(said)).toBe(true),
    );
  });

  it.each([
    ["saved", 201],
    ["no answer", 503],
  ])(
    "asks the days, the workers' months and the pay again, as each share moves: %s",
    async (_how, status) => {
      const meals = mealMoneyIsAnswered();
      answer("POST", MEAL_MONEY, {
        status,
        body: row({ date: TODAY, amount: "9000.00" }),
      });
      const months = monthsAreAnswered();
      const payAsked = payIsAnswered();
      render(
        <>
          <MealMoneyAsked />
          <MonthsAsked />
          <PayAsked />
          <RecordMealMoney day={TODAY} today={TODAY} />
        </>,
      );
      await waitFor(() =>
        expect([meals(), months().worker, payAsked()]).toEqual([1, 1, [1, 1]]),
      );
      fireEvent.click(button());

      type("Kiasi (TSh)", "9000");
      fireEvent.click(save());

      // The POST goes to the list's own address, so it is counted too.
      await waitFor(() =>
        expect([meals(), months().worker, payAsked()]).toEqual([3, 2, [2, 2]]),
      );
    },
  );

  it("starts on the day it was opened for, and offers no day to come", () => {
    openSheet("2026-11-21");

    expect(value("Siku")).toBe("2026-11-21");
    expect(box("Siku").getAttribute("max")).toBe(TODAY);
  });

  it.each([
    ["", "5000", "Siku", "Jaza sehemu hii."],
    ["2026-11-25", "5000", "Siku", "Siku hii bado haijafika."],
    [
      "2026-11-22",
      "5000",
      "Siku",
      "Siku hii si siku ya kazi, kwa hiyo haina hela ya chakula.",
    ],
    [
      TODAY,
      "",
      "Kiasi (TSh)",
      "Andika kiasi cha shilingi nzima, zaidi ya sifuri.",
    ],
    [
      TODAY,
      "0",
      "Kiasi (TSh)",
      "Andika kiasi cha shilingi nzima, zaidi ya sifuri.",
    ],
    [
      TODAY,
      "5000.50",
      "Kiasi (TSh)",
      "Andika kiasi cha shilingi nzima, zaidi ya sifuri.",
    ],
  ])(
    "says a wrong box at once, and sends nothing: %s, %s",
    async (day, amount, label, sentence) => {
      openSheet();

      type("Siku", day);
      type("Kiasi (TSh)", amount);
      fireEvent.click(save());

      await waitFor(() => expect(errorOf(box(label))).toBe(sentence));
      expect(sent).toEqual([]);
    },
  );

  it("shows the server's refusals beside their boxes", async () => {
    answer(
      "POST",
      MEAL_MONEY,
      refusal(
        400,
        "invalid",
        {},
        {
          date: ["meal_money.not_working_day"],
          amount: ["meal_money.amount_too_big"],
          note: ["demo.no_note"],
        },
      ),
    );
    openSheet();

    type("Kiasi (TSh)", "50000000");
    fireEvent.click(save());

    await waitFor(() =>
      expect(errorOf(box("Kiasi (TSh)"))).toBe(
        "Kiasi hiki ni kikubwa mno. Angalia sifuri zake.",
      ),
    );
    expect(errorOf(box("Siku"))).toBe(
      "Siku hii si siku ya kazi, kwa hiyo haina hela ya chakula.",
    );
    expect(errorOf(box("Maelezo (si lazima)"))).toBe(
      "Kwenye demo, maelezo hayahifadhiwi. Acha kisanduku hiki wazi.",
    );
  });

  it("shows a refusal of the whole request, and of a field with no box, above the buttons", async () => {
    // The key was taken away a moment ago; or the id clashes, which no box is about.
    answer("POST", MEAL_MONEY, refusal(403, "permission_denied"));
    openSheet();
    type("Kiasi (TSh)", "5000");
    fireEvent.click(save());
    expect(await within(sheet()).findByRole("alert")).toBeTruthy();

    answer(
      "POST",
      MEAL_MONEY,
      refusal(400, "invalid", {}, { id: ["id.taken"] }),
    );
    fireEvent.click(save());
    await waitFor(() =>
      expect(within(sheet()).getByRole("alert").textContent).toContain(
        "Namba ya utambulisho imeshatumika",
      ),
    );
  });

  it("sends the same try again under the same id, and a changed one under a new id", async () => {
    // The answer was lost on the way: the same try must find the row the first made, never type it twice. A changed
    // amount is another row, for the list to show beside the first.
    answer("POST", MEAL_MONEY, refusal(503, "server_error"));
    openSheet();
    type("Kiasi (TSh)", "9000");
    fireEvent.click(save());
    await waitFor(() => expect(sent).toHaveLength(1));
    await within(sheet()).findByRole("alert");
    fireEvent.click(save());
    await waitFor(() => expect(sent).toHaveLength(2));
    await waitFor(() => expect(save().getAttribute("disabled")).toBeNull());
    type("Kiasi (TSh)", "8000");
    fireEvent.click(save());
    await waitFor(() => expect(sent).toHaveLength(3));

    const ids = (await sentBodies()).map((body) => body.id);
    expect(ids[0]).toBe(ids[1]);
    expect(ids[2]).not.toBe(ids[0]);
  });

  it("closes on Ghairi with nothing sent, the keyboard back on the button", async () => {
    openSheet();
    type("Kiasi (TSh)", "9000");

    fireEvent.click(within(sheet()).getByRole("button", { name: "Ghairi" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(sent).toEqual([]);
    await waitFor(() => expect(document.activeElement).toBe(button()));
    // Opened again, the boxes are empty: nothing half-typed is kept.
    fireEvent.click(button());
    expect(value("Kiasi (TSh)")).toBe("");
  });

  it("holds the main button with no network, so nothing waits unsent", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    openSheet();

    expect((save() as HTMLButtonElement).disabled).toBe(true);
  });
});
