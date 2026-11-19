// giving.ts — what Ongeza kazi may offer (PPL-8): the giver rule of 02 §5, read from `me`, as plain functions of what
// they are handed, with no screen and no server, so each rule has its own test (giving.test.ts).
//
// The rule is the server's (`_check_giver`, backend/apps/people/services.py): whoever gives needs staff.manage on that
// side, and may give only codes they hold there themselves. On one side, a person holds what was given there plus
// what was given on every side; on "every side", only what was given on every side (HeldPermissions.on). `me` sends
// both, read the same way: `permissions.sides[].permissions` for a side, `permissions.whole_shop` for every side.
// So Neema, who holds the Seller's codes on Dawa alone, may give the Seller role on Dawa, not on every side, as that
// would open Vyakula too, where she holds nothing.
//
// The server checks it all again on each give: this only keeps off the screen what it would refuse (the card's
// default), so a manager meets the bare 403 almost never. Two more things stay off: the Owner role, which only the
// superuser gives (role.superuser_only, PPL-7, PPL-13); and what the worker already holds on that very side, which
// the server would refuse as role.already_given or permission.already_given.
//
// Each list can narrow the other: picking a side leaves the roles and keys that may be given there; picking a role or
// a key leaves the sides where it may be. So whatever the person has picked always fits together, whichever they
// picked first; Jack's order on screen is the role or the key, then the side.
import type { WhoIsHere } from "@/features/people/who-is-here";

import { EVERY_KEY, type Permission } from "./keys";
import {
  MANAGES_STAFF,
  type Role,
  ROLE_TEMPLATES,
  type Worker,
} from "./workers";

/** A side's id, or null for every side: as the server's `side`, where empty is every side, a side added later
 * included (PPL-7). */
export type Side = string | null;

/** What is given: a role of the shop's, or one extra key. */
export type Giving =
  { kind: "role"; role: Role } | { kind: "key"; key: Permission };

/** Whether a role was copied from the Owner's template: the superuser's alone to give and to take away (PPL-7), so no
 * button of a shop's ever offers it. */
export function isOwnerRole(role: { template: string }): boolean {
  return role.template === "owner";
}

/** Every side a give may name, every side first, as the form lists them: `me` names every side, as the person
 * holds staff.manage on the whole shop to open the page at all (mayManageStaff). */
export function everySide(me: WhoIsHere): Side[] {
  return [null, ...me.permissions.sides.map((side) => side.id)];
}

/** The codes the person holds on a side, or on every side (HeldPermissions.on). A side `me` doesn't name holds
 * nothing. */
export function heldOn(me: WhoIsHere, side: Side): ReadonlySet<string> {
  if (side === null) return new Set(me.permissions.whole_shop);
  const found = me.permissions.sides.find((each) => each.id === side);
  return new Set(found?.permissions ?? []);
}

/** Whether the person may give these codes on that side: staff.manage there, and every code (_check_giver). Every
 * code, a code this app doesn't know included: the server compares only codes it knows, so a newer code is held to
 * the stricter rule here, and the form offers less, never more. */
export function mayGive(
  me: WhoIsHere,
  codes: readonly string[],
  side: Side,
): boolean {
  const held = heldOn(me, side);
  return held.has(MANAGES_STAFF) && codes.every((code) => held.has(code));
}

/** The codes a give hands over. */
function codesOf(giving: Giving): readonly string[] {
  return giving.kind === "role" ? giving.role.permissions : [giving.key];
}

/** Whether the worker already holds this very role or key on this very side: the server's once rules (role.
 * already_given, permission.already_given). A role on every side doesn't rule out the same role on Dawa, as the
 * server allows both. */
function alreadyGiven(worker: Worker, giving: Giving, side: Side): boolean {
  return giving.kind === "role"
    ? worker.roles.some(
        (given) => given.role === giving.role.id && given.side === side,
      )
    : worker.keys.some(
        (given) => given.permission === giving.key && given.side === side,
      );
}

/** Whether the form offers this give on this side. */
export function offeredOn(
  me: WhoIsHere,
  worker: Worker,
  giving: Giving,
  side: Side,
): boolean {
  if (giving.kind === "role" && isOwnerRole(giving.role)) return false;
  return (
    mayGive(me, codesOf(giving), side) && !alreadyGiven(worker, giving, side)
  );
}

/** On the side picked, or, with none picked yet (undefined), on at least one side. */
function offeredWhere(
  me: WhoIsHere,
  worker: Worker,
  giving: Giving,
  side: Side | undefined,
): boolean {
  return side === undefined
    ? everySide(me).some((each) => offeredOn(me, worker, giving, each))
    : offeredOn(me, worker, giving, side);
}

/** Where a role sorts: the templates' order (ADR-0032), then any role with a name of its own. */
function placeOf(role: Role): number {
  const place = (ROLE_TEMPLATES as readonly string[]).indexOf(role.template);
  return place === -1 ? ROLE_TEMPLATES.length : place;
}

/** The roles the form offers, sorted: the server sends them newest first (PPL-7), the form lists them as the templates
 * come, manager to worker, then the roles the owner made himself, by name. */
export function rolesOffered(
  roles: readonly Role[],
  me: WhoIsHere,
  worker: Worker,
  side: Side | undefined,
): Role[] {
  return roles
    .filter((role) => offeredWhere(me, worker, { kind: "role", role }, side))
    .sort(
      (a, b) => placeOf(a) - placeOf(b) || a.name.localeCompare(b.name, "en"),
    );
}

/** The keys the form offers, in permissions.py's order (keys.ts groups them on screen). */
export function keysOffered(
  me: WhoIsHere,
  worker: Worker,
  side: Side | undefined,
): Permission[] {
  return EVERY_KEY.filter((key) =>
    offeredWhere(me, worker, { kind: "key", key }, side),
  );
}

/** The sides the form offers: with nothing picked yet, every side; else those where the pick may be given. */
export function sidesOffered(
  me: WhoIsHere,
  worker: Worker,
  giving: Giving | undefined,
): Side[] {
  return everySide(me).filter(
    (side) => giving === undefined || offeredOn(me, worker, giving, side),
  );
}
