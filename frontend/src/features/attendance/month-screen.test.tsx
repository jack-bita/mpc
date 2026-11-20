// month-screen.test.tsx — Mahudhurio ya mwezi (ATT-5): a line per worker paid by the day with the month's counts and
// what each mark means; the month moved back and forward, never past this one, and kept in the address; how far this
// month's counts reach; and the line when nobody is listed.
import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";

import { MonthScreen } from "./month-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type AttendanceMonth = components["schemas"]["AttendanceMonthAnswer"];
type WorkerMonth = components["schemas"]["WorkerMonth"];

const ME = "/api/auth/me/";
const MONTH = "/api/v1/staffpay/attendance-month/";
// Friday 20 November 2026, noon in Arusha: this month is November, and its counts reach Thursday the 19th.
const NOW = "2026-11-20T09:00:00Z";

/** Neema, a manager: attendance.manage on the whole shop, as the server counts it on every side too. */
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

let made = 0;

/** A worker's line: Asha's, made up, unless told otherwise. Each its own job's id. */
function line(fields: Partial<WorkerMonth> = {}): WorkerMonth {
  made += 1;
  return {
    staff: `019a8400-0000-7000-8000-${String(made).padStart(12, "0")}`,
    display_name: "Asha",
    on_time: 15,
    late: 2,
    half: 1,
    absent: 0,
    needs_review: 0,
    ...fields,
  };
}

/** The month page's answer for `month`, as the server would give it today. */
function monthOf(month: string, workers: WorkerMonth[]): AttendanceMonth {
  return {
    month,
    today: "2026-11-20",
    working_day_over: true,
    workers,
    to_decide: [],
  };
}

/** Meneja is logged in; each month answers with its own lines, or none. */
function theShopHas(months: Record<string, WorkerMonth[]>) {
  answer("GET", ME, { status: 200, body: MENEJA });
  answer("GET", MONTH, (request) => {
    const month = new URL(request.url).searchParams.get("month") ?? "";
    return Response.json(monthOf(month, months[month] ?? []));
  });
}

/** The months the page asked the server for, in order. */
function monthsAsked(): string[] {
  return sent
    .filter((request) => new URL(request.url).pathname === MONTH)
    .map((request) => new URL(request.url).searchParams.get("month") ?? "");
}

