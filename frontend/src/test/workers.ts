// workers.ts — made-up answers of GET /api/v1/people/staff/ for the workers' page's tests (PPL-6): a builder for a
// worker and one for a role, the manager who may open the page, and a page of the list. Tests only. For Ongeza kazi
// (PPL-8): the shop's roles as GET /api/v1/people/roles/ answers them, and two people who give: Baba, who holds every
// key, and Neema, who holds the Seller's keys and staff.manage on Dawa alone.
// Fake data: the made-up MPC of devices.ts, its Dawa and Vyakula sides, and made-up names.
import type { components } from "@/api/schema";
import { EVERY_KEY } from "@/features/workers/keys";

import { DAWA, VYAKULA, whoIsHere } from "./devices";

type Worker = components["schemas"]["Staff"];
type GivenRole = components["schemas"]["GivenRole"];
type Role = components["schemas"]["Role"];
type WhoIsHere = components["schemas"]["WhoIsHere"];

/** The list's address, as the tests answer it. */
export const STAFF = "/api/v1/people/staff/";

/** Neema, the manager `me` answers for: staff.manage on the whole shop, which the server also counts on every side
 * (HeldPermissions.on), so both lists hold it. */
export const MANAGER: components["schemas"]["WhoIsHere"] = {
  ...whoIsHere([]),
  permissions: {
    whole_shop: ["staff.manage"],
    sides: [
      { ...DAWA, permissions: ["staff.manage"] },
      { ...VYAKULA, permissions: ["staff.manage"] },
    ],
  },
};

let made = 0;

/** A role given to a worker: the template's, on one side, or on every side with `side` null. Each its own id. */
export function role(
  template: string,
  side: string | null,
  fields: Partial<GivenRole> = {},
): GivenRole {
  made += 1;
  return {
    id: `019a8300-0000-7000-8000-${String(made).padStart(12, "0")}`,
    role: `019a8301-0000-7000-8000-${String(made).padStart(12, "0")}`,
    template,
    // The server's own English name of a copied role, which the page shows only for a role of no template.
    name: template,
    side,
    ...fields,
  };
}

/** A worker as the list answers them: Juma, working since 2 Nov 2026 with no role, phone, PIN or photo yet, never
 * fixed since he was added (version 1), and never come back from, unless told otherwise. Each its own id. */
export function worker(fields: Partial<Worker> = {}): Worker {
  made += 1;
  return {
    id: `019a8302-0000-7000-8000-${String(made).padStart(12, "0")}`,
    full_name: "Juma Mfano",
    phone: null,
    display_name: "Juma",
    job_title: "",
    started_on: "2026-11-02",
    status: "active",
    left_on: null,
    switched_off: false,
    has_pin: false,
    photo: null,
    roles: [],
    keys: [],
    version: 1,
    hired_again_as: null,
    ...fields,
  };
}

/** One page of the list, the last unless `next` names the one after it. */
export function staffPage(
  workers: Worker[],
  next: string | null = null,
): components["schemas"]["PaginatedStaffList"] {
  return { next, previous: null, results: workers };
}

/** The roles' address, as the tests answer it (PPL-7). */
export const ROLES_ROUTE = "/api/v1/people/roles/";

/** The Seller's codes, as permissions.py's template has them. */
export const SELLER_CODES = [
  "sale.write",
  "sale.take_payment",
  "sale.hand_over",
  "sale.bargain",
  "sale.refund",
  "credit.give",
  "debt.view",
  "contact.manage",
  "stock.count",
  "stock.weigh",
  "drawer.count",
];

/** The owner's own four, which the Manager's template leaves out (permissions.py). */
const OWNERS_OWN = [
  "drawer.approve",
  "pay.approve",
  "settings.manage",
  "staff.manage",
];

/** One of the shop's roles, with its id and codes. */
export function shopRole(
  template: string,
  permissions: string[],
  fields: Partial<Role> = {},
): Role {
  made += 1;
  return {
    id: `019a8304-0000-7000-8000-${String(made).padStart(12, "0")}`,
    template,
    name: template,
    permissions,
    ...fields,
  };
}

/** The made-up shop's roles, as copied from the templates, and one the owner made himself with no template. */
export const OWNER_ROLE = shopRole("owner", [...EVERY_KEY]);
export const MANAGER_ROLE = shopRole(
  "manager",
  EVERY_KEY.filter((code) => !OWNERS_OWN.includes(code)),
);
export const SELLER_ROLE = shopRole("seller", SELLER_CODES);
export const CASHIER_ROLE = shopRole("cashier", [
  "sale.take_payment",
  "sale.write",
  "debt.view",
  "stock.weigh",
  "drawer.count",
]);
export const LOADER_ROLE = shopRole("", ["sale.hand_over", "stock.weigh"], {
  name: "Mbeba mizigo",
});

/** The roles as the server sends them: newest first, so the form must sort them. */
export const SHOP_ROLES = [
  LOADER_ROLE,
  CASHIER_ROLE,
  SELLER_ROLE,
  MANAGER_ROLE,
  OWNER_ROLE,
];

/** One page of the roles, the last. */
export function rolesPage(
  roles: Role[],
): components["schemas"]["PaginatedRoleList"] {
  return { next: null, previous: null, results: roles };
}

/** Baba, the owner: every key, on every side. */
export const BABA: WhoIsHere = {
  ...MANAGER,
  permissions: {
    whole_shop: [...EVERY_KEY],
    sides: [
      { ...DAWA, permissions: [...EVERY_KEY] },
      { ...VYAKULA, permissions: [...EVERY_KEY] },
    ],
  },
};

/** Neema, a Dawa seller trusted with the workers: staff.manage on the whole shop, which the workers' routes ask there
 * (PPL-4), so she can open the page at all, and the Seller's keys on Dawa alone. As `me` answers, staff.manage counts
 * on every side too (HeldPermissions.on). So she may give the Seller's roles and keys on Dawa, and on every side or on
 * Vyakula nothing but staff.manage itself (PPL-8's review). */
export const NEEMA_ON_DAWA: WhoIsHere = {
  ...MANAGER,
  permissions: {
    whole_shop: ["staff.manage"],
    sides: [
      { ...DAWA, permissions: ["staff.manage", ...SELLER_CODES] },
      { ...VYAKULA, permissions: ["staff.manage"] },
    ],
  },
};
