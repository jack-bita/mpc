// add-tap.test.tsx — Ongeza Ingia au Toka (ATT-13): the sheet that adds a tap a worker forgot. It names whose and the
// day; picks Toka on a day with an Ingia, Ingia on one with none; sends the kind, the minute and the reason to the
// taps' route with the worker, the day and an id made once, so a try again adds one tap; an empty time or reason is
// said at once and nothing is sent; the server's refusals show beside their box, or above the buttons; on the demo the
// reason is the ready one to tap; with no network the main button is held. Fake people and times.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { answer, refusal, sent } from "@/test/fake-server";
import { MealMoneyAsked, mealMoneyIsAnswered } from "@/test/meals";
import { PayAsked, payIsAnswered } from "@/test/pay";
import { render } from "@/test/render";

import { AddTap } from "./add-tap";
import type { AttendanceTap, WorkerAttendance } from "./worker-month";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

// A test that takes the network away puts it back after (navigator.onLine's spy).
afterEach(() => {
  vi.restoreAllMocks();
});

const JUMA = "019a8400-0000-7000-8000-000000000007";
const TAPS = "/api/v1/staffpay/attendance-taps/";
const THURSDAY = "2026-11-12";

/** Juma's Ingia at 07:20 on Thursday 12 November, from the Dawa laptop. */
const INGIA: AttendanceTap = {
  id: "019a8400-0000-7000-8000-000000000101",
  date: THURSDAY,
  kind: "in",
  time: "07:20",
  laptop_time: "07:20",
  laptop: "Laptop ya Dawa",
  photo: null,
  no_photo: "demo",
  doubt: null,
  entered: null,
  voided: null,
};

/** The Toka Baba adds, as the server answers it. */
const ADDED: AttendanceTap = {
  id: "019a8400-0000-7000-8000-000000000102",
  date: THURSDAY,
  kind: "out",
  time: "18:45",
  laptop_time: null,
  laptop: null,
  photo: null,
  no_photo: "entered",
  doubt: null,
  entered: {
    by: "Baba",
    at: "2026-11-12T16:00:00.123456Z",
    reason: "Alisahau kubonyeza Toka",
  },
  voided: null,
};

function month(fields: Partial<WorkerAttendance> = {}): WorkerAttendance {
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
      needs_review: 1,
    },
    started_on: "2026-09-01",
    left_on: null,
    days: [],
    taps: [INGIA],
    yours: false,
    closed: false,
    ready_reasons: [],
    ready_add_reasons: [],
    ready_void_reasons: [],
    ...fields,
  };
}

function openOn(answerFields: Partial<WorkerAttendance> = {}) {
  const onClose = vi.fn();
  render(
    <AddTap day={THURSDAY} answer={month(answerFields)} onClose={onClose} />,
  );
  return { onClose };
}

/** What the app sent, each as the server would read it. */
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
  screen.getByRole("dialog", { name: "Ongeza Ingia au Toka ya Juma" });
const kinds = () =>
  within(sheet()).getByRole("radiogroup", { name: "Ingia au Toka" });
/** Whether Ingia or Toka is picked, as the radio says it (choice.test.tsx). */
const picked = (name: string) =>
  within(kinds()).getByRole("radio", { name }).getAttribute("aria-checked");
const timeBox = () => within(sheet()).getByLabelText("Saa");
const reasonBox = () => within(sheet()).getByLabelText("Sababu");
const add = () => within(sheet()).getByRole("button", { name: "Ongeza" });

function fill(time: string, reason: string) {
  fireEvent.change(timeBox(), { target: { value: time } });
  fireEvent.change(reasonBox(), { target: { value: reason } });
}

