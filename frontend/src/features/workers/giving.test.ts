// giving.test.ts — what Ongeza kazi may offer (PPL-8): the giver rule of 02 §5, as the server's _check_giver has it,
// the Owner role never, nothing the worker already holds on that side, and each list narrowing the other.
import { describe, expect, it } from "vitest";

import { DAWA, VYAKULA } from "@/test/devices";
import {
  BABA,
  CASHIER_ROLE,
  LOADER_ROLE,
  MANAGER_ROLE,
  NEEMA_ON_DAWA,
  OWNER_ROLE,
  SELLER_ROLE,
  SHOP_ROLES,
  worker,
} from "@/test/workers";

import {
  everySide,
  heldOn,
  isOwnerRole,
  keysOffered,
  mayGive,
  rolesOffered,
  sidesOffered,
} from "./giving";
import { EVERY_KEY } from "./keys";

const JUMA = worker();

describe("the giver rule", () => {
  it("reads every side from the whole shop's codes, and a side from that side's", () => {
    // Every side: the whole shop's codes alone, staff.manage. Dawa: those, and the Seller's.
    expect([...heldOn(NEEMA_ON_DAWA, null)]).toEqual(["staff.manage"]);
    expect(heldOn(NEEMA_ON_DAWA, DAWA.id).has("stock.count")).toBe(true);
    expect([...heldOn(NEEMA_ON_DAWA, VYAKULA.id)]).toEqual(["staff.manage"]);
    // A side `me` doesn't name holds nothing.
    expect(heldOn(BABA, "019a0000-0000-7000-8000-000000000000").size).toBe(0);
  });

  it("asks staff.manage on that side, and every code there", () => {
    // Neema on Dawa: she holds the stock count, and staff.manage.
    expect(mayGive(NEEMA_ON_DAWA, ["stock.count"], DAWA.id)).toBe(true);
    // Not on every side, which would open Vyakula too, where she holds nothing.
    expect(mayGive(NEEMA_ON_DAWA, ["stock.count"], null)).toBe(false);
    // Not a code she lacks, even on Dawa.
    expect(mayGive(NEEMA_ON_DAWA, ["stock.count", "pay.run"], DAWA.id)).toBe(
      false,
    );
    // Without staff.manage there, nothing at all, though she holds the code. The rule's own branch: a person who could
    // open the page holds staff.manage on every side, so the form never meets this, but the server's rule has it.
    const noManage = {
      ...NEEMA_ON_DAWA,
      permissions: {
        whole_shop: [],
        sides: [{ ...DAWA, permissions: ["stock.count"] }],
      },
    };
    expect(mayGive(noManage, ["stock.count"], DAWA.id)).toBe(false);
  });

  it("asks a code this app doesn't know of the giver too, never assumes it", () => {
    // A newer server's code in a role: offered only if the giver holds it, never assumed.
    expect(mayGive(BABA, ["seed.sow"], null)).toBe(false);
  });

  it("lists every side, every side first", () => {
    expect(everySide(BABA)).toEqual([null, DAWA.id, VYAKULA.id]);
  });
});

