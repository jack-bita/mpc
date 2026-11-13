// attendance.tsx — the Mahudhurio screen (SYNC-11, 02 §12, 03 §6.2): the person at the counter clocks in as
// they arrive and out as they leave, with one big button, the one that fits. It owns the tap: one clock
// document saved on the laptop, in their name.
//
// The tap is saved on the laptop first (saveDocument, outbox.ts): the document, its number and its outbox
// row in one transaction, so it holds even if the laptop closes a moment later, with or without the
// internet. The sync takes it to the server later, by itself (SYNC-8, SYNC-9). The screen never calls the
// server (rule 5, ADR-0019): it reads the laptop's database and its note of who is here only.
//
// Which button: from the person's last tap today on this laptop (clock-today.ts). None, or "out" (back from
// lunch), Ingia kazini; "in", Toka kazini. Once tapped, the button goes for the rest of this visit and the
// screen says what it saved: a quick double tap would otherwise land on the button that comes next, and
// clock her out a moment after she came. Toka kazini says goodbye, then logs her out by itself: she is
// leaving the shop, and the laptop must not stay open in her name (Jack, SYNC-11).
//
// The tap carries the last time the server had told the laptop, at its last pull (meta.ts): the server's
// evidence that the laptop's clock didn't move back (ATT-1's time check). A laptop with none yet, filled by a
// bootstrap but never pulled, or never filled at all (NeverFilled), saves nothing and says to wait for the
// first sync: the server would refuse such a tap, and it would sit set aside.
//
// Above the button, any record the server refused, with why (needs-attention.tsx): a refused tap doesn't
// count for the button, so she may clock in again. Under the button, who clocked in today on this laptop (todays-list.tsx), read from the same taps; then how
// many records wait to be sent, with Tuma sasa (send-now.tsx).
//
// Times as "07:55", 24 hours, in the shop's zone (formatTime, Jack, SYNC-11).
//
// "use client": it asks use-intl for words, and reads and writes the laptop's database, in the browser only.
"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { Alert, AlertDescription } from "@/components/design/alert";
import { Button, ButtonLink } from "@/components/design/button";
import { useThisDevice } from "@/features/devices/this-device";
import {
  askToLeave,
  usePersonAtCounter,
} from "@/features/login/at-the-counter";
import { formatTime } from "@/lib/format";
import {
  CLOCK,
  CLOCK_VERSION,
  type ClockKind,
  type ClockPayload,
  useTodaysTaps,
} from "@/offline/clock-today";
import { NeverFilled, saveDocument } from "@/offline/outbox";
import { readLastServerTime } from "@/offline/sync/meta";
import { useShopDatabase } from "@/offline/this-shop";

import { NeedsAttention } from "../needs-attention";
import { SendNow } from "./send-now";
import { TodaysList } from "./todays-list";

/** How long the goodbye shows after Toka kazini, before the laptop logs her out: long enough to read it
 * and see her time was kept. */
export const GOODBYE_FOR = 3 * 1000;

/** What the last tap on this visit saved, to say so. */
interface Saved {
  kind: ClockKind;
  at: string;
}

/** Why a tap saved nothing: the laptop isn't ready yet, or something failed. */
type Problem = "firstSync" | "failed";

export function AttendanceScreen() {
  const t = useTranslations("attendance");
  const person = usePersonAtCounter();
  const db = useShopDatabase();
  const timezone = useThisDevice()?.shop.timezone;
  const today = useTodaysTaps();
  const [saved, setSaved] = useState<Saved | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  // A tap on its way. A ref, not state: two taps in one moment both run before the screen draws again, and
  // the second must see the first.
  const busy = useRef(false);
  const [saving, setSaving] = useState(false);

  const row = person?.row;
  // Her last tap today on this laptop. Others' taps say nothing about her.
  const last = today?.taps.filter((tap) => tap.staffId === row?.id).at(-1);
  const time = (at: string) => (timezone ? formatTime(at, timezone) : "");

  // After Toka kazini: the goodbye, then the logout, as her own Toka would. She is leaving the shop, so the
  // screen going during the goodbye logs her out at once: Back in the browser, or any other way off it,
  // must not cancel the logout and leave the laptop open in her name. Toka pressed meanwhile already did
  // it: askToLeave then finds nobody, and asks nothing.
  const leaving = saved?.kind === "out";
  useEffect(() => {
    if (!leaving) return;
    const timer = setTimeout(askToLeave, GOODBYE_FOR);
    return () => {
      clearTimeout(timer);
      askToLeave();
    };
  }, [leaving]);

  async function tap(kind: ClockKind) {
    if (busy.current || row === undefined || db === null) return;
    busy.current = true;
    setSaving(true);
    setProblem(null);
    try {
      // Read as the tap is saved, so it is the last one the laptop knew at the tap, not at the push.
      const lastServerTime = await readLastServerTime(db);
      if (lastServerTime === null) throw new NeverFilled();
      const payload: ClockPayload = { kind, last_server_time: lastServerTime };
      const document = await saveDocument(db, {
        type: CLOCK,
        schema_version: CLOCK_VERSION,
        created_by: row.id,
        payload,
      });
      setSaved({ kind, at: document.client_time });
    } catch (error) {
      if (error instanceof NeverFilled) setProblem("firstSync");
      else {
        // A broken draft is a bug in this screen; a database that refused, a full disk or a browser that
        // blocks storage. Either way the tap is not kept, and she must know it.
        console.error("a clock tap was not saved", error);
        setProblem("failed");
      }
      // Ready for the next try. Not after a save: the button is gone for this visit.
      busy.current = false;
    } finally {
      setSaving(false);
    }
  }

  // What the screen says: what this visit saved, else where she stands today.
  const status = saved
    ? t(saved.kind === "in" ? "savedIn" : "savedOut", { time: time(saved.at) })
    : last
      ? t(last.kind === "in" ? "inSince" : "outSince", { time: time(last.at) })
      : today
        ? t("notInYet")
        : null;
  // The one button that fits: none before her taps are read, and none once this visit saved one.
  const next: ClockKind | null =
    row === undefined || today === undefined || saved
      ? null
      : last?.kind === "in"
        ? "out"
        : "in";

  return (
    <div className="grid max-w-md gap-6">
      {/* Rudi to her welcome, but not during the goodbye: she has clocked out, and is on her way out. */}
      {!leaving && (
        <div>
          <ButtonLink href="/" kind="second" size="normal">
            {t("back")}
          </ButtonLink>
        </div>
      )}
      <h1 className="text-3xl font-semibold">{t("title")}</h1>
      {/* role="status": a screen reader says what was saved as it changes. Always on the page, as a status
          line that comes with its words in it often goes unsaid (offline-banner.tsx). */}
      <p role="status" className={status ? "text-lg" : "sr-only"}>
        {status}
      </p>
      {problem && (
        <Alert kind="danger">
          <AlertDescription>{t(problem)}</AlertDescription>
        </Alert>
      )}
      {/* A tap the server refused, above the button: she sees why before she taps again (SYNC-11). */}
      <NeedsAttention />
      {next && (
        // The main kind and the big size: the one thing this screen is for, easy to hit on a phone too.
        <Button size="big" disabled={saving} onClick={() => void tap(next)}>
          {t(next === "in" ? "clockIn" : "clockOut")}
        </Button>
      )}
      {/* Who else is in today, on this laptop: under the button, as the button is what she came for. */}
      <TodaysList />
      {/* What waits to leave this laptop, and Tuma sasa: the first counter screen carries the button (SYNC-9). */}
      <SendNow />
    </div>
  );
}
