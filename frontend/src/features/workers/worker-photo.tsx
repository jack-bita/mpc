// worker-photo.tsx — Picha, a worker's photo on their own page (PPL-9): the face, or that there is none; and two ways to
// set it, as Jack pictured them (23 Nov 2026): Piga picha, the phone's own camera, for the worker standing there, and
// Chagua picha, the phone's gallery, so the owner may take the photo by day and set it at night. Either opens the photo
// in a sheet over the page (photo-sheet.tsx), and only its Hifadhi sends it. And, while there is a photo, Ondoa picha
// under them, red, which takes it off in a sheet of its own, with a reason (remove-photo-sheet.tsx).
//
// The first card of the page, as the face says whose page it is. The photo shows for every worker, one who left
// included, as the job keeps what it was; the buttons as Kuingia's do: for a worker working or suspended, none for one
// who left, none on one's own page, where Taarifa zake's line already says why (staff.own). Who may is the rule for a
// worker's details (02 §5), and the server's to ask.
//
// Each button opens a file box of the browser's own, hidden behind it, as a file box can't wear the shop's look. The
// camera's says `capture`, which asks a phone for its camera app, the back one, with its focus and its flash; a laptop's
// browser has none to hand over to, and opens the file picker instead.
//
// On the demo (Jack, PPL-9) both buttons stay on, so a visitor may try them: the sheet shows the photo, and saves
// nothing (photo-sheet.tsx). The page asks the server whether this is the demo and hands the answer down.
//
// After a photo is saved or taken off, one line says so, and the keyboard goes to it; Ghairi gives the keyboard back to
// the button that was tapped, and reads the worker again: a change whose answer was lost may have been made. The sheet
// alone moves the keyboard (its finalFocus, UI-10's review).
//
// "use client": it asks use-intl for words (use-client.test.ts), and keeps the photo picked.
"use client";

