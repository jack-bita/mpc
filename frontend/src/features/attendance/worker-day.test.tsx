// worker-day.test.tsx — a day of a worker's month, open under their calendar (ATT-12): a day tapped opens and is kept in
// the address; a day to decide says why, each tap with its time, laptop and photo, and what is missing; a late day its
// fine; today its taps as they came; a tap in doubt, an untrusted time, a photo still on its way or removed, and no
// photo with its reason; a day outside the worker's days with their days; and a day the address names with no mark.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer } from "@/test/fake-server";
import { render } from "@/test/render";

import { WorkerMonthScreen } from "./worker-month-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type WorkerAttendance = components["schemas"]["WorkerAttendanceAnswer"];
type WorkerDay = components["schemas"]["WorkerDay"];
type AttendanceTap = components["schemas"]["AttendanceTap"];

const ME = "/api/auth/me/";
const JUMA = "019a8400-0000-7000-8000-000000000007";
const JUMAS_MONTH = `/api/v1/staffpay/attendance-worker/${JUMA}/`;
// Friday 20 November 2026, noon in Arusha.
const NOW = "2026-11-20T09:00:00Z";
const PHOTO = "019a8400-0000-7000-8000-0000000000aa";

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

let taps = 0;

/** A tap of Juma's, from the Dawa laptop, its time trusted and no photo (the demo's reason), unless told otherwise. */
function tap(
  fields: Partial<AttendanceTap> &
    Pick<AttendanceTap, "date" | "kind" | "time">,
): AttendanceTap {
  taps += 1;
  return {
    id: `019a8400-0000-7000-8000-${String(taps).padStart(12, "0")}`,
    laptop_time: fields.time ?? "07:00",
    laptop: "Laptop ya Dawa",
    photo: null,
    no_photo: "demo",
    doubt: null,
    entered: null,
    voided: null,
    ...fields,
  };
}

/** A day as the book kept it. */
function day(
  fields: Partial<WorkerDay> & Pick<WorkerDay, "date" | "status">,
): WorkerDay {
  return {
    // Each day its own id, made from its date, as the server sends one.
    id: `019a8400-0000-7000-9000-${fields.date.replaceAll("-", "").padStart(12, "0")}`,
    reason: null,
    fine: "0.00",
    meal_share: "0.00",
    first_in: null,
    first_out: null,
    decision: null,
    choices: [],
    taps_changed: false,
    ...fields,
  };
}

/** Juma's November, with the days and taps a test gives it. */
function november(
  days: WorkerDay[],
  dayTaps: AttendanceTap[],
  fields: Partial<WorkerAttendance> = {},
): WorkerAttendance {
  return {
    month: "2026-11",
    today: "2026-11-20",
    worker: {
      staff: JUMA,
      display_name: "Juma",
      on_time: 0,
      late: 0,
      half: 0,
      absent: 0,
      needs_review: 0,
    },
    started_on: "2026-09-01",
    left_on: null,
    days,
    taps: dayTaps,
    yours: false,
    closed: false,
    ready_reasons: [],
    ready_add_reasons: [],
    ready_void_reasons: [],
    ...fields,
  };
}

