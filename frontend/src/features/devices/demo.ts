// demo.ts — the one-tap demo (OPS-3, BP15): whether Jaribu demo may show on this server, the tap that
// makes this browser a device of the demo shop, and the sellers' PINs the tap hands over, kept on the
// laptop for the PIN screen to show under their tiles.
//
// GET /api/devices/v1/demo/open/ answers true only where the demo shop is the only shop: never on the
// real server, which never has the demo's sign, nor beside a live shop. POST /api/devices/v1/demo/ makes
// the device, puts its key in a cookie page scripts can never read (AUTH-2), and answers with the PINs.
// The device itself the app learns as every device does, from its own check (device-check.tsx).
//
// The PINs are kept on the laptop by demo-pins.ts, which never calls the server, for the PIN screen.
import Dexie from "dexie";

import { api, csrfHeader } from "@/api/client";
import { answerOf, ApiRefusal } from "@/api/refusal";
import { databaseName } from "@/offline/db";

import { savePins } from "./demo-pins";
import { checkThisDevice } from "./device-check";
import type { ThisDevice } from "./this-device";

/** The open check's place in the store of server answers. */
export const DEMO_OPEN = ["devices", "demo", "open"] as const;

/** Whether Jaribu demo may show here. No answer (offline, a server down) is thrown: the button then
 * stays hidden, as the tap couldn't work anyway. */
export async function askDemoOpen(): Promise<boolean> {
  return (await answerOf(api.GET("/api/devices/v1/demo/open/"))).open;
}

/**
 * The tap: this browser becomes a device of the demo shop, and keeps the PINs. Gives back the device, as
 * its own check saved it. A refusal (demo.closed, too many tries) or no answer is thrown, for the screen
 * to show.
 */
export async function tryTheDemo(): Promise<ThisDevice> {
  // The tap is a change, so it needs the CSRF token, as a pairing's start does (pairing.ts): the device's
  // check hands the browser its cookie, and a tap faster than that answer asks for it first.
  if (Object.keys(csrfHeader()).length === 0)
    await checkThisDevice().catch(() => null);

  try {
    const made = await answerOf(api.POST("/api/devices/v1/demo/"));
    // Kept before the device is saved: the moment it is, the home page swaps to the PIN screen, whose
    // tiles must already find their PINs.
    savePins(made.pins);
  } catch (error) {
    // pairing.already_paired: this browser's key already opens a device. A tap before this one made it,
    // and the check after that tap got no answer (the network dropped for a second), so the visitor saw
    // an error and tapped again. Not a dead end: the device is there, so this tap goes on to the check, as
    // Sajili kifaa hiki does after a yes in the code's last second (register-this-device.tsx). The PINs
    // came with the first tap's answer, kept above; only an answer lost on its way leaves none, and the
    // tiles then show no PIN.
    if (!(
      error instanceof ApiRefusal &&
      error.body.code === "pairing.already_paired"
    ))
      throw error;
  }
  const device = await checkThisDevice();
  if (device === null)
    // The server made the device a moment ago, yet the key opens nothing: the browser didn't keep its
    // cookie (a browser set to block every site's cookies). Said, never a welcome screen that does nothing.
    throw new Error("The demo device's key didn't stay in this browser.");
  await forgetOtherShops(device.shop.id);
  return device;
}

/**
 * Deletes every shop's copy on this laptop but `keep`'s: on the demo, yesterday's demo shops (04 OPS-3).
 * Tidying only: each shop's copy is a database of its own, named by the shop's id (db.ts), and the reset
 * makes the shop with a new id, so yesterday's copy is never opened again, nor its outbox sent (the
 * background push checks its shop first, SYNC-16). Without this, each day's visit would leave one more.
 * Called only once the demo is open here, which the server says only where the demo shop is the only shop,
 * so no other copy on this address can be a real shop's. A copy that can't be deleted stays: nothing reads
 * it.
 */
export async function forgetOtherShops(keep: string): Promise<void> {
  try {
    const names = await Dexie.getDatabaseNames();
    // Every shop's name starts the same way, "mpc-shop-", then the shop's id.
    const others = names.filter(
      (name) =>
        name.startsWith(databaseName("")) && name !== databaseName(keep),
    );
    // A tab still holding one open closes it by itself: Dexie closes a database another tab deletes.
    await Promise.all(others.map((name) => Dexie.delete(name)));
  } catch {
    // A browser that can't list its databases: the copies stay, as before this card.
  }
}
