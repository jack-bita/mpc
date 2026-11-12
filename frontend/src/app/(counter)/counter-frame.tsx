// counter-frame.tsx — the frame around every counter screen (SYNC-11, 03 §7.1): who is at the counter in the
// top bar, with the side they work on, in their own language and font (UI-9); Badilisha mtu and Toka; and
// the idle lock. It owns who may see a counter screen: only someone logged in at the home page.
//
// It reads only the laptop, never the server (rule 5, ADR-0019), so it works the same offline: the
// counter's note of who is here, written by the home page, and their row on the laptop's copy
// (usePersonAtCounter, at-the-counter.ts). So a sync that brings a suspension or a new PIN sends the person
// back at once, with no server asked.
//
//   someone here       the screen, under a bar that names them and their side
//   still reading      nothing yet: their row is on its way, a moment, and they are not sent away for it
//   nobody             back to the home page, the name tiles, as after a reload, which ends the note as it
//                      ends a local session (Jack, SYNC-10)
//
// Toka and Badilisha mtu end the session the same way, as on the home page: a counter screen can't log
// anyone out on the server, so it hides them here at once and asks the home page, opened next, to do it
// (askToLeave). The idle lock does the same after the shop's minutes untouched: a seller who clocks in and
// walks away must not leave the counter open in her name.
//
// Here, inside (counter)/, so the lint rule that keeps counter screens off the server reads it too.
//
// "use client": it asks use-intl for words, and reads the laptop's database, in the browser only.
"use client";

import { useRouter } from "next/navigation";
import { type ReactNode, useEffect } from "react";
import { useTranslations } from "use-intl";

import { AppFrame } from "@/components/app-frame";
import { Button } from "@/components/design/button";
import { useThisDevice } from "@/features/devices/this-device";
import {
  askToLeave,
  usePersonAtCounter,
} from "@/features/login/at-the-counter";
import { useIdleLock } from "@/features/login/idle-lock";
import { useFollowThePerson } from "@/features/people/follow-the-person";
import { sideOfStaffRow } from "@/features/people/who-is-here";
import { useSides } from "@/offline/reference";

export function CounterFrame({ children }: { children: ReactNode }) {
  const t = useTranslations("login");
  const router = useRouter();
  const device = useThisDevice();
  const sides = useSides();
  const person = usePersonAtCounter();
  const row = person?.row;

  // Nobody here: to the name tiles. replace, not push: Back from the tiles shouldn't open a screen that
  // sends them straight back. Not while still reading (undefined): Asha's row is on its way.
  const nobody = person === null;
  useEffect(() => {
    if (nobody) router.replace("/");
  }, [nobody, router]);

  // Her own language and font, from her row on the laptop, as for a local session (UI-9, SYNC-10). Nobody's
  // from the press of Toka, so the tiles come back in the laptop's own.
  useFollowThePerson(row);
  // The side she works on, from her row's keys and the laptop's sides, as for a local session: the bar
  // says where her records go (UI-4).
  const side =
    row && device
      ? sideOfStaffRow(row, device.homeSide.id, sides ?? [])
      : undefined;

  // The idle lock: the home page's minutes, handed over with her (`me`'s, or offline the shop's rule).
  useIdleLock(person?.idleMinutes, askToLeave);

  // The bar kind: the only kind that can sit on the green; normal height, as the language button's. Both
  // end her session the same way: Toka for someone leaving, Badilisha mtu for the next person stepping up.
  const buttons = row ? (
    <>
      <Button kind="bar" size="normal" onClick={askToLeave}>
        {t("switch")}
      </Button>
      <Button kind="bar" size="normal" onClick={askToLeave}>
        {t("logout")}
      </Button>
    </>
  ) : undefined;

  return (
    <AppFrame
      area="counter"
      person={row?.display_name}
      side={side ? { name: side.name } : undefined}
      actions={buttons}
    >
      {/* The screen only to someone here: nobody, or a row still on its way, sees the bar alone. */}
      {row ? children : null}
    </AppFrame>
  );
}