/** The open day, as its words: the section named by its heading. */
async function theDay(name: string): Promise<HTMLElement> {
  return screen.findByRole("region", { name });
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(NOW));
  window.history.replaceState(
    null,
    "",
    `/attendance-month/worker/?staff=${JUMA}&month=2026-11`,
  );
  answer("GET", ME, { status: 200, body: MENEJA });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("a day under the calendar", () => {
  it("opens a day tapped on the calendar, and keeps it in the address", async () => {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({
            date: "2026-11-12",
            status: "needs_review",
            reason: "no_out",
            first_in: "07:20",
          }),
        ],
        [],
      ),
    });
    render(<WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay={null} />);

    const twelfth = await screen.findByRole("button", {
      name: "Alhamisi 12/11: inahitaji uamuzi",
    });
    expect(twelfth.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(twelfth);

    expect(await theDay("Alhamisi 12/11/2026")).toBeTruthy();
    expect(twelfth.getAttribute("aria-pressed")).toBe("true");
    expect(new URL(window.location.href).searchParams.get("day")).toBe(
      "2026-11-12",
    );
    // The open day takes the focus, so a phone shows it, and a screen reader reads it.
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { name: "Alhamisi 12/11/2026" }),
    );
  });

  it("says why a day waits, each tap with its time, laptop and photo, and what is missing", async () => {
    // As on Jack's picture: Thursday 12 November, Ingia at 07:20 with its photo, and no Toka.
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({
            date: "2026-11-12",
            status: "needs_review",
            reason: "no_out",
            first_in: "07:20",
          }),
        ],
        [
          tap({
            date: "2026-11-12",
            kind: "in",
            time: "07:20",
            photo: { id: PHOTO, state: "kept" },
            no_photo: null,
          }),
        ],
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-12" />,
    );

    const open = await theDay("Alhamisi 12/11/2026");
    expect(within(open).getByText("Inahitaji uamuzi")).toBeTruthy();
    expect(within(open).getByText("Kwa nini: hakuna Toka")).toBeTruthy();
    const list = within(open).getByRole("list", {
      name: "Ingia na Toka za siku hii",
    });
    expect(
      within(list).getByText("Ingia 07:20 asubuhi · Laptop ya Dawa"),
    ).toBeTruthy();
    const photo = within(list).getByRole("img", {
      name: "Picha ya Juma, Ingia 07:20 asubuhi",
    });
    // The photo route's own address, on the app's own host: Next.js writes it whole once the picture watches for a
    // failure (onError), so only its path is compared.
    expect(
      new URL(photo.getAttribute("src") ?? "", window.location.href).pathname,
    ).toBe(`/api/v1/control/attachments/${PHOTO}/file/`);
    expect(within(open).getByText("Hakuna Toka.")).toBeTruthy();
  });

  it("says the time a late arrival's reason names", async () => {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({
            date: "2026-11-12",
            status: "needs_review",
            reason: "came_late",
            first_in: "09:10",
            first_out: "18:45",
          }),
        ],
        [
          tap({ date: "2026-11-12", kind: "in", time: "09:10" }),
          tap({ date: "2026-11-12", kind: "out", time: "18:45" }),
        ],
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-12" />,
    );

    const open = await theDay("Alhamisi 12/11/2026");
    expect(
      within(open).getByText("Kwa nini: alifika saa 09:10 asubuhi"),
    ).toBeTruthy();
    expect(
      within(open).getByText("Toka 18:45 jioni · Laptop ya Dawa"),
    ).toBeTruthy();
    // Both taps came: nothing is missing.
    expect(within(open).queryByText("Hakuna Toka.")).toBeNull();
  });

  it("gives a late day its fine, and a tap with no photo its reason", async () => {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({
            date: "2026-11-04",
            status: "late",
            fine: "500.00",
            first_in: "07:50",
            first_out: "18:45",
          }),
        ],
        [
          tap({
            date: "2026-11-04",
            kind: "in",
            time: "07:50",
            no_photo: "blocked",
          }),
          tap({ date: "2026-11-04", kind: "out", time: "18:45" }),
        ],
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-04" />,
    );

    const open = await theDay("Jumatano 04/11/2026");
    expect(
      within(open).getByText(/^Amechelewa · faini TSh\s500$/),
    ).toBeTruthy();
    expect(
      within(open).getByText("Hakuna picha: kamera imezuiwa"),
    ).toBeTruthy();
    expect(
      within(open).getByText("Hakuna picha: hii ni demo, picha haitumwi"),
    ).toBeTruthy();
  });

  it("says their share of the day's meals, on a day with one, decided or not (WAGE-7)", async () => {
    // Monday's 1,000, as the book kept it; Tuesday, decided a full day, the same; Wednesday, when nobody typed any money,
    // says nothing of meals.
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({ date: "2026-11-02", status: "on_time", meal_share: "1000.00" }),
          day({
            date: "2026-11-03",
            status: "needs_review",
            reason: "no_out",
            meal_share: "1000.00",
            decision: {
              status: "on_time",
              absence_type: null,
              fine: "0.00",
              by: "Baba",
              at: "2026-11-04T06:00:00Z",
              reason: "Alisahau kubonyeza Toka",
            },
          }),
          day({ date: "2026-11-04", status: "on_time" }),
        ],
        [],
      ),
    });
    for (const [asked, name, shown] of [
      ["2026-11-02", "Jumatatu 02/11/2026", true],
      ["2026-11-03", "Jumanne 03/11/2026", true],
      ["2026-11-04", "Jumatano 04/11/2026", false],
    ] as const) {
      const page = render(
        <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay={asked} />,
      );
      const open = await theDay(name);
      // Nothing of meals at all on the third, never "Chakula: TSh 0".
      expect(
        within(open)
          .queryAllByText(/^Chakula/)
          .map((line) => line.textContent),
      ).toEqual(shown ? [expect.stringMatching(/^Chakula: TSh\s1,000$/)] : []);
      page.unmount();
    }
  });

  it("shows today's taps as they came, though the day isn't over", async () => {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [],
        [tap({ date: "2026-11-20", kind: "in", time: "07:25" })],
      ),
    });
    render(<WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay={null} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Ijumaa 20/11: leo" }),
    );

    const open = await theDay("Ijumaa 20/11/2026 · leo");
    expect(within(open).getByText("Siku bado haijaisha.")).toBeTruthy();
    expect(
      within(open).getByText("Ingia 07:25 asubuhi · Laptop ya Dawa"),
    ).toBeTruthy();
    // Today isn't over, so no Toka is missing yet, and nothing is decided before it is (ATT-6's card, Done when 6).
    expect(within(open).queryByText("Hakuna Toka.")).toBeNull();
    expect(
      within(open).queryByRole("button", { name: "Amua siku hii" }),
    ).toBeNull();
  });

  it("shows a tap added in the office: who added it, when and why, with no laptop and no photo (ATT-13)", async () => {
    // Juma forgot his Toka, and Baba added it in the office: no laptop made it, so the line names who added it and
    // when, not a laptop; its time is the one Baba typed, trusted.
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({
            date: "2026-11-12",
            status: "on_time",
            first_in: "07:20",
            first_out: "18:45",
          }),
        ],
        [
          tap({ date: "2026-11-12", kind: "in", time: "07:20" }),
          tap({
            date: "2026-11-12",
            kind: "out",
            time: "18:45",
            laptop: null,
            laptop_time: null,
            no_photo: "entered",
            entered: {
              by: "Baba",
              at: "2026-11-12T16:00:00Z",
              reason: "Alisahau kubonyeza Toka",
            },
          }),
        ],
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-12" />,
    );

    const open = await theDay("Alhamisi 12/11/2026");
    expect(
      within(open).getByText(
        "Toka 18:45 jioni · imeongezwa na Baba, 12/11/2026",
      ),
    ).toBeTruthy();
    expect(
      within(open).getByText("Sababu: Alisahau kubonyeza Toka"),
    ).toBeTruthy();
    expect(
      within(open).getByText("Hakuna picha: imeongezwa ofisini"),
    ).toBeTruthy();
    // The laptop's tap beside it keeps its laptop.
    expect(
      within(open).getByText("Ingia 07:20 asubuhi · Laptop ya Dawa"),
    ).toBeTruthy();
  });

  it("says a ready reason in words on the demo, for a tap added or crossed out (ATT-13)", async () => {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [day({ date: "2026-11-12", status: "on_time", first_in: "07:20" })],
        [
          tap({
            date: "2026-11-12",
            kind: "in",
            time: "07:20",
            voided: {
              by: "Meneja",
              at: "2026-11-12T16:00:00Z",
              reason: "wrong_tap",
            },
          }),
          tap({
            date: "2026-11-12",
            kind: "in",
            time: "07:20",
            laptop: null,
            laptop_time: null,
            no_photo: "entered",
            entered: {
              by: "Meneja",
              at: "2026-11-12T16:01:00Z",
              reason: "forgot_tap",
            },
          }),
        ],
        {
          ready_add_reasons: ["forgot_tap"],
          ready_void_reasons: ["wrong_tap"],
        },
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-12" />,
    );

    const open = await theDay("Alhamisi 12/11/2026");
    expect(
      within(open).getByText(
        "Imebatilishwa na Meneja, 12/11/2026 · Sababu: Alibonyeza kwa makosa",
      ),
    ).toBeTruthy();
    expect(within(open).getByText("Sababu: Alisahau kubonyeza")).toBeTruthy();
  });

  it("offers no Ongeza on a day the book keeps nothing for, as attendance was off (ATT-13's review)", async () => {
    // The owner switched attendance on from the 13th: the book keeps no 12th, so a tap there would count nothing.
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [day({ date: "2026-11-13", status: "absent" })],
        [
          tap({
            date: "2026-11-12",
            kind: "in",
            time: "07:20",
          }),
        ],
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-12" />,
    );

    const open = await theDay("Alhamisi 12/11/2026");
    expect(
      within(open).queryByRole("button", { name: "Ongeza Ingia au Toka" }),
    ).toBeNull();
  });

  it("offers Ongeza today, which the book keeps once it is over (ATT-13)", async () => {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [],
        [tap({ date: "2026-11-20", kind: "in", time: "07:20" })],
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-20" />,
    );

    const open = await theDay("Ijumaa 20/11/2026 · leo");
    expect(
      within(open).getByRole("button", { name: "Ongeza Ingia au Toka" }),
    ).toBeTruthy();
  });

  it("offers Ongeza Ingia au Toka on a working day, which opens its sheet over the day (ATT-13)", async () => {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({
            date: "2026-11-12",
            status: "needs_review",
            reason: "no_out",
            first_in: "07:20",
          }),
        ],
        [tap({ date: "2026-11-12", kind: "in", time: "07:20" })],
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-12" />,
    );

    const open = await theDay("Alhamisi 12/11/2026");
    fireEvent.click(
      within(open).getByRole("button", { name: "Ongeza Ingia au Toka" }),
    );
    const sheet = await screen.findByRole("dialog", {
      name: "Ongeza Ingia au Toka ya Juma",
    });
    expect(sheet.textContent).toContain("Alhamisi 12/11/2026");
  });

  it.each([
    ["a Sunday", "2026-11-15", "Jumapili 15/11/2026", {}],
    [
      "a day before the job's first",
      "2026-11-12",
      "Alhamisi 12/11/2026",
      { started_on: "2026-11-13" },
    ],
    ["one's own month", "2026-11-12", "Alhamisi 12/11/2026", { yours: true }],
    [
      "a day after the job's last",
      "2026-11-12",
      "Alhamisi 12/11/2026",
      { left_on: "2026-11-11" },
    ],
  ] as const)(
    "offers no Ongeza on %s (ATT-13)",
    async (_, date, name, fields) => {
      answer("GET", JUMAS_MONTH, {
        status: 200,
        body: november(
          [day({ date, status: date === "2026-11-15" ? "off" : "absent" })],
          [],
          fields,
        ),
      });
      render(
        <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay={date} />,
      );

      const open = await theDay(name);
      expect(
        within(open).queryByRole("button", { name: "Ongeza Ingia au Toka" }),
      ).toBeNull();
    },
  );

  it("shows a crossed-out tap struck through, with who, when and why, and counts the day without it (ATT-13)", async () => {
    // Juma's 10:00 Toka was crossed out by Baba: it stays on the day, struck through (A2), counts for nothing, so the day
    // has an Ingia and no Toka; and it offers no Batilisha of its own, as it is never brought back.
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({
            date: "2026-11-12",
            status: "needs_review",
            reason: "no_out",
            first_in: "07:20",
          }),
        ],
        [
          tap({ date: "2026-11-12", kind: "in", time: "07:20" }),
          tap({
            date: "2026-11-12",
            kind: "out",
            time: "10:00",
            voided: {
              by: "Baba",
              at: "2026-11-12T16:00:00Z",
              reason: "Alibonyeza kwa makosa",
            },
          }),
        ],
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-12" />,
    );

    const open = await theDay("Alhamisi 12/11/2026");
    const crossed = within(open).getByText(
      "Toka 10:00 asubuhi · Laptop ya Dawa",
    );
    expect(crossed.tagName).toBe("S");
    expect(
      within(open).getByText(
        "Imebatilishwa na Baba, 12/11/2026 · Sababu: Alibonyeza kwa makosa",
      ),
    ).toBeTruthy();
    expect(within(open).getByText("Hakuna Toka.")).toBeTruthy();
    // One Batilisha: the Ingia's, which counts.
    expect(
      within(open).getAllByRole("button", { name: "Batilisha" }),
    ).toHaveLength(1);
  });

  it("offers Batilisha under a tap, which opens its sheet over the day (ATT-13)", async () => {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({
            date: "2026-11-12",
            status: "needs_review",
            reason: "left_early",
            first_in: "07:20",
            first_out: "10:00",
          }),
        ],
        [
          tap({ date: "2026-11-12", kind: "in", time: "07:20" }),
          tap({ date: "2026-11-12", kind: "out", time: "10:00" }),
        ],
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-12" />,
    );

    const open = await theDay("Alhamisi 12/11/2026");
    const buttons = within(open).getAllByRole("button", { name: "Batilisha" });
    expect(buttons).toHaveLength(2);
    fireEvent.click(buttons[1]!);
    const sheet = await screen.findByRole("dialog", {
      name: "Batilisha Toka ya Juma",
    });
    expect(sheet.textContent).toContain(
      "Alhamisi 12/11/2026 · Toka 10:00 asubuhi",
    );
  });

  it("offers no Batilisha on one's own month (ATT-13)", async () => {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: {
        ...november(
          [day({ date: "2026-11-12", status: "on_time", first_in: "07:20" })],
          [tap({ date: "2026-11-12", kind: "in", time: "07:20" })],
        ),
        yours: true,
      },
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-12" />,
    );

    const open = await theDay("Alhamisi 12/11/2026");
    expect(
      within(open).getByText("Ingia 07:20 asubuhi · Laptop ya Dawa"),
    ).toBeTruthy();
    expect(
      within(open).queryByRole("button", { name: "Batilisha" }),
    ).toBeNull();
  });

  it("says a decided day's taps changed after the decision (Jack: A, ATT-13)", async () => {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({
            date: "2026-11-12",
            status: "needs_review",
            reason: "no_out",
            first_in: "07:20",
            decision: {
              status: "on_time",
              absence_type: null,
              fine: "0.00",
              by: "Baba",
              at: "2026-11-13T06:00:00Z",
              reason: "Alisahau kubonyeza Toka",
            },
            taps_changed: true,
          }),
        ],
        [tap({ date: "2026-11-12", kind: "in", time: "07:20" })],
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-12" />,
    );

    const open = await theDay("Alhamisi 12/11/2026");
    expect(
      within(open).getByText("Ingia au Toka zimebadilika baada ya uamuzi."),
    ).toBeTruthy();
    // The decision stays, as the book never writes over one (ATT-6).
    expect(
      within(open).getByText("Siku kamili · uamuzi wa Baba, 13/11/2026"),
    ).toBeTruthy();
  });

  it("says why a tap is in doubt, and shows an untrusted time as the laptop's", async () => {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({
            date: "2026-11-12",
            status: "needs_review",
            reason: "not_working",
            first_in: "07:20",
          }),
        ],
        [
          tap({
            date: "2026-11-12",
            kind: "in",
            time: "07:20",
            doubt: "not_working",
          }),
          tap({
            date: "2026-11-12",
            kind: "out",
            time: "18:45",
            doubt: "clock_disagrees",
          }),
          tap({
            date: "2026-11-12",
            kind: "out",
            time: null,
            laptop_time: "18:30",
          }),
        ],
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-12" />,
    );

    const open = await theDay("Alhamisi 12/11/2026");
    expect(
      within(open).getByText("Shaka: alikuwa amesimamishwa au ameondoka"),
    ).toBeTruthy();
    // The other doubt, in words of its own: never "Shaka: saa yake ina shaka".
    expect(
      within(open).getByText("Shaka: huenda saa ya kompyuta ilibadilishwa"),
    ).toBeTruthy();
    expect(
      within(open).getByText(
        "Toka 18:30 jioni (saa ya kompyuta, haiaminiki) · Laptop ya Dawa",
      ),
    ).toBeTruthy();
  });

  it("says so when a kept photo can't be opened, never a broken picture", async () => {
    // The answer says the photo is kept, but the browser can't open it now: the phone went offline, or the login
    // ended while the page was open, and the photo route refused.
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({
            date: "2026-11-02",
            status: "on_time",
            first_in: "07:20",
            first_out: "18:45",
          }),
        ],
        [
          tap({
            date: "2026-11-02",
            kind: "in",
            time: "07:20",
            photo: { id: PHOTO, state: "kept" },
            no_photo: null,
          }),
        ],
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-02" />,
    );

    const open = await theDay("Jumatatu 02/11/2026");
    fireEvent.error(within(open).getByRole("img"));

    expect(
      await within(open).findByText("Picha haikufunguka. Jaribu tena baadaye."),
    ).toBeTruthy();
    expect(within(open).queryByRole("img")).toBeNull();
  });

  it("says a photo hasn't come yet, or was removed, never a broken picture", async () => {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({
            date: "2026-11-02",
            status: "on_time",
            first_in: "07:20",
            first_out: "18:45",
          }),
        ],
        [
          tap({
            date: "2026-11-02",
            kind: "in",
            time: "07:20",
            photo: { id: PHOTO, state: "waiting" },
            no_photo: null,
          }),
          tap({
            date: "2026-11-02",
            kind: "out",
            time: "18:45",
            photo: { id: PHOTO, state: "removed" },
            no_photo: null,
          }),
        ],
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-02" />,
    );

    const open = await theDay("Jumatatu 02/11/2026");
    expect(within(open).getByText("Picha bado haijafika.")).toBeTruthy();
    expect(within(open).getByText("Picha imeondolewa.")).toBeTruthy();
    expect(within(open).queryByRole("img")).toBeNull();
  });

  it("says a working day with no tap had none, and a shut day nothing more", async () => {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({ date: "2026-11-11", status: "absent" }),
          day({ date: "2026-11-15", status: "off" }),
        ],
        [],
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-11" />,
    );

    expect(
      within(await theDay("Jumatano 11/11/2026")).getByText(
        "Hakuna Ingia wala Toka siku hii.",
      ),
    ).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: "Jumapili 15/11: duka limefungwa" }),
    );
    const sunday = await theDay("Jumapili 15/11/2026");
    expect(within(sunday).getByText("Duka limefungwa")).toBeTruthy();
    expect(
      within(sunday).queryByText("Hakuna Ingia wala Toka siku hii."),
    ).toBeNull();
  });

  it("gives a day outside the worker's days their first day", async () => {
    // Neema's first day is 10 November, but she tapped on the 9th (ATT-11).
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [
          day({
            date: "2026-11-09",
            status: "needs_review",
            reason: "outside_job",
            first_in: "07:20",
            first_out: "18:45",
          }),
        ],
        [
          tap({ date: "2026-11-09", kind: "in", time: "07:20" }),
          tap({ date: "2026-11-09", kind: "out", time: "18:45" }),
        ],
        { started_on: "2026-11-10" },
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-09" />,
    );

    const open = await theDay("Jumatatu 09/11/2026");
    expect(
      within(open).getByText("Kwa nini: nje ya siku zake za kazi"),
    ).toBeTruthy();
    expect(
      within(open).getByText("Siku zake za kazi: kuanzia 10/11/2026."),
    ).toBeTruthy();
  });

  it("opens a day with taps the book doesn't count, marked +", async () => {
    // Juma's first day is 10 November, but he tapped on Sunday the 8th: the book keeps no Sunday outside a job's days,
    // so the day has no mark of the book's. Its taps are still in reach: + opens them, and the day says it isn't
    // counted.
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [],
        [tap({ date: "2026-11-08", kind: "in", time: "09:00" })],
        { started_on: "2026-11-10" },
      ),
    });
    render(<WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay={null} />);

    fireEvent.click(
      await screen.findByRole("button", {
        name: "Jumapili 08/11: ina Ingia au Toka, haihesabiwi",
      }),
    );

    const open = await theDay("Jumapili 08/11/2026");
    expect(
      within(open).getByText("Siku hii haihesabiwi, lakini ina Ingia au Toka."),
    ).toBeTruthy();
    expect(
      within(open).getByText("Ingia 09:00 asubuhi · Laptop ya Dawa"),
    ).toBeTruthy();
  });

  it("opens nothing for another month's day the address names", async () => {
    // ?month=2026-10&day=2026-11-20: today, but not October's. October's calendar opens no November day under it.
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(
        [],
        [tap({ date: "2026-11-20", kind: "in", time: "07:25" })],
        {
          month: "2026-10",
        },
      ),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-10" askedDay="2026-11-20" />,
    );

    await screen.findByRole("table");
    expect(screen.queryByRole("region")).toBeNull();
  });

  it("opens nothing for a day the address names with no mark", async () => {
    // A day to come: the book answers nothing for it, so there is nothing to open.
    answer("GET", JUMAS_MONTH, { status: 200, body: november([], []) });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-25" />,
    );

    await screen.findByRole("table");
    expect(screen.queryByRole("region")).toBeNull();
  });
});

