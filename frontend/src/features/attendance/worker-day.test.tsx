// worker-day.test.tsx — a day of a worker's month, open under their calendar (ATT-12): a day tapped opens and is kept in
// the address; a day to decide says why, each tap with its time, laptop and photo, and what is missing; a late day its
// fine; today its taps as they came; a tap in doubt, an untrusted time, a photo still on its way or removed, and no
// photo with its reason; a day outside the worker's days with their days; and a day the address names with no mark.
import { fireEvent, screen, within } from "@testing-library/react";
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
    ...fields,
  };
}

/** A day as the book kept it. */
function day(
  fields: Partial<WorkerDay> & Pick<WorkerDay, "date" | "status">,
): WorkerDay {
  return {
    reason: null,
    fine: "0.00",
    first_in: null,
    first_out: null,
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
    // Today isn't over, so no Toka is missing yet.
    expect(within(open).queryByText("Hakuna Toka.")).toBeNull();
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
