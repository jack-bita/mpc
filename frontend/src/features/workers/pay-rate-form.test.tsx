// pay-rate-form.test.tsx — Weka malipo and Badilisha malipo on a worker's page (WAGE-1): where the boxes start, what is
// sent and what is said after, in a sheet over the page (UI-10); what the sheet sees itself and sends nothing for; the
// server's refusals, beside their boxes or above the sheet's buttons; the same id for a try of the same rate; offline;
// Ghairi.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { MESSAGES } from "@/i18n/language";
import { Decimal } from "@/lib/decimal";
import { formatMoney } from "@/lib/format";
import { answer, refusal, sent } from "@/test/fake-server";
import {
  MealMoneyAsked,
  mealMoneyIsAnswered,
  MonthsAsked,
  monthsAreAnswered,
} from "@/test/meals";
import { notPaidByDay, PayAsked, payIsAnswered } from "@/test/pay";
import { PAY_RATES_ROUTE, payRate, payRates, TODAY } from "@/test/pay-rates";
import { render } from "@/test/render";
import { BABA, STAFF, worker } from "@/test/workers";

import { WorkerScreen } from "./worker-page";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

afterEach(() => {
  // A test that takes the network away puts it back after (navigator.onLine's spy).
  vi.restoreAllMocks();
});

type PayRates = components["schemas"]["PayRatesAnswer"];
type PayRate = components["schemas"]["PayRate"];

const ME = "/api/auth/me/";

/** Juma, working since 10 Nov 2026. */
const JUMA = worker({ started_on: "2026-11-10" });

/** The server's sentence for a code, from the Swahili book, as the page shows it. */
function sentence(code: string): string {
  let found: unknown = MESSAGES.sw.errors;
  for (const part of code.split("."))
    found = (found as Record<string, unknown>)[part];
  if (typeof found !== "string") throw new Error(`no sentence for ${code}`);
  return found;
}

/** The server holds Juma and his `rates`; a save answers with the rate it was sent, unless a test says otherwise. */
function theServerHas(rates: PayRates): void {
  answer("GET", ME, { status: 200, body: BABA });
  answer("GET", `${STAFF}${JUMA.id}/`, { status: 200, body: JUMA });
  answer("GET", PAY_RATES_ROUTE, { status: 200, body: rates });
  notPaidByDay(JUMA.id);
  answer("POST", PAY_RATES_ROUTE, async (request) => {
    const body = (await request.json()) as PayRate;
    return Response.json(
      payRate({ ...body, daily_rate: `${body.daily_rate}.00` }),
      { status: 201 },
    );
  });
}

/** What the app sent to the rates route, in order, as the server would read it. */
async function posted(): Promise<Record<string, unknown>[]> {
  return Promise.all(
    sent
      .filter((request) => request.method === "POST")
      .map(
        (request) => request.clone().json() as Promise<Record<string, unknown>>,
      ),
  );
}

const reads = () =>
  sent.filter(
    (request) =>
      request.method === "GET" && request.url.includes(PAY_RATES_ROUTE),
  ).length;

const button = (name: string) => screen.getByRole("button", { name });
const box = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
const radio = (name: string) => screen.getByRole("radio", { name });

/** The error under a box: the line its aria-describedby names (field.tsx). */
function errorOf(element: HTMLElement): string {
  const ids = element.getAttribute("aria-describedby")?.split(" ") ?? [];
  const error = ids.find((id) => id.endsWith("-error"));
  return error ? (document.getElementById(error)?.textContent ?? "") : "";
}

function typeInto(element: HTMLElement, text: string) {
  fireEvent.change(element, { target: { value: text } });
}

/** Opens the sheet by its button's name, on Juma's page. */
async function openTheForm(name: "Weka malipo" | "Badilisha malipo") {
  render(<WorkerScreen id={JUMA.id} />);
  fireEvent.click(await screen.findByRole("button", { name }));
  await screen.findByRole("dialog", { name: "Malipo mapya ya Juma" });
}

/** A button inside the open sheet: Hifadhi malipo, its main one, or Ghairi (UI-10). */
const sheetButton = (name: string) =>
  within(screen.getByRole("dialog")).getByRole("button", { name });

