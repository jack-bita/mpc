// sync.test.ts — one sync of the laptop's shop (SYNC-7): the bootstrap once, then pulls; a second check
// while one runs joins it; a failed one leaves the next free to run.
import { describe, expect, it, vi } from "vitest";

import { DAWA_LAPTOP } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { BOOTSTRAP } from "@/test/shop-lists";

import { shopDatabase } from "../this-shop";
import { readCursor } from "./meta";
import { syncShop } from "./sync";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const SHOP = DAWA_LAPTOP.shop.id;
const BOOTSTRAP_ROUTE = "/api/sync/v1/bootstrap/";
const PULL = "/api/sync/v1/pull/";

const emptyPage = (cursor: number) => ({
  status: 200,
  body: {
    changes: [],
    cursor,
    has_more: false,
    server_time: "2026-11-11T09:00:00Z",
    min_app_version: null,
  },
});

const paths = () => sent.map((request) => new URL(request.url).pathname);

describe("a sync", () => {
  it("bootstraps a fresh laptop, then pulls from its cursor", async () => {
    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });
    answer("GET", PULL, emptyPage(120));

    await syncShop(SHOP);

    expect(paths()).toEqual([BOOTSTRAP_ROUTE, PULL]);
    expect(new URL(sent[1]!.url).searchParams.get("cursor")).toBe("120");
    expect(await readCursor(shopDatabase(SHOP))).toBe(120);
  });

  it("only pulls on a laptop already filled", async () => {
    await shopDatabase(SHOP).meta.put({ key: "pull_cursor", value: 130 });
    answer("GET", PULL, emptyPage(130));

    await syncShop(SHOP);

    expect(paths()).toEqual([PULL]);
  });

  it("joins the sync already running instead of starting a second", async () => {
    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });
    answer("GET", PULL, emptyPage(120));

    const first = syncShop(SHOP);
    const second = syncShop(SHOP);
    await Promise.all([first, second]);

    expect(second).toBe(first);
    expect(paths()).toEqual([BOOTSTRAP_ROUTE, PULL]);
  });

  it("never joins another shop's sync", async () => {
    // The laptop was moved to another shop while its old shop's sync still ran.
    const other = "019a5e00-0000-7000-8000-0000000000a2";
    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });
    answer("GET", PULL, emptyPage(120));

    const first = syncShop(SHOP);
    const second = syncShop(other);
    await Promise.all([first, second]);

    expect(second).not.toBe(first);
    expect(await readCursor(shopDatabase(other))).toBe(120);
  });

  it("leaves the next sync free to run after one fails", async () => {
    answer("GET", BOOTSTRAP_ROUTE, refusal(500, "server_error"));
    await expect(syncShop(SHOP)).rejects.toThrow();

    answer("GET", BOOTSTRAP_ROUTE, { status: 200, body: BOOTSTRAP });
    answer("GET", PULL, emptyPage(120));
    await syncShop(SHOP);

    expect(await readCursor(shopDatabase(SHOP))).toBe(120);
  });
});
