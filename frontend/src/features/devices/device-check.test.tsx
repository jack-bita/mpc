// device-check.test.tsx — the device asks the server who it is, keeps a yes, forgets a "not registered",
// and keeps its last answer when the server can't be reached; the top bar then names its shop (UI-3).
import { act, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QueryProvider } from "@/api/provider";
import { ApiRefusal, NoConnection } from "@/api/refusal";
import OfficeLayout from "@/app/(office)/layout";
import { DAWA_LAPTOP, DAWA_LAPTOP_ANSWER } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { databaseName } from "@/offline/db";
import { readCursor } from "@/offline/sync/meta";
import { AppTooOld } from "@/offline/sync/pull";
import { BrokenPush } from "@/offline/sync/push";
import { shopDatabase } from "@/offline/this-shop";
import { BOOTSTRAP, DAWA_SIDE } from "@/test/shop-lists";

import {
  checkThisDevice,
  DEVICE_CHECK_EVERY,
  DeviceCheck,
  reportSyncFailure,
} from "./device-check";
import {
  saveBlocked,
  savedBlocked,
  saveDevice,
  savedDevice,
} from "./this-device";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/devices/v1/me/";

afterEach(() => {
  vi.useRealTimers();
  // The console the failure tests silenced, back as it was.
  vi.restoreAllMocks();
});

describe("checkThisDevice", () => {
  it("keeps a registered device's answer", async () => {
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });

    expect(await checkThisDevice()).toEqual(DAWA_LAPTOP);
    expect(savedDevice()).toEqual(DAWA_LAPTOP);
  });

  it("forgets the saved copy when the server knows no device by this key", async () => {
    // A key still waiting for the manager, or a browser whose key is gone: 401 not_authenticated.
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, refusal(401, "not_authenticated"));

    expect(await checkThisDevice()).toBeNull();
    expect(savedDevice()).toBeNull();
  });

  it("keeps a block, and the device it was known as", async () => {
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, refusal(401, "device.blocked"));

    await expect(checkThisDevice()).rejects.toBeInstanceOf(ApiRefusal);
    expect(savedBlocked()).toBe(true);
    expect(savedDevice()).toEqual(DAWA_LAPTOP);
  });

  it("lifts a block when the server names the device again", async () => {
    // The manager unblocked it: the same key works again (AUTH-1).
    saveDevice(DAWA_LAPTOP);
    saveBlocked();
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });

    await checkThisDevice();

    expect(savedBlocked()).toBe(false);
  });

  it("keeps the saved copy when no answer comes", async () => {
    // Offline, the laptop is still the Dawa laptop.
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, () => {
      throw new TypeError("Failed to fetch");
    });

    await expect(checkThisDevice()).rejects.toBeInstanceOf(NoConnection);
    expect(savedDevice()).toEqual(DAWA_LAPTOP);
  });

  it("keeps the saved copy when the server has a problem", async () => {
    saveDevice(DAWA_LAPTOP);
    answer("GET", ME, refusal(500, "server_error"));

    await expect(checkThisDevice()).rejects.toBeInstanceOf(ApiRefusal);
    expect(savedDevice()).toEqual(DAWA_LAPTOP);
  });
});

describe("DeviceCheck", () => {
  it("asks when the app opens, and the top bar names the shop and the home side", async () => {
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });

    render(
      <QueryProvider>
        <OfficeLayout>
          <p>screen</p>
        </OfficeLayout>
        <DeviceCheck />
      </QueryProvider>,
    );

    expect(await screen.findByText("MPC · Dawa")).toBeDefined();
    // Words only: no side says which band it gets yet (04 §20, item 19).
    expect(document.querySelector("[data-look]")).toBeNull();
  });

  it("asks again every 5 minutes, so a rename on the manager's phone shows", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });
    render(
      <QueryProvider>
        <DeviceCheck />
      </QueryProvider>,
    );
    await vi.waitFor(() => expect(savedDevice()).toEqual(DAWA_LAPTOP));

    const renamed = {
      ...DAWA_LAPTOP_ANSWER,
      device: { ...DAWA_LAPTOP_ANSWER.device, name: "Laptop ya Dawa" },
    };
    answer("GET", ME, { status: 200, body: renamed });
    await act(() => vi.advanceTimersByTimeAsync(DEVICE_CHECK_EVERY));

    await vi.waitFor(() => expect(savedDevice()?.name).toBe("Laptop ya Dawa"));
    // Two checks; each also started a sync, whose requests are its own (sync.test.ts).
    expect(sent.filter((request) => request.url.endsWith(ME))).toHaveLength(2);
  });

  it("fills a fresh laptop's database once the check names it, then pulls", async () => {
    // A change made in the office after the copy: the first pull brings it.
    const renamed = { ...DAWA_SIDE, name: "Duka la Dawa" };
    answer("GET", ME, { status: 200, body: DAWA_LAPTOP_ANSWER });
    answer("GET", "/api/sync/v1/bootstrap/", { status: 200, body: BOOTSTRAP });
    // Nothing waits to go: the push before the pull is the laptop's report alone (SYNC-8).
    answer("POST", "/api/sync/v1/push/", {
      status: 200,
      body: { answers: [] },
    });
    answer("GET", "/api/sync/v1/pull/", {
      status: 200,
      body: {
        changes: [
          {
            seq: 121,
            entity: "side",
            id: DAWA_SIDE.id,
            op: "upsert",
            data: renamed,
          },
        ],
        cursor: 121,
        has_more: false,
        server_time: "2026-11-11T09:00:00Z",
        min_app_version: null,
      },
    });

    render(
      <QueryProvider>
        <DeviceCheck />
      </QueryProvider>,
    );

    const db = shopDatabase(DAWA_LAPTOP.shop.id);
    await vi.waitFor(async () => expect(await readCursor(db)).toBe(121));
    expect(db.name).toBe(databaseName(DAWA_LAPTOP.shop.id));
    expect(await db.side.get(DAWA_SIDE.id)).toEqual(renamed);
    expect(await db.staff.toArray()).toEqual(BOOTSTRAP.staff);
  });

  it("starts no sync while the device isn't registered", async () => {
    answer("GET", ME, refusal(401, "not_authenticated"));

    render(
      <QueryProvider>
        <DeviceCheck />
      </QueryProvider>,
    );

    await vi.waitFor(() => expect(sent).toHaveLength(1));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(sent.map((request) => new URL(request.url).pathname)).toEqual([ME]);
  });
});

describe("a failed sync", () => {
  it("says nothing for the server's answers and a dropped network", () => {
    // Part of a shop's day: the next check tries again.
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);

    reportSyncFailure(
      new ApiRefusal(500, {
        code: "server_error",
        message: "",
        fields: {},
        params: {},
      }),
    );
    reportSyncFailure(new NoConnection(new TypeError("Failed to fetch")));

    expect(log).not.toHaveBeenCalled();
  });

  it("goes to the console when it is no answer of the server's", () => {
    // An app older than the server, or a bug: it would fail at every check, unseen.
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const tooOld = new AppTooOld("product");

    reportSyncFailure(tooOld);

    expect(log).toHaveBeenCalledWith("sync failed", tooOld);
  });

  it("goes to the console when the server refuses a push as broken", () => {
    // A bug in the sync code (SYNC-8): every later push would be refused the same way.
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const broken = new BrokenPush(
      new ApiRefusal(400, {
        code: "invalid",
        message: "",
        fields: { "documents.0.device_seq": ["invalid"] },
        params: {},
      }),
    );

    reportSyncFailure(broken);

    expect(log).toHaveBeenCalledWith("sync failed", broken);
  });
});