describe("Weka malipo", () => {
  it("starts on the first day, sharing the meals, and saves the rate", async () => {
    // Juma started on the 10th; Baba types his rate on the 19th, from the 10th, so those days are paid.
    theServerHas(payRates([], null));
    await openTheForm("Weka malipo");

    // The keyboard is in the sheet's first box, Base UI's own on a laptop; on a phone, on the sheet itself.
    await waitFor(() =>
      expect(document.activeElement).toBe(box("Kiasi kwa siku")),
    );
    expect(box("Kiasi kwa siku").value).toBe("");
    expect(box("Kuanzia").value).toBe("2026-11-10");
    expect(radio("Ndiyo").getAttribute("aria-checked")).toBe("true");

    const before = reads();
    typeInto(box("Kiasi kwa siku"), "10,000");
    fireEvent.click(sheetButton("Hifadhi malipo"));

    // Spaces as a reader reads them: money is written with a space that never breaks ("TSh 10,000").
    const plain = (text: string) => text.replace(/\s+/g, " ");
    const line = plain(
      `Malipo ya Juma yamehifadhiwa: ${formatMoney(new Decimal("10000"))} kwa siku, kuanzia 10/11/2026.`,
    );
    await waitFor(() =>
      expect(plain(document.activeElement?.textContent ?? "")).toBe(line),
    );
    // On Malipo kwa siku itself, never only somewhere on the page (UI-10's review).
    expect(
      within(screen.getByRole("region", { name: "Malipo kwa siku" })).getByText(
        line,
      ),
    ).toBeTruthy();
    const [body] = await posted();
    expect(body).toEqual({
      id: expect.stringMatching(/^[0-9a-f-]{36}$/) as unknown,
      staff: JUMA.id,
      daily_rate: "10000",
      effective_from: "2026-11-10",
      shares_meals: true,
      note: "",
    });
    // The sheet is gone, and the rates are asked again, so the new one shows where it belongs.
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(reads()).toBeGreaterThan(before));
  });
});

