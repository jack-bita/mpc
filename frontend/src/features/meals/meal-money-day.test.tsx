// meal-money-day.test.tsx — one day's own page (WAGE-7): its total and how it is split, each row with who typed it and
// when, the crossed-out ones struck through with who, when and why; Batilisha under a row that counts; and Andika hela ya
// chakula, which starts on the day itself. On a day whose pay is approved, neither button, and why (WAGE-3).
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import {
  mealDay,
  mealDays,
  type MealMoneyDays,
  row,
  TODAY,
  WITH_THE_KEY,
} from "@/test/meals";
import { render } from "@/test/render";

import { MealMoneyDayScreen } from "./meal-money-day";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const MEAL_MONEY = "/api/v1/staffpay/meal-money/";
const MONDAY = "2026-11-23";

const FLOUR = row();
const MEAT = row({
  amount: "3000.00",
  note: "Nyama",
  at: "2026-11-23T08:30:00Z",
});
const SLIP = row({
  amount: "30000.00",
  note: "Nyama",
  at: "2026-11-23T08:20:00Z",
  voided: {
    by: "Baba",
    at: "2026-11-23T16:00:00Z",
    reason: "Sifuri moja zaidi",
  },
});

/** Monday as Jack drew it (24 Nov 2026). */
const MONDAYS = mealDays([mealDay({ rows: [FLOUR, SLIP, MEAT] })], {
  first: MONDAY,
  last: MONDAY,
  total: "8000.00",
});

function theDayIs(body: MealMoneyDays) {
  answer("GET", ME, { status: 200, body: WITH_THE_KEY });
  answer("GET", MEAL_MONEY, { status: 200, body });
}

function wordsOf(part: Element | null): string {
  return (part?.textContent ?? "").replace(/ /g, " ");
}

