// decide-day.test.tsx — Amua siku hii (ATT-6): the sheet that decides a worker's day. Its choices come from the server,
// each with its fine; a choice and a reason go to the day's own route, with the decision the screen showed; an empty
// choice or reason is said at once and nothing is sent; the server's refusals show beside their box, or above the
// buttons, someone deciding it meanwhile among them; on the demo the reason is a ready one to tap; with no network the
// main button is held. The fines are the demo's made-up 500 and 1,500 (rule 10).
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";

import { choiceOf, DecideDay } from "./decide-day";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

// A test that takes the network away puts it back after (navigator.onLine's spy).
afterEach(() => {
  vi.restoreAllMocks();
});

type WorkerAttendance = components["schemas"]["WorkerAttendanceAnswer"];
type WorkerDay = components["schemas"]["WorkerDay"];
type DayDecision = components["schemas"]["DayDecision"];

const JUMA = "019a8400-0000-7000-8000-000000000007";
const THURSDAY = "019a8400-0000-7000-9000-000020261112";
const DECIDE = `/api/v1/staffpay/attendance-days/${THURSDAY}/decide/`;
const NOTHING = "0.00";

/** Juma's Thursday 12 November: in at 07:50, no Toka, waiting; the server offers its six choices. */
const THURSDAYS: WorkerDay = {
  id: THURSDAY,
  date: "2026-11-12",
  status: "needs_review",
  reason: "no_out",
  fine: NOTHING,
  first_in: "07:50",
  first_out: null,
  decision: null,
  taps_changed: false,
  choices: [
    { choice: "on_time", fine: NOTHING },
    { choice: "late", fine: "500.00" },
    { choice: "half", fine: "500.00" },
    { choice: "office_duty", fine: NOTHING },
    { choice: "permission", fine: NOTHING },
    { choice: "no_show", fine: NOTHING },
  ],
};

/** Baba's decision, as the server answers it. */
const DECIDED: DayDecision = {
  status: "on_time",
  absence_type: null,
  fine: NOTHING,
  by: "Baba",
  at: "2026-11-20T06:00:00.123456Z",
  reason: "Alisahau kubonyeza Toka",
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
    days: [THURSDAYS],
    taps: [],
    yours: false,
    ready_reasons: [],
    ready_add_reasons: [],
    ready_void_reasons: [],
    ...fields,
  };
}

