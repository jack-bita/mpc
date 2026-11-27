// correction-sheet.test.tsx — Ongeza marekebisho on a worker's pay page (WAGE-10): the sheet as Jack drew it, what it
// sends, plus or minus, what it says before it sends, the server's refusals where they belong, the demo's ready reasons,
// and the address that opens it as the page opens.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { answer, refusal, sent } from "@/test/fake-server";
import {
  APPROVER,
  correction,
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
const CORRECTIONS = "/api/v1/staffpay/pay-corrections/";
const REASON = "Oktoba: siku ya 7/10 haikuhesabiwa";

/** Baba, who approves pay, is logged in, and Juma's November takes a correction, unless told otherwise. */
function jumasNovember(fields: Partial<WorkerPayMonth> = {}) {
  answer("GET", ME, { status: 200, body: APPROVER });
  answer("GET", payRoute(JUMA), {
    status: 200,
    body: workerPayMonth(workerPay({ staff: JUMA }), fields),
  });
}

function open() {
  return render(<WorkerPayScreen staff={JUMA} asked="2026-11" />);
}

/** The sheet, opened by its button. */
async function theSheet(): Promise<HTMLElement> {
  fireEvent.click(
    await screen.findByRole("button", { name: "Ongeza marekebisho" }),
  );
  return screen.findByRole("dialog");
}

function typeInto(sheet: HTMLElement, label: string, value: string) {
  fireEvent.change(within(sheet).getByLabelText(label), { target: { value } });
}

/** What each send of a correction carried, in order. */
async function sentCorrections(): Promise<unknown[]> {
  return Promise.all(
    sent
      .filter((request) => new URL(request.url).pathname === CORRECTIONS)
      .map((request) => request.clone().json()),
  );
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

describe("Ongeza marekebisho", () => {
  it("types + 9,000 as Jack drew it, and says what it wrote", async () => {
    jumasNovember();
    answer("POST", CORRECTIONS, {
      status: 201,
      body: correction({ reason: REASON }),
    });
    open();
    const sheet = await theSheet();

    expect(within(sheet).getByRole("heading").textContent).toBe(
      "Marekebisho ya Juma",
    );
    expect(within(sheet).getByText("Novemba 2026")).toBeTruthy();
    // Ongeza malipo picked at first, as Jack drew it.
    expect(
      within(sheet)
        .getByRole("radio", { name: "Ongeza malipo" })
        .getAttribute("aria-checked"),
    ).toBe("true");
    typeInto(sheet, "Kiasi (TSh)", "9,000");
    typeInto(sheet, "Sababu", `  ${REASON} `);
    fireEvent.click(within(sheet).getByRole("button", { name: "Hifadhi" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const [body] = (await sentCorrections()) as Record<string, string>[];
    expect(body).toEqual({
      id: expect.any(String),
      staff: JUMA,
      month: "2026-11",
      amount: "9000",
      reason: REASON,
    });
    const news = await screen.findByText("Imeandikwa: marekebisho ya + 9,000.");
    await waitFor(() =>
      expect(document.activeElement?.contains(news)).toBe(true),
    );
  });

  it("sends Punguza malipo below 0", async () => {
    jumasNovember();
    answer("POST", CORRECTIONS, {
      status: 201,
      body: correction({
        amount: "-5000.00",
        reason: "Oktoba: alilipwa zaidi",
      }),
    });
    open();
    const sheet = await theSheet();
    fireEvent.click(
      within(sheet).getByRole("radio", { name: "Punguza malipo" }),
    );
    typeInto(sheet, "Kiasi (TSh)", "5000");
    typeInto(sheet, "Sababu", "Oktoba: alilipwa zaidi");
    fireEvent.click(within(sheet).getByRole("button", { name: "Hifadhi" }));

    expect(
      await screen.findByText("Imeandikwa: marekebisho ya − 5,000."),
    ).toBeTruthy();
    const [body] = (await sentCorrections()) as Record<string, string>[];
    expect(body?.amount).toBe("-5000");
  });

  it("says what it sees itself, beside each box, and sends nothing", async () => {
    jumasNovember();
    open();
    const sheet = await theSheet();
    typeInto(sheet, "Kiasi (TSh)", "0");
    fireEvent.click(within(sheet).getByRole("button", { name: "Hifadhi" }));

    expect(
      await within(sheet).findByText(
        "Andika kiasi cha shilingi nzima, kisicho sifuri.",
      ),
    ).toBeTruthy();
    expect(within(sheet).getByText("Andika sababu.")).toBeTruthy();
    // A good amount, and still no reason: nothing sent either.
    typeInto(sheet, "Kiasi (TSh)", "9000");
    fireEvent.click(within(sheet).getByRole("button", { name: "Hifadhi" }));
    expect(await within(sheet).findByText("Andika sababu.")).toBeTruthy();
    expect(
      within(sheet).queryByText(
        "Andika kiasi cha shilingi nzima, kisicho sifuri.",
      ),
    ).toBeNull();
    expect(await sentCorrections()).toEqual([]);
  });

  it("shows the server's refusals beside their boxes, or of the whole request above the buttons", async () => {
    jumasNovember();
    answer(
      "POST",
      CORRECTIONS,
      refusal(400, "invalid", {}, { amount: ["correction.amount_too_big"] }),
    );
    open();
    const sheet = await theSheet();
    typeInto(sheet, "Kiasi (TSh)", "90000000");
    typeInto(sheet, "Sababu", REASON);
    fireEvent.click(within(sheet).getByRole("button", { name: "Hifadhi" }));
    expect(
      await within(sheet).findByText(
        "Kiasi hiki ni kikubwa mno. Angalia sifuri zake.",
      ),
    ).toBeTruthy();

    // November approved meanwhile, by someone else: the whole request is refused, and the sheet stays open.
    answer("POST", CORRECTIONS, refusal(400, "pay.day_approved"));
    typeInto(sheet, "Kiasi (TSh)", "9000");
    fireEvent.click(within(sheet).getByRole("button", { name: "Hifadhi" }));
    expect(
      await within(sheet).findByText(
        "Malipo ya siku hii yameshafungwa, hayabadiliki tena.",
      ),
    ).toBeTruthy();
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("sends the same correction again under its id, and a changed one under a new one", async () => {
    jumasNovember();
    answer("POST", CORRECTIONS, refusal(500, "server_error"));
    open();
    const sheet = await theSheet();
    typeInto(sheet, "Kiasi (TSh)", "9000");
    typeInto(sheet, "Sababu", REASON);
    fireEvent.click(within(sheet).getByRole("button", { name: "Hifadhi" }));
    await waitFor(async () => expect(await sentCorrections()).toHaveLength(1));
    fireEvent.click(within(sheet).getByRole("button", { name: "Hifadhi" }));
    await waitFor(async () => expect(await sentCorrections()).toHaveLength(2));
    typeInto(sheet, "Kiasi (TSh)", "8000");
    fireEvent.click(within(sheet).getByRole("button", { name: "Hifadhi" }));
    await waitFor(async () => expect(await sentCorrections()).toHaveLength(3));
    const [first, again, changed] = (await sentCorrections()) as {
      id: string;
    }[];
    expect(again?.id).toBe(first?.id);
    expect(changed?.id).not.toBe(first?.id);
  });

  it("on the demo, offers the ready reasons alone, and sends the one picked", async () => {
    jumasNovember({ correction_reasons: ["day_not_counted", "paid_too_much"] });
    answer("POST", CORRECTIONS, {
      status: 201,
      body: correction({ reason: "day_not_counted" }),
    });
    open();
    const sheet = await theSheet();
    expect(within(sheet).queryByRole("textbox", { name: "Sababu" })).toBeNull();
    expect(
      within(sheet).getByText("Kwenye demo, chagua sababu iliyo tayari."),
    ).toBeTruthy();
    typeInto(sheet, "Kiasi (TSh)", "9000");
    fireEvent.click(
      within(sheet).getByRole("radio", { name: "Siku haikuhesabiwa" }),
    );
    fireEvent.click(within(sheet).getByRole("button", { name: "Hifadhi" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const [body] = (await sentCorrections()) as Record<string, string>[];
    expect(body?.reason).toBe("day_not_counted");
  });

  it("opens as the page opens when the address asks, and the word goes as it closes", async () => {
    window.history.replaceState(
      null,
      "",
      `/pay/worker/?staff=${JUMA}&month=2026-11&marekebisho=ongeza`,
    );
    jumasNovember();
    open();
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByRole("heading").textContent).toBe(
      "Marekebisho ya Juma",
    );
    fireEvent.click(within(sheet).getByRole("button", { name: "Ghairi" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(
      new URLSearchParams(window.location.search).get("marekebisho"),
    ).toBeNull();
    expect(new URLSearchParams(window.location.search).get("staff")).toBe(JUMA);
  });
});
