// attendance-on.ts — whether attendance is switched on today, as this laptop knows it (ATT-2, ADR-0033). It
// owns the switch's reading: the welcome shows Mahudhurio only while it is on, and the screen itself takes no
// tap while it is off.
//
// The shop starts attendance on the day the owner chooses: `attendance.enabled`, a dated yes-or-no rule, off
// until he switches it on (apps/core/settings_registry.py). Read like every rule on the laptop (useRule,
// reference.ts): from the rows its pulls brought, on the shop's day by the server's clock as far as the
// laptop knows it, so "on from 1 December" comes on that day by itself, offline too.
//
// It hides the way in, nothing more: the server still takes a clock-in that comes (ATT-2), as a laptop that
// hadn't pulled the switch yet must not see its taps refused, and the day calculation counts days only from
// the day it is on (ATT-4).
import type { components } from "@/api/schema";

import { useRule } from "./reference";

/** The switch as this app carries it, for a laptop filled before the release that added it: such a laptop
 * never got the rule's kind and default, only its rows (SYNC-13's note). The server's own copy, from the
 * bootstrap, wins wherever the laptop has one. */
export const ATTENDANCE_SWITCH: components["schemas"]["SettingKeyRecord"] = {
  key: "attendance.enabled",
  kind: "yes_no",
  scope: "shop",
  default: "false",
};

/** True while attendance is on today, false while it is off, undefined while the laptop is still reading.
 * Only "true" is on: a damaged row reads as off, as the default does, never as a way in left open. */
export function useAttendanceOn(): boolean | undefined {
  const stored = useRule(ATTENDANCE_SWITCH.key, null, ATTENDANCE_SWITCH);
  return stored === undefined ? undefined : stored === "true";
}