/** The rows, each as its words, its button's too. */
async function rows(): Promise<string[]> {
  const list = await screen.findByRole("list", {
    name: "Hela iliyoandikwa siku hii",
  });
  return within(list)
    .getAllByRole("listitem")
    .map((line) =>
      [...line.querySelectorAll("p, button")].map(wordsOf).join(" | "),
    );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-24T09:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("one day's meal money", () => {
  it("shows Monday as Jack drew it", async () => {
    theDayIs(MONDAYS);

    render(<MealMoneyDayScreen date={MONDAY} />);

    expect(await rows()).toEqual([
      "TSh 5,000 · Unga na maharage | Asha · 23/11/2026 08:10 asubuhi | Batilisha",
      "TSh 30,000 · Nyama | Asha · 23/11/2026 11:20 asubuhi | Imebatilishwa na Baba, 23/11/2026 | Sababu: Sifuri moja zaidi",
      "TSh 3,000 · Nyama | Asha · 23/11/2026 11:30 asubuhi | Batilisha",
    ]);
    expect(
      screen.getByRole("heading", { level: 1, name: "Jumatatu 23/11/2026" }),
    ).toBeTruthy();
    expect(wordsOf(screen.getByText(/^Jumla/))).toBe("Jumla TSh 8,000");
    expect(wordsOf(screen.getByText(/^Watu 8/))).toBe(
      "Watu 8 · TSh 1,000 kila mmoja",
    );
    // That day alone is asked for.
    const asked = new URL(sent.at(-1)?.url ?? "").searchParams;
    expect([asked.get("first"), asked.get("last")]).toEqual([MONDAY, MONDAY]);
  });

  it("strikes through a crossed-out row, for the eye", async () => {
    theDayIs(MONDAYS);

    render(<MealMoneyDayScreen date={MONDAY} />);

    await rows();
    const struck = document.querySelectorAll("s");
    expect([...struck].map(wordsOf)).toEqual(["TSh 30,000 · Nyama"]);
  });

  it("crosses out a row from its own button, and shows it struck through with the keyboard on it", async () => {
    theDayIs(MONDAYS);
    render(<MealMoneyDayScreen date={MONDAY} />);
    await rows();
    const crossed = {
      ...MEAT,
      voided: {
        by: "Meneja",
        at: "2026-11-24T09:00:00Z",
        reason: "Siku nyingine",
      },
    };
    answer("POST", `${MEAL_MONEY}${MEAT.id}/void/`, {
      status: 200,
      body: crossed,
    });
    theDayIs(
      mealDays(
        [
          mealDay({
            amount: "5000.00",
            share: "625.00",
            rows: [FLOUR, SLIP, crossed],
          }),
        ],
        { first: MONDAY, last: MONDAY, total: "5000.00" },
      ),
    );

    fireEvent.click(
      screen.getByRole("button", { name: /^Batilisha TSh\s3,000 · Nyama$/ }),
    );
    const sheet = screen.getByRole("dialog", {
      name: /^Batilisha TSh\s3,000$/,
    });
    fireEvent.change(within(sheet).getByLabelText("Sababu"), {
      target: { value: "Siku nyingine" },
    });
    fireEvent.click(within(sheet).getByRole("button", { name: "Batilisha" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() =>
      expect(wordsOf(screen.getByText(/^Jumla/))).toBe("Jumla TSh 5,000"),
    );
    expect((await rows())[2]).toBe(
      "TSh 3,000 · Nyama | Asha · 23/11/2026 11:30 asubuhi | Imebatilishwa na Meneja, 24/11/2026 | Sababu: Siku nyingine",
    );
    // Its button is gone, so the keyboard is on the row itself.
    await waitFor(() =>
      expect(wordsOf(document.activeElement)).toBe("TSh 3,000 · Nyama"),
    );
  });

  it("shows a row crossed out whose answer was lost, and gives the keyboard to it on Ghairi", async () => {
    // The server crossed it out and the network dropped: the sheet says so, the day behind it is read again, and Ghairi
    // finds no button to go back to (WAGE-7's review).
    theDayIs(MONDAYS);
    render(<MealMoneyDayScreen date={MONDAY} />);
    await rows();
    answer(
      "POST",
      `${MEAL_MONEY}${MEAT.id}/void/`,
      refusal(503, "server_error"),
    );
    fireEvent.click(screen.getByRole("button", { name: /TSh\s3,000/ }));
    const sheet = screen.getByRole("dialog");
    fireEvent.change(within(sheet).getByLabelText("Sababu"), {
      target: { value: "Siku nyingine" },
    });
    theDayIs(
      mealDays(
        [
          mealDay({
            amount: "5000.00",
            rows: [
              FLOUR,
              SLIP,
              {
                ...MEAT,
                voided: {
                  by: "Meneja",
                  at: "2026-11-24T09:00:00Z",
                  reason: "Siku nyingine",
                },
              },
            ],
          }),
        ],
        { first: MONDAY, last: MONDAY, total: "5000.00" },
      ),
    );
    fireEvent.click(within(sheet).getByRole("button", { name: "Batilisha" }));
    await within(sheet).findByRole("alert");
    await waitFor(() => expect(document.querySelectorAll("s")).toHaveLength(2));

    fireEvent.click(within(sheet).getByRole("button", { name: "Ghairi" }));

    await waitFor(() =>
      expect(wordsOf(document.activeElement)).toBe("TSh 3,000 · Nyama"),
    );
  });

  it("gives the keyboard back to Batilisha on Ghairi", async () => {
    theDayIs(MONDAYS);
    render(<MealMoneyDayScreen date={MONDAY} />);
    await rows();
    const button = screen.getByRole("button", {
      name: /^Batilisha TSh\s5,000 · Unga na maharage$/,
    });
    fireEvent.click(button);

    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Ghairi",
      }),
    );

    await waitFor(() => expect(document.activeElement).toBe(button));
  });

  it("names each Batilisha by its row, with its note when it has one", async () => {
    // Two rows of one amount: only the note tells a screen reader's two buttons apart (WAGE-7's review).
    theDayIs(
      mealDays([
        mealDay({
          rows: [
            row({ amount: "3000.00", note: "Nyama" }),
            row({ amount: "3000.00", note: "Mboga" }),
            row({ amount: "2000.00", note: "" }),
          ],
        }),
      ]),
    );

    render(<MealMoneyDayScreen date={MONDAY} />);
    await rows();

    expect(
      screen
        .getAllByRole("button", { name: /^Batilisha/ })
        .map((button) =>
          button.getAttribute("aria-label")?.replace(/\u00a0/g, " "),
        ),
    ).toEqual([
      "Batilisha TSh 3,000 · Nyama",
      "Batilisha TSh 3,000 · Mboga",
      "Batilisha TSh 2,000",
    ]);
  });

  it("says a ready reason's code in words, on the demo", async () => {
    const crossed = row({
      voided: {
        by: "Meneja",
        at: "2026-11-24T09:00:00Z",
        reason: "wrong_amount",
      },
    });
    theDayIs(
      mealDays([mealDay({ rows: [crossed] })], {
        ready_void_reasons: ["wrong_amount"],
      }),
    );

    render(<MealMoneyDayScreen date={MONDAY} />);

    expect((await rows())[0]).toContain("Sababu: Kiasi kimekosewa");
  });

  it("says a forgotten day is not written, and offers to write it, starting on that day", async () => {
    theDayIs(
      mealDays(
        [
          mealDay({
            date: "2026-11-21",
            amount: "0.00",
            sharers: 6,
            share: "0.00",
          }),
        ],
        { first: "2026-11-21", last: "2026-11-21" },
      ),
    );

    render(<MealMoneyDayScreen date="2026-11-21" />);

    expect(await screen.findByText("Haijaandikwa")).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: "Andika hela ya chakula" }),
    );
    expect(
      (
        within(screen.getByRole("dialog")).getByLabelText(
          "Siku",
        ) as HTMLInputElement
      ).value,
    ).toBe("2026-11-21");
  });

  it("says nobody typed any when every row of the day is crossed out", async () => {
    theDayIs(
      mealDays([
        mealDay({ amount: "0.00", sharers: 8, share: "0.00", rows: [SLIP] }),
      ]),
    );

    render(<MealMoneyDayScreen date={MONDAY} />);

    expect((await rows()).length).toBe(1);
    expect(screen.getByText("Haijaandikwa")).toBeTruthy();
    expect(screen.queryByText(/^Jumla/)).toBeNull();
  });

  it("says today's money is not split yet", async () => {
    theDayIs(
      mealDays([
        mealDay({
          date: TODAY,
          amount: "9000.00",
          over: false,
          sharers: 0,
          share: "0.00",
        }),
      ]),
    );

    render(<MealMoneyDayScreen date={TODAY} />);

    expect(await screen.findByText("Itagawanywa siku ikiisha")).toBeTruthy();
  });

  it.each([["2026-11-22"], ["2026-11-25"]])(
    "says a Sunday, or a day to come, has none, and offers nothing to write: %s",
    async (date) => {
      // Not "Haijaandikwa": nobody forgot it (WAGE-7's review).
      theDayIs(mealDays([], { first: date, last: date }));

      render(<MealMoneyDayScreen date={date} />);

      await screen.findByText("Hakuna hela ya chakula siku hii.");
      expect(screen.queryByText("Haijaandikwa")).toBeNull();
      expect(
        screen.queryByRole("button", { name: "Andika hela ya chakula" }),
      ).toBeNull();
    },
  );

  it("says a working day nobody came has none, and still offers to write it", async () => {
    // A day the cook alone came, or nobody: the server answers no day. Its money may still be typed.
    theDayIs(mealDays([], { first: MONDAY, last: MONDAY }));

    render(<MealMoneyDayScreen date={MONDAY} />);

    await screen.findByText("Hakuna hela ya chakula siku hii.");
    expect(
      screen.getByRole("button", { name: "Andika hela ya chakula" }),
    ).toBeTruthy();
  });

  it("says a day nobody came, its one row crossed out, has none", async () => {
    theDayIs(
      mealDays([
        mealDay({ amount: "0.00", sharers: 0, share: "0.00", rows: [SLIP] }),
      ]),
    );

    render(<MealMoneyDayScreen date={MONDAY} />);

    expect((await rows()).length).toBe(1);
    expect(screen.getByText("Hakuna hela ya chakula siku hii.")).toBeTruthy();
  });

  it.each([[null], ["jana"], ["2026-11-31"]])(
    "asks nothing for a day the address can't mean: %s",
    async (date) => {
      answer("GET", ME, { status: 200, body: WITH_THE_KEY });

      render(<MealMoneyDayScreen date={date} />);

      expect(
        await screen.findByText("Hakuna siku iliyochaguliwa."),
      ).toBeTruthy();
      expect(
        sent.filter((request) => new URL(request.url).pathname === MEAL_MONEY),
      ).toEqual([]);
    },
  );

  it("offers no Batilisha and nothing to write on a day whose pay is approved, and says why", async () => {
    // Monday is the last day of it: that day is closed too.
    theDayIs({ ...MONDAYS, closed_to: MONDAY });

    render(<MealMoneyDayScreen date={MONDAY} />);

    expect(
      await screen.findByText(
        "Malipo ya siku hii yamefungwa, kwa hiyo hela yake ya chakula haibadiliki tena.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Batilisha/ })).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Andika hela ya chakula" }),
    ).toBeNull();
    // Its rows stay to be read, the crossed-out one as it was.
    expect(await rows()).toEqual([
      "TSh 5,000 · Unga na maharage | Asha · 23/11/2026 08:10 asubuhi",
      "TSh 30,000 · Nyama | Asha · 23/11/2026 11:20 asubuhi | Imebatilishwa na Baba, 23/11/2026 | Sababu: Sifuri moja zaidi",
      "TSh 3,000 · Nyama | Asha · 23/11/2026 11:30 asubuhi",
    ]);
  });

  it("keeps both buttons the day after the last one approved", async () => {
    theDayIs({ ...MONDAYS, closed_to: "2026-11-22" });

    render(<MealMoneyDayScreen date={MONDAY} />);

    await rows();
    expect(screen.getAllByRole("button", { name: /Batilisha/ })).toHaveLength(
      2,
    );
    expect(
      screen.getByRole("button", { name: "Andika hela ya chakula" }),
    ).toBeTruthy();
    expect(screen.queryByText(/yamefungwa/)).toBeNull();
  });

  it("says why on a closed day nobody wrote any for, in place of the button", async () => {
    theDayIs(
      mealDays(
        [mealDay({ amount: "0.00", sharers: 6, share: "0.00", rows: [] })],
        { first: MONDAY, last: MONDAY, closed_to: "2026-11-30" },
      ),
    );

    render(<MealMoneyDayScreen date={MONDAY} />);

    expect(await screen.findByText(/yamefungwa/)).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Andika hela ya chakula" }),
    ).toBeNull();
  });

  it("shows only the server's refusal to someone without the key", async () => {
    answer("GET", ME, { status: 200, body: whoIsHere([]) });
    answer("GET", MEAL_MONEY, refusal(403, "permission_denied"));

    render(<MealMoneyDayScreen date={MONDAY} />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("Haijaandikwa")).toBeNull();
    expect(screen.queryByRole("button", { name: /Andika/ })).toBeNull();
  });
});
