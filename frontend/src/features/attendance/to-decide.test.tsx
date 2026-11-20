// to-decide.test.tsx — Zinahitaji uamuzi, the days a person must decide, at the top of the month page (ATT-5): a line
// per day, "Juma · Alhamisi 12/11 · hakuna Toka", for each of the nine reasons, in the server's order, counted in the
// heading; each line a link to its day under the worker's calendar (ATT-12); a line when there is none; and the same in
// English.
import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { components } from "@/api/schema";
import { setLanguage } from "@/i18n/language";
import { render } from "@/test/render";

import { DaysToDecide } from "./to-decide";

type DayToDecide = components["schemas"]["DayToDecide"];
type Reason = DayToDecide["reason"];

/** A day to decide: Juma's Thursday 12 November, an Ingia at 07:20 and no Toka, unless told otherwise. */
function day(fields: Partial<DayToDecide> = {}): DayToDecide {
  return {
    staff: "019a8400-0000-7000-8000-000000000001",
    display_name: "Juma",
    date: "2026-11-12",
    reason: "no_out",
    first_in: "07:20",
    first_out: null,
    ...fields,
  };
}

/** The list's lines, as their words. */
function lines(): string[] {
  const list = screen.getByRole("list", { name: /Zinahitaji uamuzi|decision/ });
  return within(list)
    .getAllByRole("listitem")
    .map((item) => item.textContent ?? "");
}

describe("the days to decide", () => {
  it("opens each day under its worker's calendar, on the day's month (ATT-12)", () => {
    render(<DaysToDecide days={[day()]} />);

    const line = screen.getByRole("link", {
      name: "Juma · Alhamisi 12/11 · hakuna Toka",
    });
    // Next.js's Link drops the trailing slash outside a built app (month-screen.test.tsx).
    expect(line.getAttribute("href")).toMatch(
      /^\/attendance-month\/worker\/?\?staff=019a8400-0000-7000-8000-000000000001&month=2026-11&day=2026-11-12$/,
    );
  });

  it("says each day's worker, weekday and date, and why, in the server's order, counted", () => {
    // The server sends them oldest first, by name on a day: the page keeps its order.
    render(
      <DaysToDecide
        days={[
          day({
            display_name: "Baraka",
            date: "2026-11-02",
            reason: "came_late",
            first_in: "09:10",
            first_out: "18:45",
          }),
          day(),
        ]}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Zinahitaji uamuzi (2)" }),
    ).toBeTruthy();
    expect(lines()).toEqual([
      "Baraka · Jumatatu 02/11 · alifika saa 09:10 asubuhi",
      "Juma · Alhamisi 12/11 · hakuna Toka",
    ]);
  });

  it.each<[Reason, Partial<DayToDecide>, string]>([
    ["outside_job", {}, "nje ya siku zake za kazi"],
    ["closed_day", {}, "duka lilikuwa limefungwa"],
    ["not_working", {}, "alikuwa amesimamishwa au ameondoka"],
    ["clock_disagrees", {}, "saa yake ina shaka"],
    ["time_unknown", { first_in: null }, "saa yake haijulikani"],
    ["no_in", { first_in: null, first_out: "18:45" }, "hakuna Ingia"],
    [
      "came_late",
      { first_in: "13:20", first_out: "18:45" },
      "alifika saa 13:20 mchana",
    ],
    ["no_out", {}, "hakuna Toka"],
    ["left_early", { first_out: "16:05" }, "aliondoka saa 16:05 jioni"],
  ])("says why for %s", (reason, taps, why) => {
    // Each of the book's nine reasons (ReviewReason, apps/staffpay/models.py) in words; the two about a time say it,
    // with its part of the day, so nobody reads 13:20 as Swahili time (SYNC-11).
    render(<DaysToDecide days={[day({ reason, ...taps })]} />);

    expect(lines()).toEqual([`Juma · Alhamisi 12/11 · ${why}`]);
  });

  it("names the list once, by its heading, with an id of its own (the review)", () => {
    // A screen reader says the list's name as it enters it; a region named the same around it said it twice. Two
    // lists on one page (ATT-12 may show a second) never share an id, so each is named by its own heading.
    render(
      <>
        <DaysToDecide days={[day()]} />
        <DaysToDecide days={[day(), day({ date: "2026-11-13" })]} />
      </>,
    );

    expect(screen.queryByRole("region")).toBeNull();
    const lists = screen.getAllByRole("list");
    expect(
      lists.map((list) => list.getAttribute("aria-labelledby")),
    ).toHaveLength(2);
    expect(lists[0]?.getAttribute("aria-labelledby")).not.toBe(
      lists[1]?.getAttribute("aria-labelledby"),
    );
    expect(
      screen.getByRole("list", { name: "Zinahitaji uamuzi (2)" }),
    ).toBeTruthy();
  });

  it("says so when no day needs a decision", () => {
    render(<DaysToDecide days={[]} />);

    expect(
      screen.getByRole("heading", { name: "Zinahitaji uamuzi (0)" }),
    ).toBeTruthy();
    expect(
      screen.getByText("Hakuna siku inayohitaji uamuzi mwezi huu."),
    ).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("speaks English after the switch", () => {
    setLanguage("en");

    render(
      <DaysToDecide
        days={[
          day(),
          day({ reason: "came_late", first_in: "09:10", first_out: "18:45" }),
        ]}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Need a decision (2)" }),
    ).toBeTruthy();
    expect(lines()).toEqual([
      "Juma · Thursday 12/11 · no Toka",
      "Juma · Thursday 12/11 · came at 09:10",
    ]);
  });
});