import { useQueryClient } from "@tanstack/react-query";
import Image from "next/image";
import { useId, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { Alert, AlertDescription } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { Card, CardContent } from "@/components/design/card";
import type { WhoIsHere } from "@/features/people/who-is-here";
import { photoAddress } from "@/lib/photo-address";

import { CardHeading } from "./card-heading";
import { PhotoSheet } from "./photo-sheet";
import { RemovePhotoSheet } from "./remove-photo-sheet";
import { type Worker, WORKERS } from "./workers";

/** The two ways to a photo, in their order on the card: the camera first, for the worker standing there. */
const WAYS = ["take", "choose"] as const;
type Way = (typeof WAYS)[number];

/** The sheet open: a photo the phone handed over, by the way it came; or the removal of one, the photo that was on the
 * screen as Ondoa picha was tapped, whatever the page reads while the sheet is open. */
type Opened = { by: Way; file: File } | { by: "remove"; photo: string };

export function WorkerPhoto({
  worker,
  me,
  demo = false,
}: {
  worker: Worker;
  me: WhoIsHere;
  /** This is the demo, where no worker's photo is kept. */
  demo?: boolean;
}) {
  const t = useTranslations("workers.photo");
  const store = useQueryClient();
  const titleId = useId();
  const [opened, setOpened] = useState<Opened | null>(null);
  // The line that says what the last change did, or that the worker left meanwhile.
  const [news, setNews] = useState<string | null>(null);
  // The photo the browser failed to open, by its id: a request of its own, which the route can refuse though the worker
  // was read (no network now, a login ended). By its id, so the next photo shows.
  const [failed, setFailed] = useState<string | null>(null);

  const buttons = useRef(new Map<Opened["by"], HTMLButtonElement>());
  const boxes = useRef(new Map<Way, HTMLInputElement>());
  const newsLine = useRef<HTMLDivElement>(null);
  // Whether the last close was a change, for the sheet to give the keyboard to the line: read as the sheet goes, after
  // the draw that took it away, so a ref, not the state (worker-actions.tsx).
  const afterChange = useRef(false);

  // Who may see the buttons (see the top); they stay under an open sheet, so Ghairi gives the keyboard back to the very
  // button that was tapped.
  const showButtons = worker.status !== "left" && worker.id !== me.staff.id;
  // The photo shown, which Ondoa picha names.
  const { photo } = worker;

  function said(sentence: string) {
    afterChange.current = true;
    setOpened(null);
    setNews(sentence);
  }

  function cancelled() {
    setOpened(null);
    // Asked again: a change whose answer was lost may have been made (worker-actions.tsx).
    void store.invalidateQueries({ queryKey: WORKERS });
  }

  function open(sheet: Opened) {
    afterChange.current = false;
    setNews(null);
    setOpened(sheet);
  }

  /** Keeps a button, for the sheet to give the keyboard back to the very one that was tapped. */
  function keepButton(by: Opened["by"], element: HTMLButtonElement | null) {
    if (element) buttons.current.set(by, element);
    else buttons.current.delete(by);
  }

  /** Where the keyboard goes as a sheet goes: after a change, the line; after Ghairi, the very button that was tapped,
   * named (worker-actions.tsx). */
  function keyboardGoes(by: Opened["by"]): HTMLElement | null {
    return afterChange.current
      ? newsLine.current
      : (buttons.current.get(by) ?? null);
  }

  /** The phone handed a photo over, or its camera or gallery was closed with none. */
  function handedOver(way: Way, box: HTMLInputElement) {
    const file = box.files?.[0];
    // Emptied at once: a browser says nothing when the file chosen is the one already in the box, so the same photo,
    // picked again after Ghairi, would open nothing.
    box.value = "";
    if (file !== undefined) open({ by: way, file });
  }

  return (
    <Card>
      <CardContent>
        <section aria-labelledby={titleId} className="grid gap-4">
          {/* No button on the heading's row: its two sit under the photo, side by side (Jack's drawing). */}
          <CardHeading id={titleId} title={t("title")} />
          {photo === null ? (
            <p className="text-muted-foreground">{t("none")}</p>
          ) : photo === failed ? (
            <p className="text-muted-foreground">{t("failed")}</p>
          ) : (
            // Opened from the photos' own route (CTRL-3), as the browser sends the office's login with it. Not shrunk
            // by Next.js, which a static app can't: the phone shrank it already (worker-day.tsx says the same). The
            // size is a hint for the page's layout; the photo keeps its own shape.
            <Image
              // A new photo is a new picture, never the old one with another address while it loads.
              key={photo}
              unoptimized
              src={photoAddress(photo)}
              alt={t("alt", { name: worker.display_name })}
              width={1200}
              height={1600}
              className="h-auto w-40 rounded-lg"
              onError={() => setFailed(photo)}
            />
          )}
          {/* Always on the page, empty and hidden until something happens: a role="status" box is read when its words
              change, and one that appears with its words already in it may not be read at all (offline-banner.tsx). */}
          <div
            ref={newsLine}
            tabIndex={-1}
            className={news ? "outline-none" : "sr-only"}
          >
            <Alert kind="info">
              {news ? <AlertDescription>{news}</AlertDescription> : null}
            </Alert>
          </div>
          {showButtons ? (
            <div className="grid gap-3">
              <div className="flex flex-wrap gap-3">
                {WAYS.map((way) => (
                  <div key={way}>
                    <Button
                      ref={(element) => keepButton(way, element)}
                      kind="second"
                      onClick={() => boxes.current.get(way)?.click()}
                    >
                      {t(way)}
                    </Button>
                    {/* Hidden from the eye, the keyboard and a screen reader alike: the button is its one way in. */}
                    <input
                      ref={(element) => {
                        if (element) boxes.current.set(way, element);
                        else boxes.current.delete(way);
                      }}
                      type="file"
                      accept="image/*"
                      // The camera on the back, as the manager photographs someone else (see the top).
                      capture={way === "take" ? "environment" : undefined}
                      hidden
                      onChange={(event) => handedOver(way, event.target)}
                    />
                  </div>
                ))}
              </div>
              {photo !== null ? (
                <div>
                  <Button
                    ref={(element) => keepButton("remove", element)}
                    // Danger, as Ameondoka: the photo's file goes for good.
                    kind="danger"
                    // Named now, not as it is sent: the photo the person sees as they tap (remove-photo-sheet.tsx).
                    onClick={() => open({ by: "remove", photo })}
                  >
                    {t("remove")}
                  </Button>
                </div>
              ) : null}
            </div>
          ) : null}
          {/* Mounted only while open, so one closed with Ghairi is forgotten, a photo's bytes or a reason with it. */}
          {opened === null ? null : opened.by === "remove" ? (
            <RemovePhotoSheet
              worker={worker}
              photo={opened.photo}
              onDone={(changed) =>
                said(t("removed", { name: changed.display_name }))
              }
              onChangedMeanwhile={said}
              onCancel={cancelled}
              finalFocus={() => keyboardGoes(opened.by)}
            />
          ) : (
            <PhotoSheet
              worker={worker}
              file={opened.file}
              demo={demo}
              onDone={(changed) =>
                said(t("done", { name: changed.display_name }))
              }
              onChangedMeanwhile={said}
              onCancel={cancelled}
              finalFocus={() => keyboardGoes(opened.by)}
            />
          )}
        </section>
      </CardContent>
    </Card>
  );
}
