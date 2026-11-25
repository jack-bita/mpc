// pay-rates.ts — a worker's daily pay rates, for Malipo kwa siku on their page (WAGE-1): the rates' place in the store
// of server answers, the read of one worker's, and who may see them.
//
// The server answers a worker's rates newest first, the shop's today, and which rate is in force today, worked out on
// the shop's own date there, as a phone's date can be wrong (GET /api/v1/staffpay/pay-rates/?staff=…). Its route asks
// two keys, both on the whole shop, to see a worker's pay as to change it: settings.manage, the key to the shop's
// rules and rates, and staff.manage, the workers' (Jack, WAGE-1's review: A). So the card shows, and the page asks the
// rates, only for whoever holds both (maySeePay): a manager handed settings.manage only to change the late fine sees
// nobody's pay, whatever address he opens.

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import type { WhoIsHere } from "@/features/people/who-is-here";
import { Decimal } from "@/lib/decimal";

import { MANAGES_STAFF } from "./workers";

export type PayRate = components["schemas"]["PayRate"];
export type PayRates = components["schemas"]["PayRatesAnswer"];

/** The rates route's key, on the whole shop: one of the owner's own (spec §6). The other is MANAGES_STAFF. */
export const MANAGES_RATES = "settings.manage";

/** Every worker's rates' place in the store of server answers; a save asks them all again. */
export const PAY_RATES = ["staffpay", "pay-rates"] as const;

/** One worker's rates' place, under PAY_RATES. */
export function payRatesKey(id: string) {
  return [...PAY_RATES, id] as const;
}

/** Whether the person may see a worker's pay: settings.manage and staff.manage, both on the whole shop, as the route
 * asks them there, since a worker belongs to the whole shop. */
export function maySeePay(me: WhoIsHere): boolean {
  const held = me.permissions.whole_shop;
  return held.includes(MANAGES_RATES) && held.includes(MANAGES_STAFF);
}

/** The rates read by the page, the part always on it, and handed down by their values alone, as the roles are
 * (RolesRead, workers.ts): a card that asked for itself would ask again each time it mounted on a failed read. */
export type PayRatesRead = {
  data: PayRates | undefined;
  error: unknown;
  isPending: boolean;
};

/** One worker's rates, from the store of server answers: asked only once `enabled`, for someone who may see them, so
 * the page asks nothing the server would refuse. */
export function usePayRates(id: string | null, enabled: boolean) {
  return useQuery({
    queryKey: payRatesKey(id ?? ""),
    queryFn: () =>
      answerOf(
        api.GET("/api/v1/staffpay/pay-rates/", {
          params: { query: { staff: id ?? "" } },
        }),
      ),
    enabled: enabled && id !== null,
  });
}

/** A rate's amount as its box starts with it, on Badilisha malipo: "10000.00" → "10000", so a raise to 12,000 is a
 * change of one digit. */
export function startingAmount(rate: PayRate | undefined): string {
  return rate === undefined ? "" : new Decimal(rate.daily_rate).toString();
}
