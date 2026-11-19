// pay-rates.ts — a worker's daily pay rates, for Malipo kwa siku on their page (WAGE-1): the rates' place in the store
// of server answers, the read of one worker's, who may see them, and how a rate's amount is typed.
//
// The server answers a worker's rates newest first, the shop's today, and which rate is in force today, worked out on
// the shop's own date there, as a phone's date can be wrong (GET /api/v1/staffpay/pay-rates/?staff=…). Its route asks
// settings.manage on the whole shop, the key to the shop's rules and rates, and setting one asks staff.manage too
// (set_pay_rate): the page opens only for staff.manage already (mayManageStaff), so the card shows to whoever holds
// settings.manage there.

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import type { WhoIsHere } from "@/features/people/who-is-here";
import { Decimal } from "@/lib/decimal";

export type PayRate = components["schemas"]["PayRate"];
export type PayRates = components["schemas"]["PayRatesAnswer"];

/** The key the rates' route asks, on the whole shop: one of the owner's own four (spec §6). */
export const MANAGES_RATES = "settings.manage";

/** Every worker's rates' place in the store of server answers; a save asks them all again. */
export const PAY_RATES = ["staffpay", "pay-rates"] as const;

/** One worker's rates' place, under PAY_RATES. */
export function payRatesKey(id: string) {
  return [...PAY_RATES, id] as const;
}

/** Whether the person may see a worker's pay: settings.manage on the whole shop, as the route asks it there, since a
 * worker belongs to the whole shop. */
export function maySeePay(me: WhoIsHere): boolean {
  return me.permissions.whole_shop.includes(MANAGES_RATES);
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

/** Whole shillings, as Baba types them, "10,000", "10 000" or "10000": the digits, as the server takes them, or null
 * for anything else. The same shapes as a money rule's box (setting-form.tsx): a point and cents are refused, as a
 * day's pay has none (Jack, 16 Nov 2026). */
const WHOLE = /^(\d+|[1-9]\d{0,2}([, ]\d{3})+)$/;
export function typedAmount(typed: string): string | null {
  const trimmed = typed.trim();
  if (!WHOLE.test(trimmed)) return null;
  const digits = trimmed.replace(/[, ]/g, "");
  // Above nothing, as the server asks (pay_rate.amount_invalid): "0" and "000" are no pay. "0" as text: the shared
  // Decimal is strict, and refuses a plain number, so no float ever reaches money (rule 3).
  return new Decimal(digits).gt("0") ? digits : null;
}

/** A rate's amount as its box starts with it, on Badilisha malipo: "10000.00" → "10000", so a raise to 12,000 is a
 * change of one digit. */
export function startingAmount(rate: PayRate | undefined): string {
  return rate === undefined ? "" : new Decimal(rate.daily_rate).toString();
}
