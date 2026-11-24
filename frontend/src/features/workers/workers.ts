// workers.ts — the shop's workers as the office reads them (PPL-6, 03 §5.10): the list's place in the store of
// server answers, the reading of every page, one worker for their own page and its address, a saved worker kept in
// both at once, the key the page asks, and the words for each role and its side. For PPL-8: the shop's roles, read by
// Ongeza kazi's own page (ROLES, useRoles, RolesRead, handed down as values, UI-11), how a role or a key is written on
// its side (useOnSide). For UI-11: each long form's own page's address, and the way back from it (backToWorker).
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

import type { useRouter } from "next/navigation";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import { mayGoBack } from "@/components/in-app-moves";
import type { WhoIsHere } from "@/features/people/who-is-here";

export type Worker = components["schemas"]["Staff"];
export type GivenRole = components["schemas"]["GivenRole"];
/** One of the shop's roles, with its codes, as Ongeza kazi offers it (GET /api/v1/people/roles/, PPL-7). */
export type Role = components["schemas"]["Role"];
type StaffPage = components["schemas"]["PaginatedStaffList"];
type RolePage = components["schemas"]["PaginatedRoleList"];

/** The key the workers' routes ask, on the whole shop: one of the owner's own four (spec §6). */
export const MANAGES_STAFF = "staff.manage";

/** The list's place in the store of server answers. Ongeza and each change ask it again. */
export const WORKERS = ["people", "staff"] as const;

/** Wafanyakazi, the list: where a worker's page and Mfanyakazi mpya lead back when the person didn't come from inside
 * the app. */
export const LIST_PAGE = "/workers/";

/** Mfanyakazi mpya, Ongeza's own page (UI-11). */
export const NEW_WORKER_PAGE = "/workers/new/";

/** Mwajiri tena's page, Ongeza's own with the job that ended (UI-11): the person hired again keeps his own full name
 * and phone, so the same page asks only the new job's boxes. */
export function hireAgainPage(oldJob: string): string {
  return `${NEW_WORKER_PAGE}?again=${oldJob}`;
}

/** A worker's own page, by their job's id: a query string, as the app is plain files with no page per id (ADR-0016).
 * The list's names link to it, and so do a job that ended and the page Mwajiri tena moves to (PPL-11). */
export function workerPage(id: string): string {
  return `/workers/view/?id=${id}`;
}

/** Badilisha's own page, for one worker (UI-11). */
export function editWorkerPage(id: string): string {
  return `/workers/edit/?id=${id}`;
}

/** Ongeza kazi's own page, for one worker (UI-11). */
export function giveWorkerPage(id: string): string {
  return `/workers/give/?id=${id}`;
}

/** Hifadhi on a form's own page (UI-11) goes where the page's arrow goes: back to the worker's page the person came
 * from, or, from a bookmark, to that page in the form's place (replace), so the form's page never sits in the tab's
 * history between the list and the worker, and the arrow on the worker's page never leads back into a form already
 * sent. */
export function backToWorker(
  router: ReturnType<typeof useRouter>,
  id: string,
): void {
  if (mayGoBack()) router.back();
  else router.replace(workerPage(id));
}

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

/** The shop's roles' place in the store: apart from the workers', as a change to a worker changes no role. */
export const ROLES = ["people", "roles"] as const;

/** Every role the shop has, page after page: six at first, each a copy of a template (set_up_shop), and later any the
 * owner makes himself (parking lot item 26). Behind staff.manage on the whole shop, as the workers' list is. */
async function allRoles(): Promise<Role[]> {
  const roles: Role[] = [];
  let cursor: string | null = null;
  do {
    // Named, as TypeScript can't work out a type that the loop's own cursor feeds back into (allWorkers).
    const page: RolePage = await answerOf(
      api.GET("/api/v1/people/roles/", {
        params: { query: cursor === null ? {} : { cursor } },
      }),
    );
    roles.push(...page.results);
    cursor = page.next ? new URL(page.next).searchParams.get("cursor") : null;
  } while (cursor !== null);
  return roles;
}

/** The roles' read as the page hands it down: its three values, read by the page itself (give-screen.tsx). Never the
 * query's whole result: TanStack draws a part again only when a value that part has read changes, so a result handed
 * down and read only later, by a form that opened after the read had failed, kept showing it on its way (PPL-8's
 * review). */
export type RolesRead = {
  data: Role[] | undefined;
  error: unknown;
  isPending: boolean;
};

/** The shop's roles, for Ongeza kazi (PPL-8): asked by its own page from its first draw, the part always on the screen,
 * and handed down (give-screen.tsx, UI-11), so opening a worker's page costs no read of them; only once `enabled`, as a
 * page with no worker to give to asks nothing. */
export function useRoles(enabled: boolean) {
  return useQuery({ queryKey: ROLES, queryFn: allRoles, enabled });
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
export const ROLE_TEMPLATES = [
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

/** How the page writes a role or a key on its side (PPL-8): "Muuzaji (Dawa)", "Meneja (Pande zote)". One rule for
 * both, so a role and a key on the same side read alike. */
export function useOnSide(me: WhoIsHere) {
  const t = useTranslations("workers");
  // The sides' names, from `me`: whoever opens this page holds staff.manage on the whole shop, which the server
  // counts on every side, so `me` names every side a role can be on (MePermissionsSerializer).
  const sideNames = new Map(
    me.permissions.sides.map((side) => [side.id, side.name]),
  );

  /** A name with its side. No side is every side. A side `me` doesn't name, which the key above rules out, shows
   * the name alone rather than an id. */
  return function onSide(name: string, sideId: string | null): string {
    if (sideId === null) {
      return t("roleOnSide", { role: name, side: t("allSides") });
    }
    const side = sideNames.get(sideId);
    return side === undefined ? name : t("roleOnSide", { role: name, side });
  };
}

/** How the page writes each role a worker holds, with its side: "Muuzaji (Dawa)", "Meneja (Pande zote)". */
export function useRoleWords(me: WhoIsHere) {
  const t = useTranslations("workers");
  const onSide = useOnSide(me);

  /** A role's own name: its template's words in the person's language (ADR-0032), else the name the shop gave
   * it, as a role the owner made himself, or a template a newer server knows and this app doesn't yet. */
  function roleName(given: { template: string; name: string }): string {
    return isTemplate(given.template)
      ? t(`roles.${given.template}`)
      : given.name;
  }

  /** The role with its side. */
  function roleOnSide(given: GivenRole): string {
    return onSide(roleName(given), given.side);
  }

  return { roleName, roleOnSide };
}
