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
// count for the button, so she may clock in again. Under the button, who clocked in today on this laptop
// (todays-list.tsx), read from the same taps; then how many records wait to be sent, with Tuma sasa
// (send-now.tsx).
//
// A photo at each tap (ATT-3, 03 §5.13), so a PIN alone can't clock someone in: the camera is on while the
// button is there, her face live above it (use-camera.ts); the tap takes the photo, shrunk to about 150 KB
// (shrink-photo.ts), labels it (labelPhoto) and saves it with the tap in the same transaction, the payload
// naming it; the photo goes up by itself after the tap is in (sync/attachments.ts). After the tap she sees
// the photo kept. A camera missing, blocked or broken never stops a tap (Jack: A): the screen says so before
// the tap, and the tap goes without a photo, its payload saying why (`no_photo`). On the demo the photo is
// taken and shown, but never kept: every visitor shares Meneja's login, which opens clock-in photos, so a
// visitor's face never leaves their laptop (Jack: A); the tap says `demo`.
//
// Times as "07:55", 24 hours, in the shop's zone, and in Swahili with the part of the day, "saa 07:55
// asubuhi", so nobody reads them as Swahili time (formatTime, dayPart; Jack, SYNC-11).
//
// Only while the shop has attendance switched on (ATT-2, ADR-0033): the welcome shows no way here while it
// is off, and the screen, opened by its address, says it isn't switched on and offers no button. Nor while
// the laptop is still reading the switch: a button shown, then taken away, could take a tap. Off, it still
// shows the records the server refused and what waits to be sent: a shop that switches attendance off
// again still has taps on the laptop, and a manager to tell.
//
// "use client": it asks use-intl for words, and reads and writes the laptop's database, in the browser only.
"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { Alert, AlertDescription } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { PageHeader } from "@/components/design/page-header";
import { type CameraProblem, useCamera } from "@/features/camera/use-camera";
import { isTheDemo, useThisDevice } from "@/features/devices/this-device";
import {
  askToLeave,
  usePersonAtCounter,
} from "@/features/login/at-the-counter";
import { dayPart, formatTime } from "@/lib/format";
import { BrokenPhoto, labelPhoto } from "@/offline/attachments";
import { useAttendanceOn } from "@/offline/attendance-on";
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

/** The camera's problems, each with its line before the tap: the tap still goes, with no photo. */
const CAMERA_PROBLEMS: readonly string[] = [
  "no_camera",
  "blocked",
  "failed",
] satisfies CameraProblem[];

function isCameraProblem(state: string): state is CameraProblem {
  return CAMERA_PROBLEMS.includes(state);
}

