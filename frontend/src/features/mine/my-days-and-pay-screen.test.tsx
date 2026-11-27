// my-days-and-pay-screen.test.tsx — Siku na malipo yangu, a worker's own month (WAGE-4): asked of the worker's own route
// for this month, with no id; the manager's calendar of them, counts and marks; a day tapped opens in a sheet, closed by
// Funga, the keyboard back on the day; ‹ stops at the job's first month; a refusal says why; and nothing of it stays in
// the store once the page is gone.
import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import type { components } from "@/api/schema";
import { DAWA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";

import { MINE } from "./mine";
import { MyDaysAndPayScreen } from "./my-days-and-pay-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type OwnAttendance = components["schemas"]["OwnAttendanceAnswer"];
type OwnDay = components["schemas"]["OwnDay"];

const ME = "/api/auth/me/";
const MY_DAYS = "/api/v1/staffpay/mine/attendance/";
// Friday 27 November 2026, noon in Arusha.
const NOW = "2026-11-27T09:00:00Z";

/** Asha, a seller at the Dawa laptop, who holds no key to anyone's attendance: her own needs none. */
const ASHA: components["schemas"]["WhoIsHere"] = {
  ...whoIsHere([{ side: DAWA, permissions: ["sales.create"] }]),
  staff: {
    id: "019a8400-0000-7000-8000-000000000a5a",
    display_name: "Asha",
    job_title: "Muuzaji",
  },
};

function day(date: number, status: OwnDay["status"]): OwnDay {
  return {
    date: `2026-11-${String(date).padStart(2, "0")}`,
    status,
    reason: null,
    fine: status === "late" ? "500.00" : "0.00",
    meal_share: "0.00",
    first_in: null,
    first_out: null,
    decision: null,
  };
}

/** Asha's November as Jack drew it: Sundays off, late on the 4th, on time on the 2nd and 3rd; she started in
 * September. Shortened to the first week, which is all these tests read. */
const ASHAS_NOVEMBER: OwnAttendance = {
  month: "2026-11",
  today: "2026-11-27",
  worker: {
    staff: ASHA.staff.id,
    display_name: "Asha",
    on_time: 2,
    late: 1,
    half: 0,
    absent: 0,
    needs_review: 0,
  },
  started_on: "2026-09-01",
  left_on: null,
  days: [
    day(1, "off"),
    day(2, "on_time"),
    day(3, "on_time"),
    { ...day(4, "late"), meal_share: "1500.00", first_in: "08:20" },
  ],
  taps: [
    {
      id: "019a8400-0000-7000-8000-0000000000e1",
      date: "2026-11-04",
      kind: "in",
      time: "08:20",
      laptop_time: null,
      laptop: "Laptop ya Dawa",
      entered: null,
      voided: null,
      after_approval: false,
    },
    {
      id: "019a8400-0000-7000-8000-0000000000e2",
      date: "2026-11-04",
      kind: "out",
      time: "18:05",
      laptop_time: null,
      laptop: "Laptop ya Dawa",
      entered: null,
      voided: null,
      after_approval: false,
    },
  ],
  ready_reasons: [],
  ready_add_reasons: [],
  ready_void_reasons: [],
};

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(NOW));
  answer("GET", ME, { status: 200, body: ASHA });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("my days and pay", () => {
  it("asks for this month of the worker's own, with no id, and shows its calendar", async () => {
    answer("GET", MY_DAYS, { status: 200, body: ASHAS_NOVEMBER });

    render(<MyDaysAndPayScreen />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Siku na malipo yangu" }),
    ).toBeDefined();
    const table = await screen.findByRole("table", {
      name: "Siku za Asha, Novemba 2026",
    });
    const [, firstWeek] = within(table).getAllByRole("row");
    expect(
      within(firstWeek as HTMLElement)
        .getAllByRole("cell")
        .map((place) => place.textContent),
    ).toEqual(["", "", "", "", "", "", "1–duka limefungwa"]);
    // Her own counts, as the server counted them.
    expect(
      screen.getByRole("list", { name: "Siku za mwezi huu" }).textContent,
    ).toContain("✓ 2");
    // The month alone in the address: never a worker's id, which the route doesn't read.
    const asked = sent.filter((request) => request.url.includes(MY_DAYS));
    expect(asked.length).toBeGreaterThan(0);
    expect(
      asked.every(
        (request) => new URL(request.url).search === "?month=2026-11",
      ),
    ).toBe(true);
  });

  it("opens a tapped day in a sheet with only Funga, and gives the keyboard back to the day", async () => {
    answer("GET", MY_DAYS, { status: 200, body: ASHAS_NOVEMBER });
    render(<MyDaysAndPayScreen />);

    const fourth = await screen.findByRole("button", {
      name: "Jumatano 04/11: amechelewa",
    });
    // A finger's tap focuses the button as it clicks it; jsdom's click alone moves no focus.
    fourth.focus();
    fireEvent.click(fourth);

    const sheet = await screen.findByRole("dialog", {
      name: "Jumatano 04/11/2026",
    });
    // Money as Intl writes it, with a space that never breaks after TSh: \s matches it.
    expect(sheet.textContent).toMatch(/Amechelewa · faini TSh\s500/);
    expect(sheet.textContent).toMatch(/Chakula: TSh\s1,500/);
    const taps = within(sheet).getByRole("list", {
      name: "Ingia na Toka za siku hii",
    });
    expect(
      within(taps)
        .getAllByRole("listitem")
        .map((tap) => tap.textContent),
    ).toEqual([
      "Ingia 08:20 asubuhi · Laptop ya Dawa",
      "Toka 18:05 jioni · Laptop ya Dawa",
    ]);
    // Only to read: the one button closes it.
    expect(
      within(sheet)
        .getAllByRole("button")
        .map((button) => button.textContent),
    ).toEqual(["Funga"]);

    fireEvent.click(within(sheet).getByRole("button", { name: "Funga" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(fourth));
  });

  it("stops ‹ at the month the job began", async () => {
    answer("GET", MY_DAYS, {
      status: 200,
      body: { ...ASHAS_NOVEMBER, started_on: "2026-11-02" },
    });
    render(<MyDaysAndPayScreen />);
    await screen.findByRole("table");

    const before = screen.getByRole("button", { name: "Mwezi uliopita" });
    // Greyed out, kept in the Tab order, as › is on this month.
    expect(before.getAttribute("aria-disabled")).toBe("true");
    expect(
      screen
        .getByRole("button", { name: "Mwezi unaofuata" })
        .getAttribute("aria-disabled"),
    ).toBe("true");
  });

  it("says why a month is refused", async () => {
    answer("GET", MY_DAYS, refusal(400, "mine.before_job"));
    render(<MyDaysAndPayScreen />);

    expect(
      await screen.findByText("Ulikuwa bado hujaanza kazi mwezi huu."),
    ).toBeDefined();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("keeps nothing of the worker's month in the store once the page is gone", async () => {
    answer("GET", MY_DAYS, { status: 200, body: ASHAS_NOVEMBER });
    const store = makeQueryClient();
    const { unmount } = render(
      <QueryClientProvider client={store}>
        <MyDaysAndPayScreen />
      </QueryClientProvider>,
    );
    await screen.findByRole("table");
    expect(store.getQueryCache().findAll({ queryKey: MINE })).toHaveLength(1);

    unmount();

    // The next person at the laptop finds none of it, not even in the tab's memory (gcTime 0, mine.ts).
    await waitFor(() =>
      expect(store.getQueryCache().findAll({ queryKey: MINE })).toHaveLength(0),
    );
  });
});