function openOn(day: WorkerDay = THURSDAYS, answerFields = {}) {
  const onClose = vi.fn();
  render(
    <DecideDay day={day} answer={month(answerFields)} open onClose={onClose} />,
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

/** The error under a choice or beside a box: the one its aria-describedby names (field.tsx, choice.tsx). */
function errorOf(element: HTMLElement): string {
  const ids = element.getAttribute("aria-describedby")?.split(" ") ?? [];
  const error = ids.find((id) => id.endsWith("-error"));
  return error ? (document.getElementById(error)?.textContent ?? "") : "";
}

const sheet = () => screen.getByRole("dialog", { name: "Amua siku ya Juma" });
const choices = () =>
  within(sheet()).getByRole("radiogroup", { name: "Siku hii ilikuwa" });
const reasonBox = () => within(sheet()).getByLabelText("Sababu");
const save = () => screen.getByRole("button", { name: "Hifadhi uamuzi" });

describe("Amua siku hii", () => {
  it("names the worker and the day, and lists the server's choices, each with its fine", () => {
    openOn();
    expect(sheet().getAttribute("aria-describedby")).toBeTruthy();
    expect(sheet().textContent).toContain(
      "Alhamisi 12/11/2026 · Ingia 07:50 asubuhi",
    );
    expect(within(choices()).getAllByRole("radio")).toHaveLength(6);
    for (const words of [
      "Siku kamili",
      "Amechelewa · faini TSh 500",
      "Nusu siku · faini TSh 500",
      "Kazi ya ofisi · analipwa siku kamili",
      "Ruhusa · halipwi",
      "Hakuja bila taarifa · halipwi",
    ]) {
      expect(within(choices()).getByText(words)).toBeTruthy();
    }
  });

  it("offers no Amechelewa where the server offers none", () => {
    // A Toka alone: nobody knows when Juma came, so the server leaves late out.
    openOn({
      ...THURSDAYS,
      first_in: null,
      choices: THURSDAYS.choices.filter((option) => option.choice !== "late"),
    });
    expect(within(choices()).queryByText(/^Amechelewa/)).toBeNull();
  });

  it("sends the choice and the reason to the day's own route, then closes", async () => {
    answer("POST", DECIDE, { status: 200, body: DECIDED });
    const { onClose } = openOn();

    fireEvent.click(within(choices()).getByText("Siku kamili"));
    fireEvent.change(reasonBox(), {
      target: { value: "Alisahau kubonyeza Toka" },
    });
    fireEvent.click(save());

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(await sentBodies()).toEqual([
      { choice: "on_time", reason: "Alisahau kubonyeza Toka", replaces: null },
    ]);
  });

  it("says a missing choice and an empty reason at once, and sends nothing", async () => {
    openOn();
    fireEvent.change(reasonBox(), { target: { value: "   " } });
    fireEvent.click(save());

    expect(errorOf(choices())).toBe("Chagua uamuzi mmoja.");
    expect(errorOf(reasonBox())).toBe("Andika sababu ya uamuzi huu.");
    expect(await sentBodies()).toEqual([]);
  });

  it("changes a decision with it picked, naming the one it replaces", async () => {
    // Badilisha uamuzi: Baba's full day is picked; he picks a half day, with a new reason.
    answer("POST", DECIDE, {
      status: 200,
      body: { ...DECIDED, status: "half", fine: "500.00" },
    });
    const { onClose } = openOn({ ...THURSDAYS, decision: DECIDED });

    const picked = within(choices())
      .getAllByRole("radio")
      .find((radio) => radio.getAttribute("aria-checked") === "true");
    expect(picked?.closest("label")?.textContent).toContain("Siku kamili");
    fireEvent.click(within(choices()).getByText("Nusu siku · faini TSh 500"));
    fireEvent.change(reasonBox(), {
      target: { value: "Aliondoka saa 7 mchana" },
    });
    fireEvent.click(save());

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(await sentBodies()).toEqual([
      {
        choice: "half",
        reason: "Aliondoka saa 7 mchana",
        replaces: "2026-11-20T06:00:00.123456Z",
      },
    ]);
  });

  it("sends the decision on the screen as it opened, though the month brings a newer one meanwhile", async () => {
    // Baba opens the sheet on Juma's Thursday, decided by nobody. Meneja decides it on his own phone, and Baba's page,
    // asking the month again each minute, hands the open sheet the newer day. Baba's save still says he saw none, so
    // the server refuses it (409) instead of writing over Meneja's decision without a word (ATT-6's review).
    answer("POST", DECIDE, refusal(409, "version_conflict"));
    const onClose = vi.fn();
    const { rerender } = render(
      <DecideDay day={THURSDAYS} answer={month()} open onClose={onClose} />,
    );
    rerender(
      <DecideDay
        day={{ ...THURSDAYS, decision: { ...DECIDED, by: "Meneja" } }}
        answer={month()}
        open
        onClose={onClose}
      />,
    );

    fireEvent.click(within(choices()).getByText("Nusu siku · faini TSh 500"));
    fireEvent.change(reasonBox(), { target: { value: "Aliondoka mchana" } });
    fireEvent.click(save());

    await screen.findByRole("alert");
    expect(await sentBodies()).toEqual([
      { choice: "half", reason: "Aliondoka mchana", replaces: null },
    ]);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("says someone decided it meanwhile above the buttons, and stays open", async () => {
    answer("POST", DECIDE, refusal(409, "version_conflict"));
    const { onClose } = openOn();

    fireEvent.click(within(choices()).getByText("Siku kamili"));
    fireEvent.change(reasonBox(), { target: { value: "Alisahau" } });
    fireEvent.click(save());

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Mtu mwingine amebadilisha hiki wakati huo huo.",
    );
    expect(onClose).not.toHaveBeenCalled();
  });

  it("shows the server's refusal of a choice beside the choices", async () => {
    // A choice the day could no longer take, as a tap arrived meanwhile: beside the choices, in its own words.
    answer(
      "POST",
      DECIDE,
      refusal(400, "invalid", {}, { choice: ["day.choice_not_offered"] }),
    );
    openOn();

    fireEvent.click(within(choices()).getByText("Amechelewa · faini TSh 500"));
    fireEvent.change(reasonBox(), { target: { value: "Alichelewa" } });
    fireEvent.click(save());

    await waitFor(() =>
      expect(errorOf(choices())).toBe("Siku hii haiwezi kuamuliwa hivyo."),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("asks for a ready reason on the demo, and sends its code", async () => {
    answer("POST", DECIDE, {
      status: 200,
      body: { ...DECIDED, reason: "forgot_toka" },
    });
    const { onClose } = openOn(THURSDAYS, {
      ready_reasons: ["forgot_toka", "away_on_work", "owner_allowed"],
    });

    // No box to type in: the three ready reasons, as rows to tap.
    expect(within(sheet()).queryByRole("textbox")).toBeNull();
    const reasons = within(sheet()).getByRole("radiogroup", { name: "Sababu" });
    for (const words of [
      "Alisahau kubonyeza Toka",
      "Alikuwa kazini nje",
      "Ameruhusiwa na mwenye duka",
    ]) {
      expect(within(reasons).getByText(words)).toBeTruthy();
    }
    fireEvent.click(within(choices()).getByText("Siku kamili"));
    fireEvent.click(within(reasons).getByText("Alisahau kubonyeza Toka"));
    fireEvent.click(save());

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(await sentBodies()).toEqual([
      { choice: "on_time", reason: "forgot_toka", replaces: null },
    ]);
  });

  it("holds the main button with no network, so nothing waits unsent", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    openOn();
    expect((save() as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("choiceOf", () => {
  it("picks the sheet's choice a decision was made with: an absence by its kind", () => {
    expect(choiceOf(null)).toBeNull();
    expect(choiceOf(DECIDED)).toBe("on_time");
    expect(
      choiceOf({ ...DECIDED, status: "absent", absence_type: "office_duty" }),
    ).toBe("office_duty");
  });
});
