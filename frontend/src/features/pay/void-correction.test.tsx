// void-correction.test.tsx — Batilisha of a correction on a worker's pay page (WAGE-10): its line opens a sheet with who
// typed it, as Jack drew it (screen 3); crossed out with a reason, it moves under Marekebisho yaliyobatilishwa, struck
// through, with who, when and why; offered only to whoever approves pay, never on their own, and only while the month
// takes one; on the demo, with the ready reason.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { answer, sent } from "@/test/fake-server";
import {
  APPROVER,
  correction,
  OWNER,
  pay,
  payRoute,
  type WorkerPayMonth,
  workerPay,
  workerPayMonth,
} from "@/test/pay";
import { render } from "@/test/render";

import { WorkerPayScreen } from "./worker-pay-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const JUMA = "019a8600-0000-7000-8000-0000000000aa";
const WRONG = correction({ amount: "90000.00" });
const VOID = `/api/v1/staffpay/pay-corrections/${WRONG.id}/void/`;
const LINE = "Marekebisho: Novemba: siku ya 12/11 haikuhesabiwa";
const STRUCK = {
  by: "Baba",
  at: "2026-12-03T07:20:00Z",
  reason: "Kiasi kimekosewa",
};

/** Juma's November with Baba's + 90,000 counting, as `who` sees it; the server crosses it out when asked. */
function withTheWrongOne(
  who = APPROVER,
  fields: Partial<WorkerPayMonth> = {},
  worker: Parameters<typeof workerPay>[0] = {},
) {
  let corrections = [WRONG];
  answer("GET", ME, { status: 200, body: who });
  answer("GET", payRoute(JUMA), () =>
    Response.json(
      workerPayMonth(
        workerPay({
          staff: JUMA,
          pay: pay({
            corrections: corrections[0]?.voided ? "0.00" : "90000.00",
          }),
          ...worker,
        }),
        { corrections, ...fields },
      ),
    ),
  );
  answer("POST", VOID, async (request) => {
    const { reason } = (await request.json()) as { reason: string };
    const struck = { ...WRONG, voided: { ...STRUCK, reason } };
    corrections = [struck];
    return Response.json(struck);
  });
}

function open() {
  return render(<WorkerPayScreen staff={JUMA} asked="2026-11" />);
}

function voidsSent(): Request[] {
  return sent.filter((request) => new URL(request.url).pathname === VOID);
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  // Wednesday 25 November 2026, noon in Arusha.
  vi.setSystemTime(new Date("2026-11-25T09:00:00Z"));
  window.history.replaceState(null, "", "/pay/worker/");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Batilisha of a correction", () => {
  it("opens from its line with who typed it, as Jack drew it", async () => {
    withTheWrongOne();
    open();
    // Still counting, it is a line of the pay, and nothing is crossed out yet.
    const line = await screen.findByRole("button", { name: LINE });
    expect(
      screen.queryByRole("heading", { name: "Marekebisho yaliyobatilishwa" }),
    ).toBeNull();
    fireEvent.click(line);
    const sheet = await screen.findByRole("dialog");

    expect(within(sheet).getByRole("heading").textContent).toBe(
      "Marekebisho ya Juma · + 90,000",
    );
    expect(within(sheet).getByText("Novemba 2026")).toBeTruthy();
    expect(
      within(sheet).getByText("Sababu: Novemba: siku ya 12/11 haikuhesabiwa"),
    ).toBeTruthy();
    expect(
      within(sheet).getByText("Imeandikwa na Baba · 03/12/2026 10:05 asubuhi"),
    ).toBeTruthy();
  });

  it("asks why first, and sends nothing without it", async () => {
    withTheWrongOne();
    open();
    fireEvent.click(await screen.findByRole("button", { name: LINE }));
    const sheet = await screen.findByRole("dialog");
    fireEvent.click(within(sheet).getByRole("button", { name: "Batilisha" }));
    expect(await within(sheet).findByText("Andika sababu.")).toBeTruthy();
    expect(voidsSent()).toHaveLength(0);
  });

  it("crosses it out with its reason, and lands on the struck line, with who, when and why", async () => {
    withTheWrongOne();
    open();
    fireEvent.click(await screen.findByRole("button", { name: LINE }));
    const sheet = await screen.findByRole("dialog");
    fireEvent.change(within(sheet).getByLabelText("Sababu ya kubatilisha"), {
      target: { value: "Kiasi kimekosewa" },
    });
    fireEvent.click(within(sheet).getByRole("button", { name: "Batilisha" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(await voidsSent()[0]?.clone().json()).toEqual({
      reason: "Kiasi kimekosewa",
    });
    const heading = await screen.findByRole("heading", {
      name: "Marekebisho yaliyobatilishwa",
    });
    await waitFor(() =>
      expect(document.activeElement?.contains(heading)).toBe(true),
    );
    const struck = heading.closest("section");
    expect(struck).not.toBeNull();
    expect(within(struck as HTMLElement).getByText(LINE).tagName).toBe("S");
    expect(
      within(struck as HTMLElement).getByText(
        "Imebatilishwa na Baba · 03/12/2026 10:20 asubuhi: Kiasi kimekosewa",
      ),
    ).toBeTruthy();
    // It counts for nothing: no line of it in the pay any more.
    expect(screen.queryByRole("button", { name: LINE })).toBeNull();
  });

  it.each<[string, () => void]>([
    ["to whoever may not approve pay", () => withTheWrongOne(OWNER)],
    ["on one's own pay", () => withTheWrongOne(APPROVER, {}, { own: true })],
    [
      "once its month is approved",
      () => withTheWrongOne(APPROVER, { no_correction: "pay.day_approved" }),
    ],
    [
      "once one who left is approved",
      () =>
        withTheWrongOne(APPROVER, { no_correction: "correction.left_paid" }),
    ],
  ])("is only read, never opened, %s", async (_, theServer) => {
    theServer();
    open();
    // The line is there, as the pay holds it, with no button to open it.
    expect(await screen.findByRole("rowheader", { name: LINE })).toBeTruthy();
    expect(screen.queryByRole("button", { name: LINE })).toBeNull();
  });

  it("opens on a month still open that takes no new one, as its first day moved since (the review)", async () => {
    // Typed for November, then Juma's first day moved into December (PPL-10): November takes no new correction, and
    // the one typed still counts, so it is still crossed out from here, as the server allows.
    withTheWrongOne(APPROVER, { no_correction: "correction.outside_job" });
    open();
    expect(await screen.findByRole("button", { name: LINE })).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Ongeza marekebisho" }),
    ).toBeNull();
  });

  it("on the demo, offers the ready reason, and says it in words once crossed out", async () => {
    withTheWrongOne(APPROVER, { correction_void_reasons: ["wrong_amount"] });
    open();
    fireEvent.click(await screen.findByRole("button", { name: LINE }));
    const sheet = await screen.findByRole("dialog");
    expect(
      within(sheet).queryByRole("textbox", { name: "Sababu ya kubatilisha" }),
    ).toBeNull();
    fireEvent.click(
      within(sheet).getByRole("radio", { name: "Kiasi kimekosewa" }),
    );
    fireEvent.click(within(sheet).getByRole("button", { name: "Batilisha" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(await voidsSent()[0]?.clone().json()).toEqual({
      reason: "wrong_amount",
    });
    expect(
      await screen.findByText(
        "Imebatilishwa na Baba · 03/12/2026 10:20 asubuhi: Kiasi kimekosewa",
      ),
    ).toBeTruthy();
  });
});
