// flags.ts — made-up answers of GET /api/v1/control/flags/ for Tofauti's tests (CTRL-4): a line of the list, a page of
// it, one flag whole with a note, and the manager who may open it. Tests only. Fake data: the made-up MPC of devices.ts,
// its sides, and made-up names.
import type { components } from "@/api/schema";

import { DAWA, VYAKULA, whoIsHere } from "./devices";

type FlagLine = components["schemas"]["FlagLine"];
type Flag = components["schemas"]["Flag"];
type FlagNote = components["schemas"]["FlagNote"];

/** The list's address, as the tests answer it. */
export const FLAGS_ROUTE = "/api/v1/control/flags/";

/** Neema, the manager `me` answers for: flag.review on the whole shop, which the server also counts on every side. */
export const REVIEWER: components["schemas"]["WhoIsHere"] = {
  ...whoIsHere([]),
  permissions: {
    whole_shop: ["flag.review"],
    sides: [
      { ...DAWA, permissions: ["flag.review"] },
      { ...VYAKULA, permissions: ["flag.review"] },
    ],
  },
};

let made = 0;

/** A line of the list: Juma, suspended, tapped on the Dawa laptop at 07:52 on Sunday 22 November, unless told
 * otherwise. Each its own id. */
export function flagLine(fields: Partial<FlagLine> = {}): FlagLine {
  made += 1;
  return {
    id: `019a8310-0000-7000-8000-${String(made).padStart(12, "0")}`,
    kind: "suspended_staff_activity",
    status: "open",
    side: "Dawa",
    people: ["Juma"],
    device: "Laptop Dawa",
    made_at: "2026-11-22T04:52:00Z",
    raised_at: "2026-11-23T06:10:00Z",
    ...fields,
  };
}

/** One page of the list, the last unless `next` names the one after it; as many wait as it holds, unless told. */
export function flagsPage(
  lines: FlagLine[],
  {
    waiting = lines.length,
    next = null,
  }: { waiting?: number; next?: string | null } = {},
): components["schemas"]["PaginatedFlagLineList"] {
  return { next, previous: null, results: lines, waiting };
}

/** One flag whole: that same tap of Juma's, with its day to open and nothing written yet, unless told otherwise. */
export function flag(fields: Partial<Flag> = {}): Flag {
  return {
    ...flagLine(),
    expected: null,
    actual: null,
    difference: null,
    // 07:52 by the time the server trusts, as the laptop's own clock says too (made_at).
    tap: { staff: JUMA_JOB, kind: "in", day: "2026-11-22", time: "07:52" },
    refused_for: "",
    brought_from: null,
    loaded_by: null,
    about_loading: false,
    notes: [],
    names_you: false,
    ready_notes: [],
    ...fields,
  };
}

/** Juma's job, as the attendance pages' address names it. */
export const JUMA_JOB = "019a8311-0000-7000-8000-000000000001";

/** A note: Neema's explanation, on 23 November at 09:10, unless told otherwise. Each its own id. */
export function flagNote(fields: Partial<FlagNote> = {}): FlagNote {
  made += 1;
  return {
    id: `019a8312-0000-7000-8000-${String(made).padStart(12, "0")}`,
    step: "explained",
    text: "Alikuja kuchukua vitu vyake tu.",
    by: "Neema",
    at: "2026-11-23T06:10:00Z",
    ...fields,
  };
}

/** One flag's address, as the tests answer it. */
export const flagRoute = (id: string) => `${FLAGS_ROUTE}${id}/`;