export function AttendanceScreen() {
  const t = useTranslations("attendance");
  const person = usePersonAtCounter();
  const db = useShopDatabase();
  const device = useThisDevice();
  const timezone = device?.shop.timezone;
  const demo = isTheDemo(device);
  const today = useTodaysTaps();
  const attendanceOn = useAttendanceOn();
  const [saved, setSaved] = useState<Saved | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  // A tap on its way. A ref, not state: two taps in one moment both run before the screen draws again, and
  // the second must see the first.
  const busy = useRef(false);
  const [saving, setSaving] = useState(false);
  // The photo this visit's tap took, as an address the <img> can show, freed when it changes or the
  // screen closes: its bytes live in the browser's memory until then.
  const [kept, setKept] = useState<string | null>(null);
  useEffect(() => {
    if (kept === null) return;
    return () => URL.revokeObjectURL(kept);
  }, [kept]);
  // What the camera gave a tap that couldn't be saved (a full disk, say): her photo of a moment ago, or why
  // there was none. Her next try uses it: the camera went off with the first photo (use-camera.ts), and a
  // retry taken as "no photo, camera failed" would tell the manager a working camera broke (ATT-3's review).
  const [shotBefore, setShotBefore] = useState<Blob | CameraProblem | null>(
    null,
  );

  const row = person?.row;
  // Her last tap today on this laptop. Others' taps say nothing about her.
  const last = today?.taps.filter((tap) => tap.staffId === row?.id).at(-1);
  // "07:55 asubuhi" in Swahili, "07:55" in English (attendance.timeOfDay).
  const time = (at: string) =>
    timezone
      ? t("timeOfDay", {
          time: formatTime(at, timezone),
          part: dayPart(at, timezone),
        })
      : "";

  // The one button that fits: none before her taps and the switch are read, and none once this visit saved one.
  const next: ClockKind | null =
    row === undefined || today === undefined || attendanceOn !== true || saved
      ? null
      : last?.kind === "in"
        ? "out"
        : "in";
  // The camera, on while there is a button to tap: off before the screen knows which, off once the tap is
  // saved, and off when she leaves the screen (use-camera.ts).
  // Its three parts by name: React's lint reads an object that carries a ref as a ref, all of it.
  const { state: cameraState, videoRef, take } = useCamera(next !== null);

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
    let shot: Blob | CameraProblem | null = null;
    try {
      // Read as the tap is saved, so it is the last one the laptop knew at the tap, not at the push. Before
      // the photo: a laptop not ready to save takes none.
      const lastServerTime = await readLastServerTime(db);
      if (lastServerTime === null) throw new NeverFilled();
      // The photo, or why there is none; the camera goes off either way. A try after a save that failed uses
      // the first try's.
      shot = shotBefore ?? (await take());
      const photo =
        demo || typeof shot === "string" ? null : await labelled(shot);
      const payload: ClockPayload = {
        kind,
        last_server_time: lastServerTime,
        ...(photo !== null
          ? { photo: photo.label }
          : {
              no_photo:
                typeof shot === "string" ? shot : demo ? "demo" : "failed",
            }),
      };
      // The tap and its photo in one transaction: never a tap naming a photo the laptop lost (CTRL-6).
      const document = await saveDocument(
        db,
        {
          type: CLOCK,
          schema_version: CLOCK_VERSION,
          created_by: row.id,
          payload,
        },
        [],
        photo === null ? [] : [photo],
      );
      setSaved({ kind, at: document.client_time });
      // She sees the photo kept with her tap; on the demo, the one taken, kept nowhere.
      if (typeof shot !== "string" && (photo !== null || demo))
        setKept(URL.createObjectURL(shot));
    } catch (error) {
      if (error instanceof NeverFilled) setProblem("firstSync");
      else {
        // A broken draft is a bug in this screen; a database that refused, a full disk or a browser that
        // blocks storage. Either way the tap is not kept, and she must know it.
        console.error("a clock tap was not saved", error);
        setProblem("failed");
      }
      // The photo taken, or the camera's answer, kept for her next try.
      if (shot !== null) setShotBefore(shot);
      // Ready for the next try. Not after a save: the button is gone for this visit.
      busy.current = false;
    } finally {
      setSaving(false);
    }
  }

  // The label of the photo just taken (attachments.ts), or none when it can't be made: a photo labelPhoto
  // refuses (BrokenPhoto: over 1 MB, or no JPEG by its bytes) is a bug in the camera's code, and a browser
  // that can't read the photo or work out its SHA-256 is the laptop's trouble; never her fault either way.
  // So the tap goes on without the photo, as failed, and the console says why: a photo's problem never
  // stops a tap (Jack: A; ATT-3's review).
  async function labelled(shot: Blob) {
    try {
      return await labelPhoto(shot, "clock_photo");
    } catch (error) {
      const why = error instanceof BrokenPhoto ? error.problem : "unreadable";
      console.error(`a clock-in photo was not kept (${why})`, error);
      return null;
    }
  }

  // Why a tap will go without a photo, said before it: the camera's own answer, or, on a try after a save
  // that failed, the first try's, as the camera is off by then.
  const cameraProblem: CameraProblem | null = isCameraProblem(cameraState)
    ? cameraState
    : typeof shotBefore === "string"
      ? shotBefore
      : null;

  // What the screen says: what this visit saved, else where she stands today. Nothing before the switch is
  // read, with the button: a line that came first could turn into "not started" a moment later.
  const status = saved
    ? t(saved.kind === "in" ? "savedIn" : "savedOut", { time: time(saved.at) })
    : attendanceOn === undefined
      ? null
      : last
        ? t(last.kind === "in" ? "inSince" : "outSince", {
            time: time(last.at),
          })
        : today
          ? t("notInYet")
          : null;
  // Attendance switched off at this shop: the way back, why there is nothing to tap, and the taps already on
  // the laptop. Not once this visit saved one: the switch turned off by a pull a moment after her tap, she
  // still reads that her time was kept.
  if (attendanceOn === false && !saved)
    return (
      <div className="grid max-w-md gap-6">
        <PageHeader title={t("title")} fallback="/" />
        <p className="text-lg">{t("switchedOff")}</p>
        <NeedsAttention />
        <SendNow />
      </div>
    );

  return (
    <div className="grid max-w-md gap-6">
      {/* The back arrow to her welcome, as on every page reached from another (Jack, OPS-13), but not
          during the goodbye: she has clocked out, and is on her way out. */}
      <PageHeader title={t("title")} fallback="/" arrow={!leaving} />
      {/* role="status": a screen reader says what was saved as it changes. Always on the page, as a status
          line that comes with its words in it often goes unsaid (offline-banner.tsx). */}
      <p role="status" className={status ? "text-lg" : "sr-only"}>
        {status}
      </p>
      {/* The photo kept with her tap, small, under the line that says it was saved (Jack, ATT-3). Through
          Next's Image, as every picture of the app is; never resized by a server, as the app has none
          (images.unoptimized). */}
      {kept && (
        <div className="grid gap-2">
          <Image
            src={kept}
            // On the demo the photo is kept nowhere, so it is the one just taken, not one kept: a screen reader
            // never says "kept" above a line that says it is never sent (ATT-3's review).
            alt={t(demo ? "photo.taken" : "photo.kept")}
            width={1600}
            height={900}
            className="h-auto w-40 rounded-lg"
          />
          {demo && <p className="text-muted-foreground">{t("photo.demo")}</p>}
        </div>
      )}
      {problem && (
        <Alert kind="danger">
          <AlertDescription>{t(problem)}</AlertDescription>
        </Alert>
      )}
      {/* A tap the server refused, above the button: she sees why before she taps again (SYNC-11). */}
      <NeedsAttention />
      {/* Her face, live, above the button: she sees the camera sees her before she taps. Played by the
          browser by itself (autoPlay, muted), and inline on a phone, never full screen. A camera that
          can't says so in its place, and the tap still goes. */}
      {next &&
        (cameraProblem !== null ? (
          <p>{t(`camera.${cameraProblem}`, { kind: next })}</p>
        ) : (
          cameraState !== "off" && (
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              aria-label={t("camera.live")}
              className="aspect-video w-full rounded-lg bg-muted object-cover"
            />
          )
        ))}
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