describe("the roles offered", () => {
  it("never offers the Owner role, even to the owner (the card's third Done when)", () => {
    expect(isOwnerRole(OWNER_ROLE)).toBe(true);
    expect(rolesOffered(SHOP_ROLES, BABA, JUMA, undefined)).not.toContain(
      OWNER_ROLE,
    );
    expect(rolesOffered(SHOP_ROLES, BABA, JUMA, null)).not.toContain(
      OWNER_ROLE,
    );
  });

  it("sorts them as the templates come, then the shop's own, whatever the server's order", () => {
    expect(
      rolesOffered(SHOP_ROLES, BABA, JUMA, DAWA.id).map((role) => role.id),
    ).toEqual([
      MANAGER_ROLE.id,
      SELLER_ROLE.id,
      CASHIER_ROLE.id,
      LOADER_ROLE.id,
    ]);
  });

  it("offers only a role whose every code the giver holds on that side", () => {
    // Neema holds the Seller's codes on Dawa: the Seller, and the Cashier and the loader, whose codes the Seller's
    // all include. The rule compares codes, never the roles' names.
    expect(rolesOffered(SHOP_ROLES, NEEMA_ON_DAWA, JUMA, DAWA.id)).toEqual([
      SELLER_ROLE,
      CASHIER_ROLE,
      LOADER_ROLE,
    ]);
    // On every side, or on Vyakula, nothing.
    expect(rolesOffered(SHOP_ROLES, NEEMA_ON_DAWA, JUMA, null)).toEqual([]);
    expect(rolesOffered(SHOP_ROLES, NEEMA_ON_DAWA, JUMA, VYAKULA.id)).toEqual(
      [],
    );
    // With no side picked yet: what she may give somewhere.
    expect(rolesOffered(SHOP_ROLES, NEEMA_ON_DAWA, JUMA, undefined)).toEqual([
      SELLER_ROLE,
      CASHIER_ROLE,
      LOADER_ROLE,
    ]);
  });

  it("leaves out a role the worker already holds on that very side, and only there", () => {
    const seller = worker({
      roles: [
        {
          id: "019a8300-0000-7000-8000-000000009999",
          role: SELLER_ROLE.id,
          template: "seller",
          name: "seller",
          side: DAWA.id,
        },
      ],
    });
    expect(rolesOffered(SHOP_ROLES, BABA, seller, DAWA.id)).not.toContain(
      SELLER_ROLE,
    );
    expect(rolesOffered(SHOP_ROLES, BABA, seller, VYAKULA.id)).toContain(
      SELLER_ROLE,
    );
    // Somewhere is still somewhere.
    expect(rolesOffered(SHOP_ROLES, BABA, seller, undefined)).toContain(
      SELLER_ROLE,
    );
  });
});

describe("the keys offered", () => {
  it("offers every key to the owner, in permissions.py's order", () => {
    expect(keysOffered(BABA, JUMA, null)).toEqual(EVERY_KEY);
  });

  it("offers only the keys the giver holds on that side", () => {
    expect(keysOffered(NEEMA_ON_DAWA, JUMA, DAWA.id)).toEqual(
      EVERY_KEY.filter((code) =>
        ["staff.manage", ...SELLER_ROLE.permissions].includes(code),
      ),
    );
    // On every side, only what she holds there: staff.manage itself.
    expect(keysOffered(NEEMA_ON_DAWA, JUMA, null)).toEqual(["staff.manage"]);
    expect(keysOffered(NEEMA_ON_DAWA, JUMA, VYAKULA.id)).toEqual([
      "staff.manage",
    ]);
  });

  it("leaves out a key the worker already holds on that very side", () => {
    const counter = worker({
      keys: [
        {
          id: "019a8303-0000-7000-8000-000000009999",
          permission: "stock.count",
          side: null,
        },
      ],
    });
    expect(keysOffered(BABA, counter, null)).not.toContain("stock.count");
    expect(keysOffered(BABA, counter, DAWA.id)).toContain("stock.count");
  });
});

describe("the sides offered", () => {
  it("offers every side while nothing is picked", () => {
    expect(sidesOffered(NEEMA_ON_DAWA, JUMA, undefined)).toEqual([
      null,
      DAWA.id,
      VYAKULA.id,
    ]);
  });

  it("offers only the sides where the pick may be given", () => {
    expect(
      sidesOffered(NEEMA_ON_DAWA, JUMA, { kind: "role", role: SELLER_ROLE }),
    ).toEqual([DAWA.id]);
    expect(
      sidesOffered(BABA, JUMA, { kind: "key", key: "stock.count" }),
    ).toEqual([null, DAWA.id, VYAKULA.id]);
  });

  it("leaves out the side where the worker already holds the pick", () => {
    const counter = worker({
      keys: [
        {
          id: "019a8303-0000-7000-8000-000000009998",
          permission: "stock.count",
          side: DAWA.id,
        },
      ],
    });
    expect(
      sidesOffered(BABA, counter, { kind: "key", key: "stock.count" }),
    ).toEqual([null, VYAKULA.id]);
  });
});
