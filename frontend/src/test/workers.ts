// workers.ts — made-up answers of GET /api/v1/people/staff/ for the workers' page's tests (PPL-6): a builder for a
// worker and one for a role, the manager who may open the page, and a page of the list. Tests only.
// Fake data: the made-up MPC of devices.ts, its Dawa and Vyakula sides, and made-up names.
import type { components } from "@/api/schema";

import { DAWA, VYAKULA, whoIsHere } from "./devices";

type Worker = components["schemas"]["Staff"];
type GivenRole = components["schemas"]["GivenRole"];

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

/** A worker as the list answers them: Juma, working since 2 Nov 2026 with no role and no phone yet, never fixed
 * since he was added (version 1), unless told otherwise. Each its own id. */
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
    roles: [],
    keys: [],
    version: 1,
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
