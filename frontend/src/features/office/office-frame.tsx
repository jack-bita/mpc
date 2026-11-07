// office-frame.tsx — the office area's frame: the top bar names who is logged in and their shop, and
// someone who isn't is sent to the way in (UI-5, 03 §7.1).
//
// Every office screen asks the server for everything, and needs a login. So the frame asks `me`
// (useWhoIsHere, one answer shared with the screens), and:
//   someone logged in         their name, and their shop, in the bar: a manager's own phone knows no
//                             device, so only the login says which shop it is at
//   nobody (not_authenticated) away to the way in: the password login on a phone, and the PIN login at
//                             a registered laptop, whose home page it is (UI-4)
//   refused for a reason       stays: each screen shows why (a suspension, a shop switched off)
//   no answer                  stays: the offline banner says Inahitaji mtandao
//
// "use client": it asks the server, and reads the device's saved copy, both in the browser only.
"use client";

import { useRouter } from "next/navigation";
import { type ReactNode, useEffect } from "react";

import { ApiRefusal } from "@/api/refusal";
import { AppFrame } from "@/components/app-frame";
import { OfflineBanner } from "@/components/offline-banner";
import { useThisDevice } from "@/features/devices/this-device";
import { sideAt, useWhoIsHere } from "@/features/people/who-is-here";

export function OfficeFrame({ children }: { children: ReactNode }) {
  const me = useWhoIsHere();
  const device = useThisDevice();
  const router = useRouter();

  // Nobody logged in, and the server says only that: no reason to read. Any other refusal is a reason,
  // which the screen shows, and the person stays to read it.
  const nobody =
    me.error instanceof ApiRefusal &&
    me.error.body.code === "not_authenticated";
  const wayIn = device ? "/" : "/login/";
  useEffect(() => {
    // replace, not push: Back from the login shouldn't open a screen that sends them to it again.
    if (nobody) router.replace(wayIn);
  }, [nobody, wayIn, router]);

  const here = me.data;
  // At a registered laptop, the side the person works on, as the PIN login names it (UI-4); a phone knows
  // no side, and the bar names only the shop.
  const side = here && device ? sideAt(here, device.homeSide.id) : undefined;

  return (
    <AppFrame
      area="office"
      notice={<OfflineBanner />}
      shop={here?.shop.name}
      person={here?.staff.display_name}
      side={side ? { name: side.name } : undefined}
    >
      {children}
    </AppFrame>
  );
}
