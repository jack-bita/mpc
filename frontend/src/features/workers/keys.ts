// keys.ts — the extra keys (permission codes) as the workers' pages show them (PPL-8): each code's group, in the
// order the server lists them, and the words for a key with its side, "Kuhesabu mzigo (Vyakula)".
//
// A key is one action a person may do, named by a code ("stock.count"); a role is a named bundle of them (02 §5). The
// codes are a fixed list on the server (Permission, backend/apps/core/permissions.py), and the API's schema hands
// that list to the app as a type (PermissionEnum), so this file holds no list of its own to forget: GROUP_OF is a
// Record over that type, which TypeScript fills only when every code is in it. A card that adds a code on the server
// runs `pnpm gen:api`, and `pnpm typecheck` then fails here until the code has its group, and in the word books
// until it has its name (use-intl's typed keys, i18n/language.ts). permission-words.test.ts checks the same against
// shared/openapi.json at run time, so the screen never shows a key blank (the card's Watch out).
//
// The groups are the server's own headings in permissions.py, in its order (PPL-8): eight of them. They are the
// app's to keep, as the server sends no group: one more way of showing the same codes, not a rule.
//
// "use client": it asks use-intl for words (use-client.test.ts).
"use client";

import { useTranslations } from "use-intl";

import type { components } from "@/api/schema";
import type { WhoIsHere } from "@/features/people/who-is-here";

import { useOnSide } from "./workers";

export type Permission = components["schemas"]["PermissionEnum"];
export type GivenKey = components["schemas"]["GivenKey"];

/** The eight groups, in the order permissions.py lists them: what a manager looks for first comes first. */
export const KEY_GROUPS = [
  "selling",
  "credit",
  "products",
  "stock",
  "money",
  "staff",
  "shop",
  "production",
] as const;
export type KeyGroup = (typeof KEY_GROUPS)[number];

/** Each code's group, written in permissions.py's own order, which a JavaScript object keeps (its keys are words,
 * not numbers). A Record over every code: one left out, or one the server no longer has, fails `pnpm typecheck`. */
const GROUP_OF: Record<Permission, KeyGroup> = {
  // Selling (02 §9).
  "sale.write": "selling",
  "sale.take_payment": "selling",
  "sale.hand_over": "selling",
  "sale.bargain": "selling",
  "sale.below_floor_approve": "selling",
  "sale.jumla_switch": "selling",
  "sale.cancel": "selling",
  "sale.refund": "selling",
  // Credit and debts (02 §8).
  "credit.give": "credit",
  "credit.approve": "credit",
  "debt.view": "credit",
  "debt.adjust": "credit",
  // Products and prices (02 §6), contacts (02 §8).
  "price.change": "products",
  "cost.view": "products",
  "product.manage": "products",
  "contact.manage": "products",
  // Stock (02 §7).
  "stock.receive": "stock",
  "stock.weigh": "stock",
  "stock.loss": "stock",
  "stock.count": "stock",
  "stock.count_approve": "stock",
  "stock.transfer": "stock",
  // Money and drawers (02 §10).
  "money.expense": "money",
  "money.advance": "money",
  "money.withdraw": "money",
  "drawer.count": "money",
  "drawer.confirm": "money",
  "drawer.approve": "money",
  // Staff, attendance and pay (02 §5, §12).
  "staff.manage": "staff",
  "attendance.manage": "staff",
  "meals.record": "staff",
  "pay.run": "staff",
  "pay.approve": "staff",
  // The shop itself (02 §4, §5, §13).
  "settings.manage": "shop",
  "device.manage": "shop",
  "flag.review": "shop",
  "report.view": "shop",
  // Release 2: machine jobs and production (02 §11).
  "job.manage": "production",
  "production.run": "production",
};

/** Every code, in permissions.py's order. */
export const EVERY_KEY = Object.keys(GROUP_OF) as Permission[];

/** Whether a code is one this app knows. A GivenKey's `permission` is any text in the schema: a newer server may
 * send a code this app hasn't been built with yet. */
export function isPermission(code: string): code is Permission {
  return Object.hasOwn(GROUP_OF, code);
}

/** The group a code belongs to. */
export function groupOf(code: Permission): KeyGroup {
  return GROUP_OF[code];
}

/** How the page writes a key and its side: "Kuhesabu mzigo (Vyakula)", "Kupokea malipo (Pande zote)". */
export function useKeyWords(me: WhoIsHere) {
  const t = useTranslations("workers");
  const onSide = useOnSide(me);

  /** A key's own name, in the person's language. A code this app doesn't know yet shows as the code itself, which
   * a manager can still read, rather than nothing. */
  function keyName(code: string): string {
    return isPermission(code) ? t(`keys.${code}`) : code;
  }

  /** The key with its side, as a role shows (useRoleWords). */
  function keyOnSide(given: GivenKey): string {
    return onSide(keyName(given.permission), given.side);
  }

  /** A group's heading. */
  function groupName(group: KeyGroup): string {
    return t(`keyGroups.${group}`);
  }

  return { keyName, keyOnSide, groupName };
}
