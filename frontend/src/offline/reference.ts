// reference.ts — live hooks for the shop's lists on this laptop: sides, payment accounts, staff, and a
// rule's value today (SYNC-7, 03 §6.1).
//
// Counter screens read only the laptop's database, never the server (rule 5, ADR-0019), so they work the
// same offline. Each hook reads through useLiveQuery (dexie-react-hooks): Dexie watches what the query
// read, and when a pull changes it, the query runs again and the screen redraws. A name changed in the
// office shows at the counter after the next pull, with no reload.
//
// Each hook gives undefined while its first read runs, or while the device isn't registered; then the
// list, empty if the laptop holds none.
import { useLiveQuery } from "dexie-react-hooks";

import type { components } from "@/api/schema";
import { useThisDevice } from "@/features/devices/this-device";

import { ruleInForce, shopToday } from "./rules";
import { CLOCK_OFFSET } from "./sync/meta";
import { useShopDatabase } from "./this-shop";

type Schemas = components["schemas"];

/** The shop's sides, open and closed: a screen shows `is_live` as it needs. */
export function useSides(): Schemas["SideRecord"][] | undefined {
  const db = useShopDatabase();
  return useLiveQuery(async () => db?.side.toArray(), [db]);
}

/** The shop's payment accounts: drawers, mobile money and banks, each with the sides it serves. */
export function usePaymentAccounts():
  Schemas["PaymentAccountRecord"][] | undefined {
  const db = useShopDatabase();
  return useLiveQuery(async () => db?.payment_account.toArray(), [db]);
}

/** The shop's staff on this laptop: active and suspended. Someone who left, or was switched off, was
 * taken off by the pull (SYNC-3), so never shows. */
export function useStaff(): Schemas["StaffRecord"][] | undefined {
  const db = useShopDatabase();
  return useLiveQuery(async () => db?.staff.toArray(), [db]);
}

/**
 * A rule's value in force today, as stored text, for a side or the whole shop (side null): rules.ts says
 * how it is chosen. Its kind (setting_keys) says how to read the text: a screen reads "15" for
 * session.idle_minutes as a whole number. Undefined too for a rule the laptop doesn't know.
 *
 * Today is the shop's day, on the server's clock as far as the laptop knows it (the offset the last
 * pull kept): a laptop whose clock is wrong still turns to a new rule on the right day.
 *
 * Honest limit: the query runs again when the rows change, not when midnight passes; a screen left open
 * across midnight shows yesterday's value until it draws again or a pull changes a rule.
 */
export function useRule(key: string, side: string | null): string | undefined {
  const db = useShopDatabase();
  const timezone = useThisDevice()?.shop.timezone;
  return useLiveQuery(async () => {
    if (db === null || timezone === undefined) return undefined;
    // One read transaction, so the rows, the rule and the offset are seen as they stood together.
    return db.transaction(
      "r",
      [db.setting, db.setting_keys, db.meta],
      async () => {
        const rule = await db.setting_keys.get(key);
        if (rule === undefined) return undefined;
        const rows = await db.setting.where("key").equals(key).toArray();
        const offset = (await db.meta.get(CLOCK_OFFSET))?.value;
        const now = Date.now() + (typeof offset === "number" ? offset : 0);
        return ruleInForce(rows, rule, side, shopToday(timezone, now));
      },
    );
  }, [db, key, side, timezone]);
}
