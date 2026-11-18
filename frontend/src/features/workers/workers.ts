// workers.ts — the shop's workers as the office reads them (PPL-6, 03 §5.10): the list's place in the store of
// server answers, the reading of every page, one worker for their own page, a saved worker kept in both at once,
// the key the page asks, and the words for each role and its side.
//
// GET /api/v1/people/staff/ answers everyone the shop has had, those who left included, newest first, in pages of
// 50 (CursorPage, PPL-4). A shop has tens of workers over the years, not hundreds, so one screen holds them all,
// as Vifaa holds every device. The order is the server's, kept: a new worker comes first, where the owner who just
// added him looks.
//
// Behind staff.manage on the whole shop (PPL-4): the page shows each worker's roles, and later their pay (WAGE-2),
// which are the owner's to see. The office home offers the button only to someone holding it; the server asks the
// key again on every read and every change.
"use client";

import {
  type QueryClient,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import type { WhoIsHere } from "@/features/people/who-is-here";

export type Worker = components["schemas"]["Staff"];
export type GivenRole = components["schemas"]["GivenRole"];
type StaffPage = components["schemas"]["PaginatedStaffList"];

/** The key the workers' routes ask, on the whole shop: one of the owner's own four (spec §6). */
export const MANAGES_STAFF = "staff.manage";

/** The list's place in the store of server answers. Ongeza and each change ask it again. */
export const WORKERS = ["people", "staff"] as const;

/** Whether the person may open the workers' page: staff.manage on the whole shop, not on one side, as a worker
 * belongs to the shop, not to a side. */
export function mayManageStaff(me: WhoIsHere): boolean {
  return me.permissions.whole_shop.includes(MANAGES_STAFF);
}

/** Every worker the shop has had, page after page, in the server's order: newest first. */
async function allWorkers(): Promise<Worker[]> {
  const workers: Worker[] = [];
  let cursor: string | null = null;
  do {
    // Named, as TypeScript can't work out a type that the loop's own cursor feeds back into.
    const page: StaffPage = await answerOf(
      api.GET("/api/v1/people/staff/", {
        params: { query: cursor === null ? {} : { cursor } },
      }),
    );
    workers.push(...page.results);
    // The next page's address, in full; only its cursor is ours to send back.
    cursor = page.next ? new URL(page.next).searchParams.get("cursor") : null;
  } while (cursor !== null);
  return workers;
}

/** The shop's workers, from the store of server answers. */
export function useWorkers() {
  return useQuery({ queryKey: WORKERS, queryFn: allWorkers });
}

/** One worker's place in the store, under the list's: a change that asks the list again (invalidateQueries with
 * WORKERS) asks every worker's page again too, as TanStack matches a key by its start. */
export function workerKey(id: string) {
  return [...WORKERS, id] as const;
}

/** One worker, for their own page (GET /api/v1/people/staff/{id}/). No id in the address, nothing is asked. */
export function useWorker(id: string | null) {
  const store = useQueryClient();
  return useQuery({
    queryKey: workerKey(id ?? ""),
    queryFn: () =>
      answerOf(
        api.GET("/api/v1/people/staff/{id}/", {
          params: { path: { id: id ?? "" } },
        }),
      ),
    enabled: id !== null,
    // From the list at once, when the person came from it: the page shows with no wait while it asks the server, so
    // it soon shows the worker as they are now, whoever changed them. A placeholder, never initialData: TanStack
    // keeps a query's initialData as the state it goes back to, and forgetTheLastPerson's reset would put the last
    // person's copy back, for the next person to see, the buttons with it, beside their own refusal (UI-4, PPL-6's
    // review). A placeholder is never kept: a reset forgets it, and a refused read shows no worker.
    placeholderData: () =>
      store.getQueryData<Worker[]>(WORKERS)?.find((each) => each.id === id),
  });
}

/** A worker the server just answered with, in the list at once: a new one at the top, as the list comes newest
 * first; one already on it (a send tried again, a suspension) changed in its place. The list is asked again after,
 * so the server's own order settles it; until then the page never shows the list without the worker just saved,
 * even when that read fails (closures.ts keeps a closure the same way). Their own page gets the answer too. */
export function keepWorker(store: QueryClient, worker: Worker): void {
  store.setQueryData(workerKey(worker.id), worker);
  store.setQueryData<Worker[]>(
    WORKERS,
    (list) =>
      list &&
      (list.some((each) => each.id === worker.id)
        ? list.map((each) => (each.id === worker.id ? worker : each))
        : [worker, ...list]),
  );
}

/** The six roles every shop starts with, by the code of the template each was copied from (RoleTemplate,
 * backend/apps/core/permissions.py). Each has its words in both books; a role the owner made himself has no
 * template, and shows its own name. */
const ROLE_TEMPLATES = [
  "owner",
  "manager",
  "seller",
  "order_writer",
  "cashier",
  "worker",
] as const;
type RoleTemplate = (typeof ROLE_TEMPLATES)[number];

function isTemplate(code: string): code is RoleTemplate {
  return (ROLE_TEMPLATES as readonly string[]).includes(code);
}

/** How the page writes each role a worker holds, with its side: "Muuzaji (Dawa)", "Meneja (Pande zote)". */
export function useRoleWords(me: WhoIsHere) {
  const t = useTranslations("workers");
  // The sides' names, from `me`: whoever opens this page holds staff.manage on the whole shop, which the server
  // counts on every side, so `me` names every side a role can be on (MePermissionsSerializer).
  const sideNames = new Map(
    me.permissions.sides.map((side) => [side.id, side.name]),
  );

  /** A role's own name: its template's words in the person's language (ADR-0032), else the name the shop gave
   * it, as a role the owner made himself, or a template a newer server knows and this app doesn't yet. */
  function roleName(given: GivenRole): string {
    return isTemplate(given.template)
      ? t(`roles.${given.template}`)
      : given.name;
  }

  /** The role with its side. No side is every side. A side `me` doesn't name, which the key above rules out,
   * shows the role alone rather than an id. */
  function roleOnSide(given: GivenRole): string {
    if (given.side === null) {
      return t("roleOnSide", { role: roleName(given), side: t("allSides") });
    }
    const side = sideNames.get(given.side);
    return side === undefined
      ? roleName(given)
      : t("roleOnSide", { role: roleName(given), side });
  }

  return { roleName, roleOnSide };
}
