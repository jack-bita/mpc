// my-day-sheet.test.tsx — one of a worker's own days, in its sheet (WAGE-4): a tap crossed out in the office struck
// through with who, when and why, and one added there with who added it and why (Jack: A); a decided day with who
// decided it and what the system said (A2); today, not over yet; and nothing to change, only Funga.
import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { render } from "@/test/render";

import { MyDaySheet } from "./my-day-sheet";

type OwnAttendance = components["schemas"]["OwnAttendanceAnswer"];
type OwnTap = components["schemas"]["OwnTap"];

function tap(changes: Partial<OwnTap>): OwnTap {
  return {
    id: "019a8400-0000-7000-8000-0000000000e1",
    date: "2026-11-04",
    kind: "in",
    time: "07:20",
    laptop_time: null,
    laptop: "Laptop ya Dawa",
    entered: null,
    voided: null,
    after_approval: false,
    ...changes,
  };
}

const MONTH: OwnAttendance = {
  month: "2026-11",
  today: "2026-11-27",
  worker: {
    staff: "019a8400-0000-7000-8000-000000000a5a",
    display_name: "Asha",
    on_time: 0,
    late: 0,
    half: 0,
    absent: 1,
    needs_review: 0,
  },
  started_on: "2026-09-01",
  left_on: null,
  days: [
    {
      date: "2026-11-04",
      status: "absent",
      reason: null,
      fine: "0.00",
      meal_share: "0.00",
      first_in: null,
      first_out: null,
      decision: null,
    },
  ],
  taps: [],
  ready_reasons: [],
  ready_add_reasons: [],
  ready_void_reasons: [],
};

function open(answer: OwnAttendance, day = "2026-11-04") {
  const onClose = vi.fn();
  render(
    <MyDaySheet
      day={day}
      answer={answer}
      timezone="Africa/Dar_es_Salaam"
      onClose={onClose}
    />,
  );
  return { sheet: screen.getByRole("dialog"), onClose };
}

describe("a worker's own day", () => {
  it("shows a tap the office crossed out, struck through, with who, when and why (Jack: A)", () => {
    // Meneja crossed out Asha's Ingia of the 4th, so the day is absent: she sees why, not just that.
    const { sheet } = open({
      ...MONTH,
      taps: [
        tap({
          voided: {
            by: "Meneja",
            at: "2026-11-05T06:00:00Z",
            reason: "Alibonyeza kwa makosa",
          },
        }),
      ],
    });
    const struck = within(sheet).getByText(
      "Ingia 07:20 asubuhi · Laptop ya Dawa",
    );
    expect(struck.tagName).toBe("S");
    expect(sheet.textContent).toContain(
      "Imebatilishwa na Meneja, 05/11/2026 · Sababu: Alibonyeza kwa makosa",
    );
    // Crossed out, it counts for nothing, so the day says what it is missing as if it weren't there.
    expect(sheet.textContent).toContain("Hakuna Ingia wala Toka siku hii.");
  });

  it("shows a tap the office added, with who added it and why (Jack: A)", () => {
    const { sheet } = open({
      ...MONTH,
      taps: [
        tap({
          kind: "out",
          time: "18:45",
          laptop: null,
          entered: {
            by: "Meneja",
            at: "2026-11-05T06:00:00Z",
            reason: "Alisahau kubonyeza Toka",
          },
        }),
      ],
    });
    expect(sheet.textContent).toContain(
      "Toka 18:45 jioni · imeongezwa na Meneja, 05/11/2026",
    );
    expect(sheet.textContent).toContain("Sababu: Alisahau kubonyeza Toka");
  });

  it("shows a decided day with who decided it and what the system said (A2)", () => {
    const { sheet } = open({
      ...MONTH,
      days: [
        {
          ...MONTH.days[0]!,
          status: "needs_review",
          reason: "no_out",
          decision: {
            status: "on_time",
            absence_type: null,
            fine: "0.00",
            by: "Meneja",
            at: "2026-11-05T06:00:00Z",
            reason: "Alisahau kubonyeza Toka",
          },
        },
      ],
    });
    expect(sheet.textContent).toContain("uamuzi wa Meneja, 05/11/2026");
    expect(sheet.textContent).toContain("Sababu: Alisahau kubonyeza Toka");
    expect(sheet.textContent).toContain("Mfumo ulisema:");
  });

  it("says today isn't over yet", () => {
    const { sheet } = open(
      { ...MONTH, taps: [tap({ date: "2026-11-27" })] },
      "2026-11-27",
    );
    expect(
      within(sheet).getByRole("heading", { name: "Ijumaa 27/11/2026 · leo" }),
    ).toBeDefined();
    expect(sheet.textContent).toContain("Siku bado haijaisha.");
  });

  it("offers nothing to change, only Funga, which closes it", () => {
    const { sheet, onClose } = open({ ...MONTH, taps: [tap({})] });
    expect(
      within(sheet)
        .getAllByRole("button")
        .map((button) => button.textContent),
    ).toEqual(["Funga"]);
    // No photo and no doubt: the worker's own answer carries neither.
    expect(within(sheet).queryByRole("img")).toBeNull();
    expect(sheet.textContent).not.toContain("Shaka");
    fireEvent.click(within(sheet).getByRole("button", { name: "Funga" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
