// worker-pay.test.tsx — Malipo kwa siku on a worker's page (WAGE-1): the rate in force today and the history, newest
// first; a worker with none, or with one still to come; the cook; who sees the card at all, and who gets its button.
// The form behind the button is pay-rate-form.test.tsx's.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { Decimal } from "@/lib/decimal";
import { formatMoney } from "@/lib/format";
import { answer, refusal, sent } from "@/test/fake-server";
import { PAY_RATES_ROUTE, payRate, payRates } from "@/test/pay-rates";
import { render } from "@/test/render";
import {
  BABA,
  MANAGER,
  ROLES_ROUTE,
  rolesPage,
  SHOP_ROLES,
  STAFF,
  worker,
} from "@/test/workers";

import { WorkerScreen } from "./worker-page";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type Worker = components["schemas"]["Staff"];
type WhoIsHere = components["schemas"]["WhoIsHere"];
type PayRates = components["schemas"]["PayRatesAnswer"];

const ME = "/api/auth/me/";

/** Juma, working since 10 Nov 2026. */
const JUMA = worker({ started_on: "2026-11-10" });

/** Spaces as a reader reads them: money is written with a space that never breaks ("TSh 10,000"), which the text
 * search reads as a plain one. */
const plain = (text: string) => text.replace(/\s+/g, " ");

/** "TSh 10,000", as the shop writes money, with a plain space. */
const tsh = (amount: string) => plain(formatMoney(new Decimal(amount)));

/** The server holds `who`, logged in, and `shown`, whose rates are `rates`. */
function theServerHas(
  shown: Worker,
  rates: PayRates,
  who: WhoIsHere = BABA,
): void {
  answer("GET", ME, { status: 200, body: who });
  answer("GET", `${STAFF}${shown.id}/`, { status: 200, body: shown });
  answer("GET", PAY_RATES_ROUTE, { status: 200, body: rates });
}

/** The card, once its heading shows. */
async function theCard(): Promise<HTMLElement> {
  return screen.findByRole("region", { name: "Malipo kwa siku" });
}

/** The lines of the card's history, newest first. */
function history(card: HTMLElement): string[] {
  const section = within(card).getByRole("region", { name: "Historia" });
  return within(section)
    .getAllByRole("listitem")
    .map((line) => plain(line.textContent ?? ""));
}

const ratesAsked = () =>
  sent.filter((request) => request.url.includes(PAY_RATES_ROUTE));