describe("Ongeza Ingia au Toka", () => {
  it("names whose and the day, and picks Toka on a day with an Ingia", () => {
    openOn();
    expect(sheet().textContent).toContain("Alhamisi 12/11/2026");
    expect(picked("Toka")).toBe("true");
    expect(picked("Ingia")).toBe("false");
  });

  it("picks Ingia on a day with none, a crossed-out one counting for nothing", () => {
    openOn({
      taps: [
        {
          ...INGIA,
          voided: { by: "Baba", at: "2026-11-12T16:00:00Z", reason: "Makosa" },
        },
      ],
    });
    expect(picked("Ingia")).toBe("true");
  });

  it("sends the kind, the minute and the reason, with the worker, the day and its id, then closes", async () => {
    answer("POST", TAPS, { status: 201, body: ADDED });
    const { onClose } = openOn();

    fill("18:45", "Alisahau kubonyeza Toka");
    fireEvent.click(add());

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const [body] = await sentBodies();
    expect(body).toEqual({
      id: expect.stringMatching(
        /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
      ),
      staff: JUMA,
      date: THURSDAY,
      kind: "out",
      time: "18:45",
      reason: "Alisahau kubonyeza Toka",
    });
  });

  it("asks the meal money and the pay again, as the date is split again with the tap (WAGE-7, WAGE-2)", async () => {
    answer("POST", TAPS, { status: 201, body: ADDED });
    const asked = mealMoneyIsAnswered();
    const payAsked = payIsAnswered();
    render(
      <>
        <MealMoneyAsked />
        <PayAsked />
        <AddTap day={THURSDAY} answer={month()} onClose={vi.fn()} />
      </>,
    );
    await waitFor(() => expect([asked(), payAsked()]).toEqual([1, [1, 1]]));

    fill("18:45", "Alisahau kubonyeza Toka");
    fireEvent.click(add());

    await waitFor(() => expect([asked(), payAsked()]).toEqual([2, [2, 2]]));
  });

  it("asks the pay again when its answer was lost, as the tap may have been added (WAGE-2)", async () => {
    answer("POST", TAPS, refusal(503, "unavailable"));
    const payAsked = payIsAnswered();
    render(
      <>
        <PayAsked />
        <AddTap day={THURSDAY} answer={month()} onClose={vi.fn()} />
      </>,
    );
    await waitFor(() => expect(payAsked()).toEqual([1, 1]));

    fill("18:45", "Alisahau kubonyeza Toka");
    fireEvent.click(add());

    await waitFor(() => expect(payAsked()).toEqual([2, 2]));
  });

  it("sends the same id on a try again, so the tap is added once", async () => {
    // The first answer is lost on the way: the person taps Ongeza again, and the server answers the tap it made.
    answer("POST", TAPS, refusal(503, "unavailable"));
    const { onClose } = openOn();
    fill("18:45", "Alisahau kubonyeza Toka");
    fireEvent.click(add());
    await screen.findByRole("alert");

    answer("POST", TAPS, { status: 201, body: ADDED });
    fireEvent.click(add());

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const [first, second] = await sentBodies();
    expect(second?.id).toBe(first?.id);
  });

  it("says the minute back as the day will show it, with its part of the day (ATT-13's review)", () => {
    // A phone's own time box may show AM/PM, so 06:45 could be picked for the evening: the hint says the tap back in
    // the app's own words, 24 hours with asubuhi or jioni, before Ongeza.
    openOn();
    const box = timeBox();
    expect(within(sheet()).getByText("Saa ya duka, kama 18:45.")).toBeTruthy();
    fireEvent.change(box, { target: { value: "06:45" } });
    expect(
      within(sheet()).getByText("Itahifadhiwa kama: Toka 06:45 asubuhi"),
    ).toBeTruthy();
    fireEvent.click(within(kinds()).getByText("Ingia"));
    fireEvent.change(box, { target: { value: "18:45" } });
    expect(
      within(sheet()).getByText("Itahifadhiwa kama: Ingia 18:45 jioni"),
    ).toBeTruthy();
  });

  it("says an empty time and an empty reason at once, and sends nothing", async () => {
    const { onClose } = openOn();

    fireEvent.change(reasonBox(), { target: { value: "  " } });
    fireEvent.click(add());

    await waitFor(() => expect(errorOf(timeBox())).toBe("Andika saa."));
    expect(errorOf(reasonBox())).toBe("Andika sababu.");
    expect(sent).toHaveLength(0);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("shows a minute still to come beside the time", async () => {
    answer(
      "POST",
      TAPS,
      refusal(400, "invalid", {}, { time: ["tap.in_future"] }),
    );
    openOn();

    fill("23:59", "Alisahau kubonyeza Toka");
    fireEvent.click(add());

    await waitFor(() =>
      expect(errorOf(timeBox())).toBe("Saa hii bado haijafika."),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says a day that isn't one of the job's above the buttons, and stays open", async () => {
    answer("POST", TAPS, refusal(400, "tap.not_working_day"));
    const { onClose } = openOn();

    fill("18:45", "Alisahau kubonyeza Toka");
    fireEvent.click(add());

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Siku hii si siku ya kazi ya mfanyakazi huyu.",
    );
    expect(onClose).not.toHaveBeenCalled();
  });

  it("asks for the ready reason on the demo, and sends its code", async () => {
    answer("POST", TAPS, {
      status: 201,
      body: { ...ADDED, entered: { ...ADDED.entered, reason: "forgot_tap" } },
    });
    const { onClose } = openOn({ ready_add_reasons: ["forgot_tap"] });

    // No box to type a reason in: the ready reason, as a row to tap.
    const reasons = within(sheet()).getByRole("radiogroup", { name: "Sababu" });
    fireEvent.change(timeBox(), { target: { value: "18:45" } });
    fireEvent.click(within(reasons).getByText("Alisahau kubonyeza"));
    fireEvent.click(add());

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const [body] = await sentBodies();
    expect(body?.reason).toBe("forgot_tap");
  });

  it("holds the main button with no network, so nothing waits unsent", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    openOn();
    expect((add() as HTMLButtonElement).disabled).toBe(true);
  });
});
