// void-tap.test.tsx — Batilisha (ATT-13): the sheet that crosses out a tap made by mistake. It names whose tap, which
// and on which day; a reason goes to the tap's own route; an empty reason is said at once and nothing is sent; the
// server's refusals show beside the reason, or above the buttons; on the demo the reason is the ready one to tap; with
// no network the main button is held. Fake people and times.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";

import { VoidTap } from "./void-tap";
import type { AttendanceTap, WorkerAttendance } from "./worker-month";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

// A test that takes the network away puts it back after (navigator.onLine's spy).
afterEach(() => {
  vi.restoreAllMocks();
});

const JUMA = "019a8400-0000-7000-8000-000000000007";
const TOKA = "019a8400-0000-7000-8000-000000000101";
const VOID = `/api/v1/staffpay/attendance-taps/${TOKA}/void/`;

/** Juma's Toka at 10:00 on Thursday 12 November, by mistake, from the Dawa laptop. */
const TEN_OCLOCK: AttendanceTap = {
  id: TOKA,
  date: "2026-11-12",
  kind: "out",
  time: "10:00",
  laptop_time: "10:00",
  laptop: "Laptop ya Dawa",
  photo: null,
  no_photo: "demo",
  doubt: null,
  entered: null,
  voided: null,
};

/** The same tap, crossed out by Baba, as the server answers it. */
const CROSSED: AttendanceTap = {
  ...TEN_OCLOCK,
  voided: {
    by: "Baba",
    at: "2026-11-12T16:00:00.123456Z",
    reason: "Alibonyeza kwa makosa",
  },
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
    taps: [TEN_OCLOCK],
    yours: false,
    ready_reasons: [],
    ready_add_reasons: [],
    ready_void_reasons: [],
    ...fields,
  };
}

function openOn(answerFields: Partial<WorkerAttendance> = {}) {
  const onClose = vi.fn();
  render(
    <VoidTap
      tap={TEN_OCLOCK}
      said={{ kind: "Toka", time: "10:00 asubuhi" }}
      answer={month(answerFields)}
      onClose={onClose}
    />,
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
  screen.getByRole("dialog", { name: "Batilisha Toka ya Juma" });
const reasonBox = () => within(sheet()).getByLabelText("Sababu");
const crossOut = () =>
  within(sheet()).getByRole("button", { name: "Batilisha" });

describe("Batilisha", () => {
  it("names whose tap, which, and the day", () => {
    openOn();
    expect(sheet().textContent).toContain(
      "Alhamisi 12/11/2026 · Toka 10:00 asubuhi",
    );
    expect(
      within(sheet()).getByRole("button", { name: "Ghairi" }),
    ).toBeTruthy();
  });

  it("sends the reason to the tap's own route, then closes", async () => {
    answer("POST", VOID, { status: 200, body: CROSSED });
    const { onClose } = openOn();

    fireEvent.change(reasonBox(), {
      target: { value: "Alibonyeza kwa makosa" },
    });
    fireEvent.click(crossOut());

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(await sentBodies()).toEqual([{ reason: "Alibonyeza kwa makosa" }]);
  });

  it("says an empty reason at once, and sends nothing", async () => {
    const { onClose } = openOn();

    fireEvent.change(reasonBox(), { target: { value: "   " } });
    fireEvent.click(crossOut());

    await waitFor(() => expect(errorOf(reasonBox())).toBe("Andika sababu."));
    expect(sent).toHaveLength(0);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("says one's own tap above the buttons, and stays open", async () => {
    // The page offers no button on one's own month; a refusal all the same, from a month open before a change of job.
    answer("POST", VOID, refusal(400, "tap.own"));
    const { onClose } = openOn();

    fireEvent.change(reasonBox(), { target: { value: "Makosa" } });
    fireEvent.click(crossOut());

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Huwezi kurekebisha Ingia au Toka zako mwenyewe.",
    );
    expect(onClose).not.toHaveBeenCalled();
  });

  it("shows the server's refusal of a reason beside its box", async () => {
    answer(
      "POST",
      VOID,
      refusal(400, "invalid", {}, { reason: ["tap.reason_missing"] }),
    );
    openOn();

    fireEvent.change(reasonBox(), { target: { value: "x" } });
    fireEvent.click(crossOut());

    await waitFor(() => expect(errorOf(reasonBox())).toBe("Andika sababu."));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("asks for the ready reason on the demo, and sends its code", async () => {
    answer("POST", VOID, {
      status: 200,
      body: { ...CROSSED, voided: { ...CROSSED.voided!, reason: "wrong_tap" } },
    });
    const { onClose } = openOn({ ready_void_reasons: ["wrong_tap"] });

    // No box to type in: the ready reason, as a row to tap.
    expect(within(sheet()).queryByRole("textbox")).toBeNull();
    const reasons = within(sheet()).getByRole("radiogroup", { name: "Sababu" });
    fireEvent.click(within(reasons).getByText("Alibonyeza kwa makosa"));
    fireEvent.click(crossOut());

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(await sentBodies()).toEqual([{ reason: "wrong_tap" }]);
  });

  it("holds the main button with no network, so nothing waits unsent", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    openOn();
    expect((crossOut() as HTMLButtonElement).disabled).toBe(true);
  });
});