describe("Malipo kwa siku", () => {
  it("shows today's rate, and the history newest first, asked for this worker", async () => {
    // As Jack pictured it: 10,000 from his first day, in force today, and a raise from 1 December with its reason.
    const first = payRate({ staff: JUMA.id });
    const raise = payRate({
      staff: JUMA.id,
      daily_rate: "12000.00",
      effective_from: "2026-12-01",
      note: "Ameongezewa",
    });
    theServerHas(JUMA, payRates([raise, first], first));

    render(<WorkerScreen id={JUMA.id} />);
    const card = await theCard();

    expect(
      await within(card).findByText(
        `Sasa: ${tsh("10000")} kwa siku · anachangia chakula`,
      ),
    ).toBeTruthy();
    expect(history(card)).toEqual([
      `Kuanzia 01/12/2026 · ${tsh("12000")} · anachangia chakula · Ameongezewa`,
      `Kuanzia 10/11/2026 · ${tsh("10000")} · anachangia chakula`,
    ]);
    expect(
      within(card).getByRole("button", { name: "Badilisha malipo" }),
    ).toBeTruthy();
    // Asked for Juma alone, by his job's id.
    expect(
      new URL(ratesAsked()[0]?.url ?? "http://x").searchParams.get("staff"),
    ).toBe(JUMA.id);
  });

  it("says a worker has no rate yet, and offers Weka malipo", async () => {
    theServerHas(JUMA, payRates([], null));

    render(<WorkerScreen id={JUMA.id} />);
    const card = await theCard();

    expect(
      await within(card).findByText("Bado hana malipo kwa siku."),
    ).toBeTruthy();
    expect(within(card).queryByRole("region", { name: "Historia" })).toBeNull();
    expect(
      within(card).getByRole("button", { name: "Weka malipo" }),
    ).toBeTruthy();
  });

  it("shows a first rate still to come in the history, with none today", async () => {
    // Typed today, from Monday: it counts from its own day, which the server says, on the shop's date.
    const coming = payRate({ staff: JUMA.id, effective_from: "2026-11-23" });
    theServerHas(JUMA, payRates([coming], null));

    render(<WorkerScreen id={JUMA.id} />);
    const card = await theCard();

    expect(
      await within(card).findByText("Bado hana malipo kwa siku."),
    ).toBeTruthy();
    expect(history(card)).toEqual([
      `Kuanzia 23/11/2026 · ${tsh("10000")} · anachangia chakula`,
    ]);
    expect(
      within(card).getByRole("button", { name: "Weka malipo" }),
    ).toBeTruthy();
  });

  it("says the cook pays no share of the meals", async () => {
    const neema = worker({ display_name: "Neema", started_on: "2026-11-01" });
    const cooks = payRate({
      staff: neema.id,
      daily_rate: "8000.00",
      effective_from: "2026-11-01",
      shares_meals: false,
    });
    theServerHas(neema, payRates([cooks], cooks));

    render(<WorkerScreen id={neema.id} />);
    const card = await theCard();

    expect(
      await within(card).findByText(
        `Sasa: ${tsh("8000")} kwa siku · hachangii chakula, ni mpishi`,
      ),
    ).toBeTruthy();
  });

  it("isn't there for someone without the rules-and-rates key, and asks nothing", async () => {
    // Neema manages the workers (staff.manage) but not the shop's rules and rates: the route would refuse her, so the
    // page neither shows the card nor asks.
    theServerHas(JUMA, payRates([], null), MANAGER);

    render(<WorkerScreen id={JUMA.id} />);

    expect(
      await screen.findByRole("button", { name: "Badilisha" }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("region", { name: "Malipo kwa siku" }),
    ).toBeNull();
    expect(ratesAsked()).toEqual([]);
  });

  it("isn't there for someone with the rules-and-rates key alone, and asks nothing", async () => {
    // Baba hands Neema settings.manage to change the late fine, and nothing else: seeing a worker's pay needs the same
    // two keys as changing it (Jack, WAGE-1's review: A), so the page asks no rates, whatever address she opens.
    const finesOnly: WhoIsHere = {
      ...MANAGER,
      permissions: {
        whole_shop: ["settings.manage"],
        sides: MANAGER.permissions.sides.map((side) => ({
          ...side,
          permissions: ["settings.manage"],
        })),
      },
    };
    theServerHas(JUMA, payRates([], null), finesOnly);

    render(<WorkerScreen id={JUMA.id} />);

    expect(
      await screen.findByRole("heading", { name: JUMA.display_name }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("region", { name: "Malipo kwa siku" }),
    ).toBeNull();
    expect(ratesAsked()).toEqual([]);
  });

  it("offers no button on one's own page", async () => {
    // Nobody sets their own pay (staff.own): Baba opens his own page and sees his rate, if he has one, and no button.
    const own = worker({ id: BABA.staff.id, display_name: "Baba" });
    theServerHas(own, payRates([], null));

    render(<WorkerScreen id={own.id} />);
    const card = await theCard();

    expect(
      await within(card).findByText("Bado hana malipo kwa siku."),
    ).toBeTruthy();
    expect(within(card).queryByRole("button")).toBeNull();
  });

  it("offers no button for a worker who left", async () => {
    // Their pay up to their last day is worked out with the rates they had: the history stays, as it was.
    const gone = worker({
      started_on: "2026-11-10",
      status: "left",
      left_on: "2026-11-18",
    });
    const rate = payRate({ staff: gone.id });
    theServerHas(gone, payRates([rate], rate));

    render(<WorkerScreen id={gone.id} />);
    const card = await theCard();

    expect(
      await within(card).findByText(
        `Sasa: ${tsh("10000")} kwa siku · anachangia chakula`,
      ),
    ).toBeTruthy();
    expect(within(card).queryByRole("button")).toBeNull();
  });

  it("hides Weka malipo while another card's form is open in the page, and brings it back after", async () => {
    // One form at a time on the page (PPL-8's review): Badilisha or Ongeza kazi open in the page, Malipo kwa siku's
    // button stays off it, so a person never meets two Hifadhi; Ghairi brings it back. A sheet (Weka PIN, UI-10) shuts
    // the whole page off instead (worker-pin.test.tsx).
    theServerHas(JUMA, payRates([], null));
    answer("GET", ROLES_ROUTE, { status: 200, body: rolesPage(SHOP_ROLES) });
    answer("GET", "/api/devices/v1/demo/open/", {
      status: 200,
      body: { open: false },
    });

    render(<WorkerScreen id={JUMA.id} />);
    const card = await theCard();
    await within(card).findByRole("button", { name: "Weka malipo" });

    for (const other of ["Badilisha", "Ongeza kazi"]) {
      fireEvent.click(await screen.findByRole("button", { name: other }));
      await waitFor(() =>
        expect(
          within(card).queryByRole("button", { name: "Weka malipo" }),
        ).toBeNull(),
      );
      fireEvent.click(screen.getByRole("button", { name: "Ghairi" }));
      expect(
        await within(card).findByRole("button", { name: "Weka malipo" }),
      ).toBeTruthy();
    }
  });

  it("says why when the rates can't be read", async () => {
    answer("GET", ME, { status: 200, body: BABA });
    answer("GET", `${STAFF}${JUMA.id}/`, { status: 200, body: JUMA });
    answer("GET", PAY_RATES_ROUTE, refusal(403, "permission_denied"));

    render(<WorkerScreen id={JUMA.id} />);
    const card = await theCard();

    await waitFor(() => expect(within(card).getByRole("alert")).toBeTruthy());
    expect(within(card).queryByRole("button")).toBeNull();
  });
});
