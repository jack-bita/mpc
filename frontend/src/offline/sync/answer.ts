// answer.ts — the answer of a sync call, with the device's standing kept on the way (SYNC-7, 03 §5.9).
//
// The bootstrap, the pull and later the push call the server outside TanStack Query, so the store's
// watcher (noticeBlock, device-check.tsx) never sees their refusals. Each passes its call through here
// instead, and the two answers about the device itself are kept as the device check keeps them:
// - 401 device.blocked: the manager blocked this laptop. The lock goes on at once (03 §5.9, step 4); the
//   database stays as it is, so an unblock finds its records still there.
// - 401 not_authenticated: the key opens no device. The saved copy is forgotten, and the top bar stops
//   naming a shop this browser can't act for.
// Either way the refusal is thrown on, so the sync stops there and changes nothing.
import { ApiRefusal, answerOf } from "@/api/refusal";
import { saveBlocked, saveDevice } from "@/features/devices/this-device";

type Answer<D> = { data?: D; error?: unknown; response: Response };

/** The call's answer, or its refusal thrown, after keeping a block or a "not registered". */
export async function syncAnswer<D>(call: Promise<Answer<D>>): Promise<D> {
  try {
    return await answerOf(call);
  } catch (error) {
    if (error instanceof ApiRefusal) {
      if (error.body.code === "device.blocked") saveBlocked();
      else if (error.body.code === "not_authenticated") saveDevice(null);
    }
    throw error;
  }
}

/** Whether a sync's failure is about the device itself, a block or a "not registered": the sync must
 * then ask nothing more, as the device check would. Any other failure of the push still lets the pull
 * run (sync.ts). */
export function isAboutTheDevice(error: unknown): boolean {
  return (
    error instanceof ApiRefusal &&
    (error.body.code === "device.blocked" ||
      error.body.code === "not_authenticated")
  );
}
