// worker-month-screen.test.tsx — a worker's month as a calendar (ATT-12): the worker's name as the title, the month,
// the counts as the server counted them, each day's mark Monday first, – for a shut day, • for today, nothing for a
// day the book doesn't answer; the month asked of the server; the way back to the month page; and the server's
// refusal.
import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";

import { WorkerMonthScreen } from "./worker-month-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type WorkerAttendance = components["schemas"]["WorkerAttendanceAnswer"];
type WorkerDay = components["schemas"]["WorkerDay"];

const ME = "/api/auth/me/";
const JUMA = "019a8400-0000-7000-8000-000000000007";
const JUMAS_MONTH = `/api/v1/staffpay/attendance-worker/${JUMA}/`;
// Friday 20 November 2026, noon in Arusha.
const NOW = "2026-11-20T09:00:00Z";

/** Neema, a manager: attendance.manage on the whole shop. */
const MENEJA: components["schemas"]["WhoIsHere"] = {
  ...whoIsHere([]),
  permissions: {
    whole_shop: ["attendance.manage"],
    sides: [
      { ...DAWA, permissions: ["attendance.manage"] },
      { ...VYAKULA, permissions: ["attendance.manage"] },
    ],
  },
};

/** A day of Juma's November, as the book keeps it. */
function day(date: number, status: WorkerDay["status"]): WorkerDay {
  return {
    // Each day its own id, made from its date, as the server sends one.
    id: `019a8400-0000-7000-9000-${String(date).padStart(12, "0")}`,
    date: `2026-11-${String(date).padStart(2, "0")}`,
    status,
    reason: status === "needs_review" ? "no_out" : null,
    fine: status === "late" ? "500.00" : "0.00",
    meal_share: "0.00",
    first_in: null,
    first_out: null,
    decision: null,
    choices: [],
    taps_changed: false,
  };
}

/** Juma's November as on Jack's picture: Sundays off, a late 4th and 17th, a half 7th, an absent 11th, the 12th to
 * decide, the rest on time up to yesterday, the 19th. */
const JUMAS_NOVEMBER: WorkerAttendance = {
  month: "2026-11",
  today: "2026-11-20",
  worker: {
    staff: JUMA,
    display_name: "Juma",
    on_time: 11,
    late: 2,
    half: 1,
    absent: 1,
    needs_review: 1,
  },
  started_on: "2026-09-01",
  left_on: null,
  days: [
    day(1, "off"),
    day(2, "on_time"),
    day(3, "on_time"),
    day(4, "late"),
    day(5, "on_time"),
    day(6, "on_time"),
    day(7, "half"),
    day(8, "off"),
    day(9, "on_time"),
    day(10, "on_time"),
    day(11, "absent"),
    day(12, "needs_review"),
    day(13, "on_time"),
    day(14, "on_time"),
    day(15, "off"),
    day(16, "on_time"),
    day(17, "late"),
    day(18, "on_time"),
    day(19, "on_time"),
  ],
  taps: [],
  yours: false,
  ready_reasons: [],
  ready_add_reasons: [],
  ready_void_reasons: [],
};

/** Each row of the calendar, as its seven places' text: the day's number, its mark for the eye, and the mark in
 * words for a screen reader; or "" for an empty place. */