/** The table's rows of workers, each as its cells' words: the name, then the five counts. */
async function rows(): Promise<string[][]> {
  const table = await screen.findByRole("table", {
    name: "Siku za kila mfanyakazi",
  });
  const [, ...body] = within(table).getAllByRole("row");
  return body.map((row) =>
    [
      ...within(row).getAllByRole("rowheader"),
      ...within(row).getAllByRole("cell"),
    ].map((cell) => cell.textContent ?? ""),
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(NOW));
  window.history.replaceState(null, "", "/attendance-month/");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("the month page", () => {
  it("opens on this month, a line per worker with the month's counts", async () => {
    theShopHas({
      "2026-11": [
        line({ display_name: "Asha" }),
        line({
          display_name: "Baraka",
          on_time: 17,
          late: 0,
          half: 0,
          absent: 1,
        }),
      ],
    });

    render(<MonthScreen asked={null} />);

    expect(await rows()).toEqual([
      ["Asha", "15", "2", "1", "0", "0"],
      ["Baraka", "17", "0", "0", "1", "0"],
    ]);
    expect(screen.getByRole("heading", { name: "Novemba 2026" })).toBeTruthy();
    expect(monthsAsked()).toEqual(["2026-11"]);
  });

  it("names each count's kind to a screen reader, and says what each mark means", async () => {
    // A column's mark is short for a phone ("Ch"), so its heading also says the kind in words, which a screen reader
    // reads; and under the table, each mark with its meaning, for whoever doesn't know them yet.
    theShopHas({ "2026-11": [line()] });

    render(<MonthScreen asked={null} />);

    const table = await screen.findByRole("table");
    const headings = within(table)
      .getAllByRole("columnheader")
      .map((heading) => heading.textContent);
    expect(headings).toEqual([
      "Mfanyakazi",
      "✓kwa wakati",
      "Chamechelewa",
      "½nusu siku",
      "Hhakuja",
      "!inahitaji uamuzi",
    ]);
    const key = screen.getByRole("list", { name: "Maana ya alama" });
    expect(
      within(key)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([
      "✓ kwa wakati",
      "Ch amechelewa",
      "½ nusu siku",
      "H hakuja",
      "! inahitaji uamuzi",
    ]);
  });

  it("says this month's counts reach yesterday, as no day is counted before it is over", async () => {
    theShopHas({ "2026-11": [line()] });

    render(<MonthScreen asked={null} />);

    expect(await screen.findByText("Hadi jana, 19/11/2026.")).toBeTruthy();
  });

  it("says only that no working day is over yet, on the month's first days (the review)", async () => {
    // 1 December: no day is over, so nobody is listed for want of a day, not of a pay rate. "Hakuna mfanyakazi
    // anayelipwa kwa siku" would be untrue. The same on Monday the 2nd after a Sunday the 1st, which the server says.
    vi.setSystemTime(new Date("2026-12-01T09:00:00Z"));
    answer("GET", ME, { status: 200, body: MENEJA });
    answer("GET", MONTH, {
      status: 200,
      body: {
        ...monthOf("2026-12", []),
        today: "2026-12-01",
        working_day_over: false,
      },
    });

    render(<MonthScreen asked={null} />);

    expect(
      await screen.findByText(
        "Bado hakuna siku ya kazi iliyokwisha mwezi huu.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText(/Hakuna mfanyakazi/)).toBeNull();
    expect(screen.queryByText(/Hadi jana/)).toBeNull();
  });

  it("goes back a month, and forward again, never past this one, keeping the month in the address", async () => {
    // › stays off this month: no day after today is over. The month is in the address, replaced, so the back arrow
    // still leaves the page, and a worker's page (ATT-12) comes back to the same month.
    theShopHas({
      "2026-11": [line({ display_name: "Asha" })],
      "2026-10": [line({ display_name: "Baraka" })],
    });

    render(<MonthScreen asked={null} />);

    await screen.findByRole("heading", { name: "Novemba 2026" });
    expect(
      screen.queryByRole("button", { name: "Mwezi unaofuata" }),
    ).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Mwezi uliopita" }));

    expect(
      await screen.findByRole("heading", { name: "Oktoba 2026" }),
    ).toBeTruthy();
    expect((await rows()).map(([name]) => name)).toEqual(["Baraka"]);
    expect(window.location.search).toBe("?month=2026-10");
    // A month gone by is counted to its end: no "Hadi jana".
    expect(screen.queryByText(/Hadi jana/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Mwezi unaofuata" }));

    await screen.findByRole("heading", { name: "Novemba 2026" });
    expect(window.location.search).toBe("?month=2026-11");
    expect(monthsAsked()).toEqual(["2026-11", "2026-10", "2026-11"]);
  });

  it("goes back across a year's end", async () => {
    theShopHas({});

    render(<MonthScreen asked="2026-01" />);

    await screen.findByRole("heading", { name: "Januari 2026" });
    fireEvent.click(screen.getByRole("button", { name: "Mwezi uliopita" }));

    expect(
      await screen.findByRole("heading", { name: "Desemba 2025" }),
    ).toBeTruthy();
    expect(monthsAsked()).toEqual(["2026-01", "2025-12"]);
  });

  it("opens the month the address names, and this month for one to come or no month at all", async () => {
    theShopHas({});

    const { unmount } = render(<MonthScreen asked="2026-09" />);
    expect(
      await screen.findByRole("heading", { name: "Septemba 2026" }),
    ).toBeTruthy();
    unmount();

    for (const asked of ["2026-12", "2026-13", "Novemba"]) {
      const shown = render(<MonthScreen asked={asked} />);
      expect(
        await screen.findByRole("heading", { name: "Novemba 2026" }),
      ).toBeTruthy();
      shown.unmount();
    }
    expect(monthsAsked()).toEqual(["2026-09", "2026-11", "2026-11", "2026-11"]);
  });

  it("puts the days to decide at the top, above the workers' lines (Jack's picture)", async () => {
    answer("GET", ME, { status: 200, body: MENEJA });
    answer("GET", MONTH, {
      status: 200,
      body: {
        ...monthOf("2026-11", [
          line({ display_name: "Juma", needs_review: 1 }),
        ]),
        to_decide: [
          {
            staff: "019a8400-0000-7000-8000-000000000099",
            display_name: "Juma",
            date: "2026-11-12",
            reason: "no_out",
            first_in: "07:20",
            first_out: null,
          },
        ],
      },
    });

    render(<MonthScreen asked={null} />);

    const table = await screen.findByRole("table");
    const toDecide = screen.getByRole("heading", {
      name: "Zinahitaji uamuzi (1)",
    });
    expect(
      toDecide.compareDocumentPosition(table) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      screen.getByText("Juma · Alhamisi 12/11 · hakuna Toka"),
    ).toBeTruthy();
  });

  it("says so when nobody is paid by the day in the month", async () => {
    // Before the owner gave anyone a daily rate, or a month before attendance was switched on.
    theShopHas({ "2026-11": [] });

    render(<MonthScreen asked={null} />);

    expect(
      await screen.findByText(
        "Hakuna mfanyakazi anayelipwa kwa siku katika mwezi huu.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows the server's refusal to someone without the key, who reached the page by its address", async () => {
    answer("GET", ME, { status: 200, body: whoIsHere([]) });
    answer("GET", MONTH, refusal(403, "permission_denied"));

    render(<MonthScreen asked={null} />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("says to wait while it asks, so the page is never blank", () => {
    answer("GET", ME, () => new Promise<Response>(() => undefined));

    render(<MonthScreen asked={null} />);

    expect(screen.getByText("Subiri kidogo…").getAttribute("role")).toBe(
      "status",
    );
  });
});
