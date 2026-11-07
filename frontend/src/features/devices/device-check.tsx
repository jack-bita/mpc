// device-check.tsx — the device asks the server who it is, and keeps the answer (UI-3, 03 §5.9, step 3).
//
// GET /api/devices/v1/me/ sends the device's key, in its cookie, and answers with the device, its shop
// and its home side, once a manager has said yes to it. Asked when the app opens, when its window comes
// back to the front, when the network comes back, and every 5 minutes while the app is open, so a rename
// or a new home side shows soon. The answer is saved in this-device.ts, which the top bar reads.
//
// The root layout puts it around every page, the counter's included. That is not a counter screen asking
// the server for the shop's data (rule 5): it is the device asking about itself, and offline it simply
// fails and keeps the last answer, so a counter screen works the same either way. It shows nothing.
//
// It also gives the browser its CSRF token: the server sends the cookie with every answer of this route
// (DeviceMeView), so the first change the app sends, a pairing's start or a manager's confirm, has it.
//
// "use client": it runs in the browser, and the build has none.
"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { answerOf, ApiRefusal } from "@/api/refusal";
import type { components } from "@/api/schema";

import { saveDevice, type ThisDevice } from "./this-device";

type DeviceMe = components["schemas"]["DeviceMe"];

/** How often the app asks, while it is open: 5 minutes, as often as the server notes the device was
 * seen (last_seen_at, AUTH-2), so each check keeps the manager's list up to date and costs no more. */
export const DEVICE_CHECK_EVERY = 5 * 60 * 1000;

/** The check's place in the store of server answers. The registration screen asks the same, faster,
 * while it waits for the manager (UI-3), so both share one answer. */
export const DEVICE_CHECK = ["devices", "me"] as const;

// The API's answer, in our own shape (this-device.ts says why).
function fromAnswer(me: DeviceMe): ThisDevice {
  return {
    id: me.device.id,
    name: me.device.name,
    code: me.device.code,
    shop: { id: me.shop.id, name: me.shop.name, code: me.shop.code },
    homeSide: {
      id: me.home_side.id,
      code: me.home_side.code,
      name: me.home_side.name,
    },
  };
}

/**
 * Asks the server who this device is, saves the answer, and gives it back: the device, or null when the
 * server knows no working device by this browser's key. Anything else (no network, a server down) is
 * thrown, and the saved copy stays as it was: the device was registered a moment ago, and a dropped
 * network doesn't change that.
 */
export async function checkThisDevice(): Promise<ThisDevice | null> {
  try {
    const device = fromAnswer(await answerOf(api.GET("/api/devices/v1/me/")));
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
    throw error;
  }
}

/** Keeps the device's saved copy up to date. Shows nothing; the root layout puts it on every page. */
export function DeviceCheck() {
  useQuery({
    queryKey: DEVICE_CHECK,
    queryFn: checkThisDevice,
    refetchInterval: DEVICE_CHECK_EVERY,
    // TanStack's defaults, written out because they are the point: the window back in front, or the
    // network back, may mean hours have passed since the last answer.
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  });
  return null;
}