describe("deciding a day (ATT-6)", () => {
  /** Thursday 12th, in at 07:50 and no Toka, waiting; the server offers the sheet's choices. */
  const waiting = (fields: Partial<WorkerDay> = {}) =>
    day({
      date: "2026-11-12",
      status: "needs_review",
      reason: "no_out",
      first_in: "07:50",
      choices: [
        { choice: "on_time", fine: "0.00" },
        { choice: "late", fine: "500.00" },
        { choice: "half", fine: "500.00" },
        { choice: "office_duty", fine: "0.00" },
        { choice: "permission", fine: "0.00" },
        { choice: "no_show", fine: "0.00" },
      ],
      ...fields,
    });
  const DECIDED: components["schemas"]["DayDecision"] = {
    status: "on_time",
    absence_type: null,
    fine: "0.00",
    by: "Baba",
    at: "2026-11-20T06:00:00Z",
    reason: "Alisahau kubonyeza Toka",
  };

  function openThursday(days: WorkerDay[], fields = {}) {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november(days, [], fields),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-12" />,
    );
  }

  it("offers Amua siku hii where the server offers choices, and opens the sheet over the day", async () => {
    openThursday([waiting()]);
    const thursday = await theDay("Alhamisi 12/11/2026");

    fireEvent.click(
      within(thursday).getByRole("button", { name: "Amua siku hii" }),
    );

    expect(
      screen.getByRole("dialog", { name: "Amua siku ya Juma" }),
    ).toBeTruthy();
    // Ghairi closes it, and the day is as it was.
    fireEvent.click(screen.getByRole("button", { name: "Ghairi" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(within(thursday).getByText("Kwa nini: hakuna Toka")).toBeTruthy();
  });

  it("shows a decision first, who made it and when, its reason, then what the system said (A2)", async () => {
    openThursday([waiting({ decision: DECIDED })]);
    const thursday = await theDay("Alhamisi 12/11/2026");

    expect(thursday.textContent).toContain(
      "Siku kamili · uamuzi wa Baba, 20/11/2026",
    );
    expect(
      within(thursday).getByText("Sababu: Alisahau kubonyeza Toka"),
    ).toBeTruthy();
    expect(
      within(thursday).getByText(
        "Mfumo ulisema: Inahitaji uamuzi · hakuna Toka",
      ),
    ).toBeTruthy();
    // Decided once, it may be decided again.
    expect(
      within(thursday).getByRole("button", { name: "Badilisha uamuzi" }),
    ).toBeTruthy();
    expect(
      within(thursday).queryByRole("button", { name: "Amua siku hii" }),
    ).toBeNull();
  });

  it("says an absence by its kind, and a late decision with its fine", async () => {
    openThursday([
      waiting({
        decision: {
          ...DECIDED,
          status: "absent",
          absence_type: "office_duty",
          reason: "Alienda benki",
        },
      }),
      waiting({
        date: "2026-11-13",
        decision: { ...DECIDED, status: "late", fine: "500.00" },
      }),
    ]);
    const thursday = await theDay("Alhamisi 12/11/2026");
    expect(thursday.textContent).toContain(
      "Kazi ya ofisi · uamuzi wa Baba, 20/11/2026",
    );
    fireEvent.click(
      // Marked by its decision now, late, on the calendar too.
      screen.getByRole("button", { name: "Ijumaa 13/11: amechelewa" }),
    );
    // By its words, as a person reads them: the amount keeps its space unbroken (formatMoney), which getByText reads as
    // a space.
    expect(
      within(await theDay("Ijumaa 13/11/2026")).getByText(
        "Amechelewa · faini TSh 500 · uamuzi wa Baba, 20/11/2026",
      ),
    ).toBeTruthy();
  });

  it("says a demo's ready reason in words", async () => {
    openThursday(
      [waiting({ decision: { ...DECIDED, reason: "forgot_toka" } })],
      {
        ready_reasons: ["forgot_toka", "away_on_work", "owner_allowed"],
      },
    );
    const thursday = await theDay("Alhamisi 12/11/2026");
    expect(
      within(thursday).getByText("Sababu: Alisahau kubonyeza Toka"),
    ).toBeTruthy();
  });

  it("offers nothing on the viewer's own month, and says it is not theirs to decide", async () => {
    // Meneja opens his own month: the server sends no choices, and says it is his.
    openThursday([waiting({ choices: [] })], { yours: true });
    const thursday = await theDay("Alhamisi 12/11/2026");
    expect(within(thursday).queryByRole("button")).toBeNull();
    expect(
      within(thursday).getByText("Huwezi kuamua siku zako mwenyewe."),
    ).toBeTruthy();
  });

  it("offers nothing on a day the shop was shut", async () => {
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november([day({ date: "2026-11-15", status: "off" })], []),
    });
    render(
      <WorkerMonthScreen staff={JUMA} asked="2026-11" askedDay="2026-11-15" />,
    );
    const sunday = await theDay("Jumapili 15/11/2026");
    expect(within(sunday).queryByRole("button")).toBeNull();
  });

  it("shows the decision on the day as soon as the sheet saves it", async () => {
    openThursday([waiting()]);
    answer("POST", `/api/v1/staffpay/attendance-days/${waiting().id}/decide/`, {
      status: 200,
      body: DECIDED,
    });
    const thursday = await theDay("Alhamisi 12/11/2026");

    fireEvent.click(
      within(thursday).getByRole("button", { name: "Amua siku hii" }),
    );
    const sheet = screen.getByRole("dialog");
    fireEvent.click(within(sheet).getByText("Siku kamili"));
    fireEvent.change(within(sheet).getByLabelText("Sababu"), {
      target: { value: "Alisahau kubonyeza Toka" },
    });
    // The server, once it has kept the decision, answers the month with it, as the page asks for it again.
    answer("GET", JUMAS_MONTH, {
      status: 200,
      body: november([waiting({ decision: DECIDED })], []),
    });
    fireEvent.click(
      within(sheet).getByRole("button", { name: "Hifadhi uamuzi" }),
    );

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(
      await within(thursday).findByText("Sababu: Alisahau kubonyeza Toka"),
    ).toBeTruthy();
  });
});