describe("after a save", () => {
  it("asks the months, the meal money and the pay again, as a rate says who is paid and who shares the meals", async () => {
    // Baba makes Juma the cook, then opens Hela ya chakula within the minute its answer is kept: the split must be the
    // new one (WAGE-7's review). And a first rate puts him on the month page, his days' shares on his own.
    theServerHas(payRates([], null));
    const meals = mealMoneyIsAnswered();
    const months = monthsAreAnswered();
    const payAsked = payIsAnswered();
    render(
      <>
        <MealMoneyAsked />
        <MonthsAsked />
        <PayAsked />
        <WorkerScreen id={JUMA.id} />
      </>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Weka malipo" }));
    await screen.findByRole("dialog", { name: "Malipo mapya ya Juma" });
    await waitFor(() =>
      expect([meals(), months(), payAsked()]).toEqual([
        1,
        { month: 1, worker: 1 },
        [1, 1],
      ]),
    );

    typeInto(box("Kiasi kwa siku"), "10000");
    fireEvent.click(radio("Hapana, ni mpishi"));
    fireEvent.click(sheetButton("Hifadhi malipo"));

    await waitFor(() =>
      expect([meals(), months(), payAsked()]).toEqual([
        2,
        { month: 2, worker: 2 },
        [2, 2],
      ]),
    );
  });

  it("shows the new rate as today's and in the history, read again from the server", async () => {
    // The card's first box, end to end on the page: Baba sets Juma's 10,000 from his first day, and the card shows it
    // as Sasa and in Historia, from the server's next answer, as the store asks the rates again after the save.
    let held = payRates([], null);
    answer("GET", ME, { status: 200, body: BABA });
    answer("GET", `${STAFF}${JUMA.id}/`, { status: 200, body: JUMA });
    answer("GET", PAY_RATES_ROUTE, () => Response.json(held));
    notPaidByDay(JUMA.id);
    answer("POST", PAY_RATES_ROUTE, async (request) => {
      const body = (await request.json()) as PayRate;
      const saved = payRate({ ...body, daily_rate: `${body.daily_rate}.00` });
      held = payRates([saved], saved);
      return Response.json(saved, { status: 201 });
    });
    await openTheForm("Weka malipo");

    typeInto(box("Kiasi kwa siku"), "10000");
    fireEvent.click(sheetButton("Hifadhi malipo"));

    // Spaces as a reader reads them: money is written with a space that never breaks ("TSh 10,000").
    const plain = (text: string) => text.replace(/\s+/g, " ");
    const tsh = plain(formatMoney(new Decimal("10000")));
    // Once the sheet has gone, and the page behind it can be read again.
    const card = await screen.findByRole("region", { name: "Malipo kwa siku" });
    expect(
      await within(card).findByText(
        `Sasa: ${tsh} kwa siku · anachangia chakula`,
      ),
    ).toBeTruthy();
    const history = within(card).getByRole("region", { name: "Historia" });
    expect(
      within(history)
        .getAllByRole("listitem")
        .map((line) => plain(line.textContent ?? "")),
    ).toEqual([`Kuanzia 10/11/2026 · ${tsh} · anachangia chakula`]);
    expect(
      within(card).getByRole("button", { name: "Badilisha malipo" }),
    ).toBeTruthy();
  });
});

describe("Badilisha malipo", () => {
  it("starts from today's rate, on today, and sends a raise with its reason", async () => {
    // Neema's case on Juma's page: the cook's 8,000, in force today. A raise keeps her answer about the meals.
    const cooks = payRate({
      staff: JUMA.id,
      daily_rate: "8000.00",
      shares_meals: false,
    });
    theServerHas(payRates([cooks], cooks));
    await openTheForm("Badilisha malipo");

    expect(box("Kiasi kwa siku").value).toBe("8000");
    expect(box("Kuanzia").value).toBe(TODAY);
    expect(radio("Hapana, ni mpishi").getAttribute("aria-checked")).toBe(
      "true",
    );

    typeInto(box("Kiasi kwa siku"), "9000");
    typeInto(box("Kuanzia"), "2026-12-01");
    typeInto(box("Sababu (si lazima)"), "Ameongezewa");
    fireEvent.click(sheetButton("Hifadhi malipo"));

    await waitFor(async () =>
      expect(await posted()).toEqual([
        expect.objectContaining({
          daily_rate: "9000",
          effective_from: "2026-12-01",
          shares_meals: false,
          note: "Ameongezewa",
        }),
      ]),
    );
  });

  it("starts a worker who hasn't started yet on their first day", async () => {
    // Zawadi starts on the 25th and has her rate from then; Baba adds another on the 19th: the box starts on her first
    // day, as one on today would be refused (pay_rate.before_first_day).
    const zawadi = worker({ display_name: "Zawadi", started_on: "2026-11-25" });
    const coming = payRate({ staff: zawadi.id, effective_from: "2026-11-25" });
    answer("GET", ME, { status: 200, body: BABA });
    answer("GET", `${STAFF}${zawadi.id}/`, { status: 200, body: zawadi });
    notPaidByDay(zawadi.id);
    answer("GET", PAY_RATES_ROUTE, {
      status: 200,
      body: payRates([coming], null),
    });

    render(<WorkerScreen id={zawadi.id} />);
    fireEvent.click(await screen.findByRole("button", { name: "Weka malipo" }));
    await screen.findByRole("dialog", { name: "Malipo mapya ya Zawadi" });

    expect(box("Kuanzia").value).toBe("2026-11-25");
  });

  it("starts one who left on their first day, and takes no day after their last (WAGE-3's review)", async () => {
    // Juma came on the 16th and the 17th, his rate was typed from the 17th, and he left on the 18th: what he lacks is
    // the 16th's, which holds his approval.
    const gone = worker({
      started_on: "2026-11-16",
      status: "left",
      left_on: "2026-11-18",
    });
    const rate = payRate({ staff: gone.id, effective_from: "2026-11-17" });
    answer("GET", ME, { status: 200, body: BABA });
    answer("GET", `${STAFF}${gone.id}/`, { status: 200, body: gone });
    notPaidByDay(gone.id);
    answer("GET", PAY_RATES_ROUTE, {
      status: 200,
      body: payRates([rate], rate),
    });

    render(<WorkerScreen id={gone.id} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Badilisha malipo" }),
    );
    await screen.findByRole("dialog", { name: "Malipo mapya ya Juma" });

    expect(box("Kuanzia").value).toBe("2026-11-16");
    expect([box("Kuanzia").min, box("Kuanzia").max]).toEqual([
      "2026-11-16",
      "2026-11-18",
    ]);
    typeInto(box("Kuanzia"), "2026-11-19");
    fireEvent.click(sheetButton("Hifadhi malipo"));
    expect(errorOf(box("Kuanzia"))).toBe(sentence("pay_rate.after_last_day"));
    expect(await posted()).toEqual([]);

    // Their last day itself is one of theirs.
    typeInto(box("Kuanzia"), "2026-11-18");
    fireEvent.click(sheetButton("Hifadhi malipo"));
    await waitFor(async () => expect(await posted()).toHaveLength(1));
  });

  it("asks about the meals again for each rate", async () => {
    const rate = payRate({ staff: JUMA.id });
    theServerHas(payRates([rate], rate));
    await openTheForm("Badilisha malipo");

    fireEvent.click(radio("Hapana, ni mpishi"));
    fireEvent.click(sheetButton("Hifadhi malipo"));

    await waitFor(async () =>
      expect(await posted()).toEqual([
        expect.objectContaining({ daily_rate: "10000", shares_meals: false }),
      ]),
    );
  });
});

describe("what the form says itself", () => {
  it.each([
    ["an empty amount", ""],
    ["no pay at all", "0"],
    ["cents", "10000.50"],
    ["words", "elfu kumi"],
  ])("refuses %s beside the amount, and sends nothing", async (_, typed) => {
    theServerHas(payRates([], null));
    await openTheForm("Weka malipo");

    typeInto(box("Kiasi kwa siku"), typed);
    fireEvent.click(sheetButton("Hifadhi malipo"));

    expect(errorOf(box("Kiasi kwa siku"))).toBe(
      sentence("pay_rate.amount_invalid"),
    );
    expect(await posted()).toEqual([]);
  });

  it("refuses a day before the first, or none, beside the day, and sends nothing", async () => {
    theServerHas(payRates([], null));
    await openTheForm("Weka malipo");
    typeInto(box("Kiasi kwa siku"), "10000");

    typeInto(box("Kuanzia"), "2026-11-09");
    fireEvent.click(sheetButton("Hifadhi malipo"));
    expect(errorOf(box("Kuanzia"))).toBe(sentence("pay_rate.before_first_day"));

    typeInto(box("Kuanzia"), "");
    fireEvent.click(sheetButton("Hifadhi malipo"));
    expect(errorOf(box("Kuanzia"))).toBe(sentence("required"));

    expect(await posted()).toEqual([]);
  });

  it("offers nothing before the first day on the phone's calendar", async () => {
    theServerHas(payRates([], null));
    await openTheForm("Weka malipo");
    expect(box("Kuanzia").min).toBe("2026-11-10");
  });
});

describe("the server's refusals", () => {
  it("shows a rate with zeros too many beside its box (WAGE-2's review)", async () => {
    theServerHas(payRates([], null));
    answer(
      "POST",
      PAY_RATES_ROUTE,
      refusal(400, "invalid", {}, { daily_rate: ["pay_rate.amount_too_big"] }),
    );
    await openTheForm("Weka malipo");

    typeInto(box("Kiasi kwa siku"), "999999999999");
    fireEvent.click(sheetButton("Hifadhi malipo"));

    await waitFor(() =>
      expect(errorOf(box("Kiasi kwa siku"))).toBe(
        "Kiasi hiki ni kikubwa mno. Angalia sifuri zake.",
      ),
    );
  });

  it("shows beside its box that a day's pay is approved (WAGE-3)", async () => {
    theServerHas(payRates([], null));
    answer(
      "POST",
      PAY_RATES_ROUTE,
      refusal(400, "invalid", {}, { effective_from: ["pay.day_approved"] }),
    );
    await openTheForm("Weka malipo");

    typeInto(box("Kiasi kwa siku"), "10000");
    fireEvent.click(sheetButton("Hifadhi malipo"));

    await waitFor(() =>
      expect(errorOf(box("Kuanzia"))).toBe(sentence("pay.day_approved")),
    );
    // The form stays, so a day still open can be picked.
    expect(box("Kiasi kwa siku").value).toBe("10000");
  });

  it("shows a box's refusal beside it, as the demo's note", async () => {
    theServerHas(payRates([], null));
    answer(
      "POST",
      PAY_RATES_ROUTE,
      refusal(400, "invalid", {}, { note: ["demo.no_note"] }),
    );
    await openTheForm("Weka malipo");

    typeInto(box("Kiasi kwa siku"), "10000");
    typeInto(box("Sababu (si lazima)"), "Ameongezewa");
    fireEvent.click(sheetButton("Hifadhi malipo"));

    await waitFor(() =>
      expect(errorOf(box("Sababu (si lazima)"))).toBe(sentence("demo.no_note")),
    );
    // The form stays, with what was typed.
    expect(box("Kiasi kwa siku").value).toBe("10000");
  });

  it("shows who may above the sheet's buttons, in the server's sentence", async () => {
    // Juma holds a key Meneja lacks: the server's rule, the same as for his details (staff.more_keys).
    theServerHas(payRates([], null));
    answer("POST", PAY_RATES_ROUTE, refusal(400, "staff.more_keys"));
    await openTheForm("Weka malipo");

    typeInto(box("Kiasi kwa siku"), "10000");
    fireEvent.click(sheetButton("Hifadhi malipo"));

    // Inside the sheet, which stays open, above its buttons.
    const sheet = screen.getByRole("dialog", { name: "Malipo mapya ya Juma" });
    expect((await within(sheet).findByRole("alert")).textContent).toContain(
      sentence("staff.more_keys"),
    );
  });

  it("sends a try of the same rate under its id, and a changed one under a new id", async () => {
    // The first send's answer is lost to a server error: the same try again goes under the same id, so the server
    // finds the rate the first made, if it made one; a changed amount is a new rate, under a new id.
    theServerHas(payRates([], null));
    answer("POST", PAY_RATES_ROUTE, refusal(500, "server_error"));
    await openTheForm("Weka malipo");

    typeInto(box("Kiasi kwa siku"), "10000");
    fireEvent.click(sheetButton("Hifadhi malipo"));
    await screen.findByRole("alert");
    fireEvent.click(sheetButton("Hifadhi malipo"));
    await waitFor(async () => expect(await posted()).toHaveLength(2));
    typeInto(box("Kiasi kwa siku"), "12000");
    fireEvent.click(sheetButton("Hifadhi malipo"));

    await waitFor(async () => expect(await posted()).toHaveLength(3));
    const [first, again, changed] = (await posted()).map((body) => body.id);
    expect(again).toBe(first);
    expect(changed).not.toBe(first);
  });
});

describe("leaving the form", () => {
  it("switches the sheet's Hifadhi malipo off offline", async () => {
    theServerHas(payRates([], null));
    await openTheForm("Weka malipo");
    // The network gone as the form draws again (useOnline reads it as it draws): no "offline" event, which would leave
    // TanStack's own watcher offline for the tests after (worker-roles.test.tsx).
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    typeInto(box("Kiasi kwa siku"), "10000");

    await waitFor(() =>
      expect(sheetButton("Hifadhi malipo").hasAttribute("disabled")).toBe(true),
    );
  });

  it("gives the keyboard back to the button on Ghairi, and asks the rates and the pay again", async () => {
    theServerHas(payRates([], null));
    const payAsked = payIsAnswered();
    // One store for both, as the app has.
    render(
      <>
        <PayAsked />
        <WorkerScreen id={JUMA.id} />
      </>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Weka malipo" }));
    await screen.findByRole("dialog", { name: "Malipo mapya ya Juma" });
    await waitFor(() => expect(payAsked()).toEqual([1, 1]));
    const before = reads();

    fireEvent.click(sheetButton("Ghairi"));

    await waitFor(() =>
      expect(document.activeElement).toBe(button("Weka malipo")),
    );
    await waitFor(() => expect(reads()).toBeGreaterThan(before));
    // A save whose answer was lost may have been made, and moved the pay (WAGE-2).
    await waitFor(() => expect(payAsked()).toEqual([2, 2]));
    expect(await posted()).toEqual([]);
  });

  it("keeps one form open at a time on the page, the page shut off behind the sheet", async () => {
    // While Malipo mapya is open, only its own buttons can be reached (PPL-8's review, UI-10): the others stay drawn,
    // in their places, behind it.
    theServerHas(payRates([], null));
    await openTheForm("Weka malipo");

    expect(screen.queryByRole("link", { name: "Badilisha" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Ongeza kazi" })).toBeNull();
    expect(
      screen.getByRole("link", { name: "Ongeza kazi", hidden: true }),
    ).toBeTruthy();
  });
});