async function calendar(): Promise<string[][]> {
  const table = await screen.findByRole("table", {
    name: "Siku za Juma, Novemba 2026",
  });
  const [, ...weeks] = within(table).getAllByRole("row");
  return weeks.map((week) =>
    within(week)
      .getAllByRole("cell")
      .map((place) => place.textContent ?? ""),
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(NOW));
  answer("GET", ME, { status: 200, body: MENEJA });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("a worker's month", () => {
  it("shows the month as a calendar, Monday first, each day its mark", async () => {
    answer("GET", JUMAS_MONTH, { status: 200, body: JUMAS_NOVEMBER });

    render(<WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay={null} />);

    // Each place holds its number, its mark (✓ Ch ½ H ! – •), drawn for the eye alone, then the mark in words, for a
    // screen reader.
    expect(await calendar()).toEqual([
      ["", "", "", "", "", "", "1–duka limefungwa"],
      [
        "2✓kwa wakati",
        "3✓kwa wakati",
        "4Chamechelewa",
        "5✓kwa wakati",
        "6✓kwa wakati",
        "7½nusu siku",
        "8–duka limefungwa",
      ],
      [
        "9✓kwa wakati",
        "10✓kwa wakati",
        "11Hhakuja",
        "12!inahitaji uamuzi",
        "13✓kwa wakati",
        "14✓kwa wakati",
        "15–duka limefungwa",
      ],
      // Today, the 20th, is •; the days to come are empty.
      [
        "16✓kwa wakati",
        "17Chamechelewa",
        "18✓kwa wakati",
        "19✓kwa wakati",
        "20•leo",
        "21",
        "22",
      ],
      ["23", "24", "25", "26", "27", "28", "29"],
      ["30", "", "", "", "", "", ""],
    ]);
    // The weekdays over the columns, Monday first.
    const table = screen.getByRole("table", {
      name: "Siku za Juma, Novemba 2026",
    });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((weekday) => weekday.textContent),
    ).toEqual([
      "JtJumatatu",
      "JnJumanne",
      "JtnJumatano",
      "AlAlhamisi",
      "IjIjumaa",
      "JmJumamosi",
      "JpJumapili",
    ]);
  });

  it("marks a decided day by its decision: O office duty, R permission, H a no-show (ATT-6)", async () => {
    // Baba decided the week of the 9th: Monday permission, Tuesday a no-show, Wednesday the bank (office duty), and
    // Thursday's day to decide a full day. Each shows its decision's mark, the book's own answer kept on the day.
    const decided = (
      status: WorkerDay["status"],
      absence: "office_duty" | "permission" | "no_show" | null,
    ): WorkerDay["decision"] => ({
      status: status === "needs_review" ? "on_time" : "absent",
      absence_type: absence,
      fine: "0.00",
      by: "Baba",
      at: "2026-11-20T06:00:00Z",
      reason: "Uamuzi wa mwenye duka",
    });
    const days = JUMAS_NOVEMBER.days.map((each) => {
      const kinds: Record<
        string,
        "office_duty" | "permission" | "no_show" | null
      > = {
        "2026-11-09": "permission",
        "2026-11-10": "no_show",
        "2026-11-11": "office_duty",
        "2026-11-12": null,
      };
      return each.date in kinds
        ? {
            ...each,
            status:
              each.date === "2026-11-12" ? each.status : ("absent" as const),
            decision: decided(each.status, kinds[each.date] ?? null),
          }
        : each;
    });
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: { ...JUMAS_NOVEMBER, days },
    });

    render(<WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay={null} />);

    const weeks = await calendar();
    expect(weeks[2]?.slice(0, 4)).toEqual([
      "9Rruhusa, halipwi",
      "10Hhakuja bila taarifa",
      "11Okazi ya ofisi, analipwa",
      "12✓kwa wakati",
    ]);
    // The key says what O and R mean; H is any absence's.
    const key = screen.getByRole("list", { name: "Maana ya alama" });
    const lines = within(key)
      .getAllByRole("listitem")
      .map((line) => line.textContent);
    expect(lines).toContain("O kazi ya ofisi, analipwa");
    expect(lines).toContain("R ruhusa, halipwi");
  });

  it("names the worker and the month, and counts the month as the server did", async () => {
    answer("GET", JUMAS_MONTH, { status: 200, body: JUMAS_NOVEMBER });

    render(<WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay={null} />);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Juma" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { level: 2, name: "Novemba 2026" }),
    ).toBeTruthy();
    const counts = screen.getByRole("list", { name: "Siku za mwezi huu" });
    expect(
      within(counts)
        .getAllByRole("listitem")
        .map((each) => each.textContent),
    ).toEqual([
      "✓ 11kwa wakati: 11",
      "Ch 2amechelewa: 2",
      "½ 1nusu siku: 1",
      "H 1hakuja: 1",
      "! 1inahitaji uamuzi: 1",
    ]);
    // What each mark means, the shut day's and today's too.
    const key = screen.getByRole("list", { name: "Maana ya alama" });
    expect(
      within(key)
        .getAllByRole("listitem")
        .map((each) => each.textContent),
    ).toEqual([
      "✓ kwa wakati",
      "Ch amechelewa",
      "½ nusu siku",
      "H hakuja",
      "! inahitaji uamuzi",
      // A decided absence's own two (ATT-6); a no-show is H, as any absence.
      "O kazi ya ofisi, analipwa",
      "R ruhusa, halipwi",
      "– duka limefungwa",
      "• leo",
      "+ ina Ingia au Toka, haihesabiwi",
    ]);
  });

  it("asks the server for the worker and the month in the address", async () => {
    answer("GET", JUMAS_MONTH, { status: 200, body: JUMAS_NOVEMBER });

    render(<WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay={null} />);

    await calendar();
    const asked = sent.filter(
      (request) => new URL(request.url).pathname === JUMAS_MONTH,
    );
    expect(
      asked.map((request) => new URL(request.url).searchParams.get("month")),
    ).toEqual(["2026-11"]);
  });

  it("opens this month on the shop's clock when the address names none", async () => {
    answer("GET", JUMAS_MONTH, { status: 200, body: JUMAS_NOVEMBER });

    render(<WorkerMonthScreen staff={JUMA} asked="Novemba" askedDay={null} />);

    await calendar();
    const asked = sent.filter(
      (request) => new URL(request.url).pathname === JUMAS_MONTH,
    );
    expect(new URL(asked[0]?.url ?? "").searchParams.get("month")).toBe(
      "2026-11",
    );
  });

  it("leaves nothing for a day the book doesn't answer, before the first day", async () => {
    // Neema started on Wednesday 11 November: the book answers nothing before it, so those days are empty, not absent.
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: {
        ...JUMAS_NOVEMBER,
        started_on: "2026-11-11",
        days: JUMAS_NOVEMBER.days.filter((each) => each.date >= "2026-11-11"),
      },
    });

    render(<WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay={null} />);

    const weeks = await calendar();
    expect(weeks[1]).toEqual(["2", "3", "4", "5", "6", "7", "8"]);
    expect(weeks[2]?.[2]).toBe("11Hhakuja");
  });

  it("gives no • to today after the worker's last day, nor before their first", async () => {
    // Juma left on Sunday the 15th: the 20th is none of his days, so it is empty, with nothing to open. And a worker
    // whose first day is the 23rd has none on the 20th either.
    for (const [started, left] of [
      ["2026-09-01", "2026-11-15"],
      ["2026-11-23", null],
    ] as const) {
      answer("GET", JUMAS_MONTH, {
        status: 200,
        body: {
          ...JUMAS_NOVEMBER,
          started_on: started,
          left_on: left,
          days: JUMAS_NOVEMBER.days.filter((each) => each.date <= "2026-11-15"),
        },
      });
      const { unmount } = render(
        <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay={null} />,
      );
      const weeks = await calendar();
      expect(weeks[3]?.[4]).toBe("20");
      expect(
        screen.queryByRole("button", { name: /^Ijumaa 20\/11/ }),
      ).toBeNull();
      unmount();
    }
  });

  it("says when the address names no worker, and asks nothing", async () => {
    render(<WorkerMonthScreen staff={null} asked="2026-11" askedDay={null} />);

    expect(
      await screen.findByText("Hakuna mfanyakazi aliyechaguliwa."),
    ).toBeTruthy();
    expect(
      sent.some((request) => request.url.includes("attendance-worker")),
    ).toBe(false);
  });

  it("shows the server's refusal for a worker it doesn't show", async () => {
    // Another shop's worker, or an id no shop has: "not found" alike (03 §5.4).
    answer("GET", JUMAS_MONTH, refusal(404, "not_found"));

    render(<WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay={null} />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
