// device-check.tsx — the device asks the server who it is, and keeps the answer, a block included
// (UI-3, 03 §5.9, steps 3 and 4).
//
// GET /api/devices/v1/me/ sends the device's key, in its cookie, and answers with the device, its shop
// and its home side, once a manager has said yes to it; a blocked device gets 401 device.blocked. Asked
// when the app opens, when its window comes back to the front, when the network comes back, and every 5
// minutes while the app is open, so a rename, a block or an unblock shows soon. The answer is saved in
// this-device.ts, which the top bar and the lock read.
//
// Each answer that names a working device also starts a sync of its shop's database (SYNC-7, sync.ts),
// so an office change reaches the counter at the next check. The check and its moments are the trigger
// until SYNC-9 brings sync's own (03 §6.5).
//
// A block also shows at the device's next request of any kind: every answer in the store of server
// answers is watched for device.blocked. A PIN session's office routes send it as a 403 (AUTH-4). Sync's
// pull and push (SYNC-7, SYNC-8) won't go through the store, so nothing here sees their answers: each
// calls saveBlocked() itself, and Background Sync, in the service worker, which has no localStorage,
// finds its own way to tell the page (SYNC-9).
//
// The root layout puts it on every page, the counter's included. That is not a counter screen asking the
// server for the shop's data (rule 5): it is the device asking about itself, and offline it simply fails
// and keeps the last answer, so a counter screen works the same either way. It shows nothing.
//
// It also gives the browser its CSRF token: the server sends the cookie with every answer of this route
// (DeviceMeView), so the first change the app sends, a pairing's start or a manager's confirm, has it.
//
// "use client": it runs in the browser, and the build has none.
"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { api } from "@/api/client";
import { syncShop } from "@/offline/sync/sync";
import { answerOf, ApiRefusal, NoConnection } from "@/api/refusal";
import type { components } from "@/api/schema";

import { saveBlocked, saveDevice, type ThisDevice } from "./this-device";

type DeviceMe = components["schemas"]["DeviceMe"];

/** How often the app asks, while it is open: every 5 minutes. The server notes the device seen at most
 * every 5 minutes too (last_seen_at, LAST_SEEN_EVERY, AUTH-2), and a check that lands just short of that
 * notes nothing, so on the manager's list an open laptop reads as seen up to about 10 minutes ago. */
export const DEVICE_CHECK_EVERY = 5 * 60 * 1000;

/** The check's place in the store of server answers. The registration screen asks the same, faster,
 * while it waits for the manager (UI-3), and the lock asks it again on a tap; all share one answer. */
export const DEVICE_CHECK = ["devices", "me"] as const;

// The API's answer, in our own shape (this-device.ts says why).
function fromAnswer(me: DeviceMe): ThisDevice {
  return {
    id: me.device.id,
    name: me.device.name,
    code: me.device.code,
    shop: {
      id: me.shop.id,
      name: me.shop.name,
      code: me.shop.code,
      timezone: me.shop.timezone,
      currency: me.shop.currency,
      language: me.shop.default_language,
    },
    homeSide: {
      id: me.home_side.id,
      code: me.home_side.code,
      name: me.home_side.name,
    },
  };
}

/** Keeps a block, from whichever request the server refused with it: 401 on the device's own routes,
 * 403 on a PIN session's (AUTH-4). Anything else changes nothing. */
export function noticeBlock(error: unknown): void {
  if (error instanceof ApiRefusal && error.body.code === "device.blocked")
    saveBlocked();
}

/**
 * Asks the server who this device is, saves the answer, and gives it back: the device, or null when the
 * server knows no working device by this browser's key. Anything else (a block, no network, a server
 * down) is thrown. A block is kept first; otherwise the saved copy stays as it was: the device was
 * registered a moment ago, and a dropped network doesn't change that.
 *
 * Honest limits: a slow answer from before a block, landing after another request's device.blocked,
 * clears the block until the next request, a moment later. And a suspended shop's device gets 401
 * shop.suspended, which is none of the answers above: the app keeps its copy and is neither locked nor
 * told, until the card that checks a shop's status for devices decides what it shows.
 */
export async function checkThisDevice(): Promise<ThisDevice | null> {
  try {
    const device = fromAnswer(await answerOf(api.GET("/api/devices/v1/me/")));
    // A working device, so no longer blocked, if it was: an unblock opens the lock here.
    saveDevice(device);
    return device;
  } catch (error) {
    // 401 not_authenticated: no key, a key still waiting for the manager's yes, or a key that opens no
    // device. Not a failure: the honest answer "not registered", so the saved copy is forgotten, and the
    // top bar stops naming a shop this browser can't act for.
    if (
      error instanceof ApiRefusal &&
      error.body.code === "not_authenticated"
    ) {
      saveDevice(null);
      return null;
    }
    noticeBlock(error);
    throw error;
  }
}

/**
 * What a failed sync leaves. Every failure waits for the next check, which tries again from where the
 * last one stopped. The server's answers and a dropped network are part of a shop's day: a block or a
 * "not registered" is kept already (answer.ts), and the rest pass. Anything else is no answer of the
 * server's: an app older than the server (AppTooOld, which SYNC-13 turns into an update), or a bug. It
 * would fail again at every check with no one the wiser, so it goes to the console, where a developer
 * looking at a laptop that stopped syncing finds it.
 */
export function reportSyncFailure(error: unknown): void {
  if (error instanceof ApiRefusal || error instanceof NoConnection) return;
  console.error("sync failed", error);
}

/** Keeps the device's saved copy up to date. Shows nothing; the root layout puts it on every page. */
export function DeviceCheck() {
  const client = useQueryClient();

  const { data: device, dataUpdatedAt } = useQuery({
    queryKey: DEVICE_CHECK,
    queryFn: checkThisDevice,
    refetchInterval: DEVICE_CHECK_EVERY,
    // TanStack's defaults, written out because they are the point: the window back in front, or the
    // network back, may mean hours have passed since the last answer.
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  });

  // After every answer naming a working device, a sync. dataUpdatedAt moves at each answer, even one the
  // same as the last, so a laptop that shows no change in itself still pulls the shop's.
  const shopId = device?.shop.id;
  useEffect(() => {
    if (shopId === undefined) return;
    syncShop(shopId).catch(reportSyncFailure);
  }, [shopId, dataUpdatedAt]);

  // Every read and every change through the store, any screen's, is watched for a block, so the lock
  // comes at the device's very next request, not at the next check. Each store tells its watchers of
  // every change to an answer; only a failure is looked at. The store is made once per page (provider.tsx),
  // so this runs once; the returned functions stop the watching if the page ever drops it.
  useEffect(() => {
    const stopReads = client.getQueryCache().subscribe((event) => {
      if (event.type === "updated" && event.action.type === "error")
        noticeBlock(event.action.error);
    });
    const stopChanges = client.getMutationCache().subscribe((event) => {
      if (event.type === "updated" && event.action.type === "error")
        noticeBlock(event.action.error);
    });
    return () => {
      stopReads();
      stopChanges();
    };
  }, [client]);

  return null;
}
