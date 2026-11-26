// pay-sheet.test.tsx — the Lipa sheet (WAGE-9), as Jack drew it (26 Nov 2026): the whole amount, Taslimu with Asha's
// signature or M-Pesa and Benki with their number, Nimemlipa off until one is there, what is sent each way, the demo,
// and the server's refusals beside the box or above the buttons.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import sw from "../../../messages/sw.json";
import { standInCanvas, signOn, DRAWN } from "@/test/canvas";
import { answer, refusal, sent } from "@/test/fake-server";
import { payment, workerPay } from "@/test/pay";
import { render } from "@/test/render";

import { PaySheet } from "./pay-sheet";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const SLIP = "019a8600-0000-7000-8000-0000000005a1";
const ASHA = workerPay({
  display_name: "Asha",
  total: "152000.00",
  payslip: SLIP,
  to_hand_out: "152000.00",
});
const BY_NUMBER = `/api/v1/staffpay/payslips/${SLIP}/pay/`;
const IN_CASH = `/api/v1/staffpay/payslips/${SLIP}/pay-cash/`;

beforeEach(() => {
  standInCanvas();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function open(keepsSignatures = true) {
  const onDone = vi.fn();
  const onClose = vi.fn();
  render(
    <PaySheet
      worker={ASHA}
      month="2026-11"
      keepsSignatures={keepsSignatures}
      onDone={onDone}
      onClose={onClose}
      finalFocus={() => null}
    />,
  );
  const sheet = screen.getByRole("dialog");
  return { sheet, onDone, onClose };
}

/** The sheet open, with the render's own handles, to draw it again with other props. */
function openWith() {
  const rendered = render(
    <PaySheet
      worker={ASHA}
      month="2026-11"
      keepsSignatures
      onDone={vi.fn()}
      onClose={vi.fn()}
      finalFocus={() => null}
    />,
  );
  return { ...rendered, sheet: screen.getByRole("dialog") };
}

function nimemlipa(sheet: HTMLElement): HTMLButtonElement {
  return within(sheet).getByRole("button", {
    name: "Nimemlipa",
  }) as HTMLButtonElement;
}

/** What was sent to a route, in order. */
function requests(path: string): Request[] {
  return sent.filter((request) => new URL(request.url).pathname === path);
}

/** The one request sent to a route. */
function only(path: string): Request {
  const [request, ...more] = requests(path);
  expect(more).toHaveLength(0);
  if (request === undefined) throw new Error(`Nothing was sent to ${path}.`);
  return request;
}

describe("PaySheet", () => {
  it("says whose pay, which month and how much, as Jack drew it", () => {
    const { sheet } = open();
    expect(within(sheet).getByRole("heading").textContent).toBe("Lipa Asha");
    expect(sheet.textContent.replace(/ /g, " ")).toContain(
      "Novemba 2026 · TSh 152,000",
    );
    for (const way of ["Taslimu", "M-Pesa", "Benki"])
      expect(within(sheet).getByRole("radio", { name: way })).toBeTruthy();
    expect(
      (
        within(sheet).getByRole("radio", { name: "Taslimu" }) as HTMLElement
      ).getAttribute("aria-checked"),
    ).toBe("true");
  });

  it("keeps the amount it opened with while the page reads the pay again", () => {
    // Once paid, the page's line says nothing is left to hand out, a moment before the sheet goes: never "TSh 0".
    const { sheet, rerender } = openWith();
    rerender(
      <PaySheet
        worker={{ ...ASHA, to_hand_out: "0.00" }}
        month="2026-11"
        keepsSignatures
        onDone={vi.fn()}
        onClose={vi.fn()}
        finalFocus={() => null}
      />,
    );
    expect(sheet.textContent.replace(/\u00a0/g, " ")).toContain(
      "Novemba 2026 · TSh 152,000",
    );
  });

  it("keeps Nimemlipa off until Asha has signed", () => {
    const { sheet } = open();
    expect(nimemlipa(sheet).disabled).toBe(true);
    signOn(within(sheet).getByRole("img", { name: "Sahihi ya Asha" }));
    expect(nimemlipa(sheet).disabled).toBe(false);
    // Futa sahihi empties it, and Nimemlipa waits again.
    fireEvent.click(within(sheet).getByRole("button", { name: "Futa sahihi" }));
    expect(nimemlipa(sheet).disabled).toBe(true);
  });

  it("waits for a new signature once another way was picked and Taslimu again", () => {
    // Asha signs, Baba taps M-Pesa by mistake, then Taslimu: the box is back empty, and so Nimemlipa is off.
    const { sheet } = open();
    signOn(within(sheet).getByRole("img", { name: "Sahihi ya Asha" }));
    fireEvent.click(within(sheet).getByRole("radio", { name: "M-Pesa" }));
    fireEvent.click(within(sheet).getByRole("radio", { name: "Taslimu" }));
    expect(nimemlipa(sheet).disabled).toBe(true);
    signOn(within(sheet).getByRole("img", { name: "Sahihi ya Asha" }));
    expect(nimemlipa(sheet).disabled).toBe(false);
  });

  it("sends the drawing as the body, with its two ids, and closes once the pay is read again", async () => {
    answer("PUT", IN_CASH, { status: 200, body: payment() });
    const { sheet, onDone } = open();
    signOn(within(sheet).getByRole("img", { name: "Sahihi ya Asha" }));
    fireEvent.click(nimemlipa(sheet));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const request = only(IN_CASH);
    const asked = new URL(request.url).searchParams;
    expect(asked.get("id")).toMatch(/^[0-9a-f-]{36}$/);
    expect(asked.get("signature")).toMatch(/^[0-9a-f-]{36}$/);
    expect(asked.get("id")).not.toBe(asked.get("signature"));
    expect(request.headers.get("Content-Type")).toBe("image/jpeg");
    expect(await request.clone().text()).toBe(DRAWN);
    expect(requests(BY_NUMBER)).toHaveLength(0);
  });

  it("sends M-Pesa with its number, once it is typed", async () => {
    answer("POST", BY_NUMBER, {
      status: 200,
      body: payment({ method: "mobile_money", reference: "QK7H2M9XPL" }),
    });
    const { sheet, onDone } = open();
    fireEvent.click(within(sheet).getByRole("radio", { name: "M-Pesa" }));
    // No signature box now: the number is the proof.
    expect(within(sheet).queryByRole("img")).toBeNull();
    expect(nimemlipa(sheet).disabled).toBe(true);
    fireEvent.change(within(sheet).getByLabelText("Namba ya muamala"), {
      target: { value: "QK7H2M9XPL" },
    });
    fireEvent.click(nimemlipa(sheet));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const request = only(BY_NUMBER);
    const body = (await request.clone().json()) as Record<string, string>;
    expect({ method: body.method, reference: body.reference }).toEqual({
      method: "mobile_money",
      reference: "QK7H2M9XPL",
    });
  });

  it("says a number used already beside its box", async () => {
    answer(
      "POST",
      BY_NUMBER,
      refusal(400, "invalid", {}, { reference: ["payment.reference_used"] }),
    );
    const { sheet, onDone } = open();
    fireEvent.click(within(sheet).getByRole("radio", { name: "Benki" }));
    fireEvent.change(within(sheet).getByLabelText("Namba ya muamala"), {
      target: { value: "BENKI1" },
    });
    fireEvent.click(nimemlipa(sheet));
    expect(
      await within(sheet).findByText(
        "Namba hii ya muamala imeshatumika kwa malipo mengine.",
      ),
    ).toBeTruthy();
    expect(onDone).not.toHaveBeenCalled();
  });

  it("says a payslip paid already above the buttons, and sends the same payment again", async () => {
    answer("PUT", IN_CASH, refusal(400, "payment.already_paid"));
    const { sheet } = open();
    signOn(within(sheet).getByRole("img", { name: "Sahihi ya Asha" }));
    fireEvent.click(nimemlipa(sheet));
    expect(
      await within(sheet).findByText(
        "Mfanyakazi huyu ameshalipwa malipo haya.",
      ),
    ).toBeTruthy();
    fireEvent.click(nimemlipa(sheet));
    await waitFor(() => expect(requests(IN_CASH)).toHaveLength(2));
    const [first, second] = requests(IN_CASH).map(
      (request) => new URL(request.url).search,
    );
    // The same ids: the same payment and signature, never a second one.
    expect(second).toBe(first);
  });

  it("says an id held already above the buttons, where no box names it", async () => {
    answer("PUT", IN_CASH, refusal(400, "invalid", {}, { id: ["id.taken"] }));
    const { sheet, onDone } = open();
    signOn(within(sheet).getByRole("img", { name: "Sahihi ya Asha" }));
    fireEvent.click(nimemlipa(sheet));
    expect(await within(sheet).findByText(sw.errors.id.taken)).toBeTruthy();
    expect(onDone).not.toHaveBeenCalled();
  });

  it("on the demo, lets the visitor draw and sends no signature", async () => {
    answer("POST", BY_NUMBER, {
      status: 200,
      body: payment({ signature: null, no_signature: "demo" }),
    });
    const { sheet, onDone } = open(false);
    expect(sheet.textContent).toContain("Kwenye demo, sahihi haihifadhiwi.");
    // A number typed under M-Pesa, then back to Taslimu: cash goes with no number.
    fireEvent.click(within(sheet).getByRole("radio", { name: "M-Pesa" }));
    fireEvent.change(within(sheet).getByLabelText("Namba ya muamala"), {
      target: { value: "QK7H2M9XPL" },
    });
    fireEvent.click(within(sheet).getByRole("radio", { name: "Taslimu" }));
    signOn(within(sheet).getByRole("img", { name: "Sahihi ya Asha" }));
    fireEvent.click(nimemlipa(sheet));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(requests(IN_CASH)).toHaveLength(0);
    const request = only(BY_NUMBER);
    const body = (await request.clone().json()) as Record<string, string>;
    expect({ method: body.method, reference: body.reference }).toEqual({
      method: "cash",
      reference: "",
    });
  });
});
