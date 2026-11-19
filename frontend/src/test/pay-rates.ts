// pay-rates.ts — made-up pay rates and the rates route's answer, for the tests of Malipo kwa siku (WAGE-1). Tests only.
// The amounts are made up: the repo is public (rule 10).
import type { components } from "@/api/schema";

type PayRate = components["schemas"]["PayRate"];
type PayRates = components["schemas"]["PayRatesAnswer"];

/** The rates route, as the page calls it (?staff=… comes on top). */
export const PAY_RATES_ROUTE = "/api/v1/staffpay/pay-rates/";

/** The shop's today, as the rates route answers it: 19 Nov 2026. */
export const TODAY = "2026-11-19";

let made = 0;

/** A rate as the route answers it: 10,000 a day from 10 Nov 2026, sharing the meals, with no note, set by Baba,
 * unless told otherwise. Each its own id. */
export function payRate(fields: Partial<PayRate> = {}): PayRate {
  made += 1;
  return {
    id: `019a8310-0000-7000-8000-${String(made).padStart(12, "0")}`,
    staff: "019a8302-0000-7000-8000-000000000000",
    daily_rate: "10000.00",
    shares_meals: true,
    effective_from: "2026-11-10",
    note: "",
    set_by: "Baba",
    created_at: "2026-11-19T05:00:00Z",
    ...fields,
  };
}

/** The route's answer: `rates` newest first, as the server sends them, and the one in force today. */
export function payRates(rates: PayRate[], inForce: PayRate | null): PayRates {
  return { today: TODAY, in_force: inForce?.id ?? null, rates };
}
