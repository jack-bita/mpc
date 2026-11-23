// photo-sheet.tsx — a worker's new photo, shown before it is saved (PPL-9): the photo the phone handed over, read and
// shrunk here, on the phone, to about 150 KB (shrink-photo.ts, as a phone's own photo is 3 to 5 MB, and the server keeps
// none over 1 MB), in a sheet over the worker's page (sheet.tsx), titled "Picha ya Asha", with Ghairi and Hifadhi.
//
// What shows is what goes: the small copy, never the phone's own file, whose hidden data (where it was taken, when) the
// copy doesn't hold. Nothing is sent until Hifadhi: then the copy's bytes, as the request's whole body, with no form
// around them, through PUT …/staff/{id}/photo/ (the server's check is by the bytes, apps/control/services.py).
//
// The photo's id is made here as the sheet opens, once (ADR-0007): Hifadhi tapped again, after an answer the network
// lost, sends the same photo under the same id, and the server answers with the one it kept. A photo picked again is
// another sheet, so another photo.
//
// A photo this browser can't read, as some can't an iPhone's HEIC, is said at once, and Hifadhi stays off.
//
// On the demo (Jack, PPL-9) the photo shows and Hifadhi is off, with demo.photos_fixed's own sentence: every visitor
// there is Meneja, so one kept would show to every visitor after, maybe a real person's face. The server refuses one
// too, for a page that doesn't know yet that it is the demo's.
//
// It names the photo it replaces, the one that was on the screen as it was picked, or none: another one shows by now,
// which nobody here saw, and the server refuses (409 version_conflict), as a replaced photo's file is gone for good
// (Jack, PPL-9's review: A). Then, and at staff.left, as someone else marked them left meanwhile, the sheet closes, the
// card says it, and the worker is read again, so the card shows the photo there now. Every other refusal shows above the sheet's buttons, the photo still there to try again: who may
// (staff.own, staff.superuser_only, staff.more_keys), the demo's, the file's own (attachment.*), the id's.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Image from "next/image";
import { useEffect, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription } from "@/components/design/alert";
import { Sheet } from "@/components/design/sheet";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { newId } from "@/lib/ids";
import { shrinkFile } from "@/lib/shrink-photo";
import { useOnline } from "@/offline/network";

import { aboutTheChange, keepWorker, type Worker, WORKERS } from "./workers";

/** The codes that say someone else changed the worker first: the sheet closes, and the card says it. */
const CHANGED_MEANWHILE = new Set(["version_conflict", "staff.left"]);

/** The photo as the sheet has it: still being read; the small copy, with the address an <img> shows it at; or none, as
 * this browser can't read it. */
type Shot = "reading" | { photo: Blob; address: string } | "unreadable";

export function PhotoSheet({
  worker,
  file,
  insteadOf,
  demo,
  onDone,
  onChangedMeanwhile,
  onCancel,
  finalFocus,
}: {
  worker: Worker;
  /** What the phone's camera or gallery handed over. */
  file: File;
  /** The photo that was on the screen as this one was picked, by its id; none, null. */
  insteadOf: string | null;
  /** This is the demo, where no worker's photo is kept. */
  demo: boolean;
  /** Saved: the worker as the server answered. */
  onDone: (worker: Worker) => void;
  /** Someone else changed the worker first: what the server's code says. */
  onChangedMeanwhile: (sentence: string) => void;
  /** Ghairi or Esc. */
  onCancel: () => void;
  /** Where the keyboard goes as the sheet goes (sheet.tsx). */
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("workers.photo");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const codes = useCodeWords();
  const online = useOnline();
  const store = useQueryClient();
  const [id] = useState(newId);
  const [shot, setShot] = useState<Shot>("reading");

  useEffect(() => {
    // Closed, or another photo picked, before this one was read: what comes then is no one's.
    let gone = false;
    let address: string | null = null;
    shrinkFile(file).then(
      (photo) => {
        if (gone) return;
        address = URL.createObjectURL(photo);
        setShot({ photo, address });
      },
      (error: unknown) => {
        // The browser's own words, for whoever looks: the screen says it in the person's.
        console.error("the chosen photo was not read", error);
        if (!gone) setShot("unreadable");
      },
    );
    return () => {
      gone = true;
      // The copy's bytes live in the browser's memory at that address until it is freed.
      if (address !== null) URL.revokeObjectURL(address);
    };
  }, [file]);

  const save = useMutation({
    mutationFn: async (photo: Blob) =>
      answerOf(
        api.PUT("/api/v1/people/staff/{id}/photo/", {
          params: {
            path: { id: worker.id },
            // None is said by leaving it out.
            query: { photo: id, instead_of: insteadOf ?? undefined },
          },
          // The photo's bytes alone, past the client's JSON, as the laptop's photos go (offline/sync/attachments.ts):
          // the server's description names the body a string, as OpenAPI writes any file. fetch gives an ArrayBuffer
          // its length, so the route never has to answer 411 for want of one.
          body: (await photo.arrayBuffer()) as unknown as string,
          bodySerializer: (body) => body,
          headers: { "Content-Type": photo.type },
        }),
      ),
    // Nothing of the face outlives the sheet in the store, which everyone on this phone shares (UI-4).
    gcTime: 0,
    onSuccess: (changed) => {
      // The worker as they are now, on their page and in the list at once, then both asked again (workers.ts).
      keepWorker(store, changed);
      void store.invalidateQueries({ queryKey: WORKERS });
      onDone(changed);
    },
    onError: (error) => {
      if (
        !(error instanceof ApiRefusal) ||
        !CHANGED_MEANWHILE.has(error.body.code)
      )
        return;
      void store.invalidateQueries({ queryKey: WORKERS });
      onChangedMeanwhile(
        error.body.code === "version_conflict"
          ? // Said of the photo, as the code's own sentence says only that something changed.
            t("changedMeanwhile", { name: worker.display_name })
          : codeMessage(codes, error.body.code),
      );
    },
  });

  const ready = typeof shot === "object";
  const code =
    save.error instanceof ApiRefusal ? save.error.body.code : undefined;
  // A refusal that closes the sheet shows nothing here. A field's, as id.taken comes on `id`, has no box to sit beside,
  // so it shows above too, never nowhere (aboutTheChange).
  const closes = code !== undefined && CHANGED_MEANWHILE.has(code);
  const above = closes ? null : aboutTheChange(save.error);

  /** Hifadhi, or Enter: the sheet calls it only while Hifadhi is on (sheet.tsx). */
  function send() {
    if (ready) save.mutate(shot.photo);
  }

  return (
    <Sheet
      open
      onClose={onCancel}
      title={t("sheetTitle", { name: worker.display_name })}
      actionLabel={t("save")}
      onAction={send}
      // Held while it is sent, so a second tap sends nothing, and the sheet stays until its answer comes.
      busy={save.isPending}
      // Off until there is a photo; on the demo, with the line saying why; and offline, so nothing waits unsent while
      // it looks done (setting-form.tsx).
      actionDisabled={!ready || demo || !online}
      finalFocus={finalFocus}
    >
      <p role="status" className={shot === "reading" ? "text-lg" : "sr-only"}>
        {shot === "reading" ? loginWords("waiting") : null}
      </p>
      {ready ? (
        <Image
          unoptimized
          src={shot.address}
          alt={t("newAlt", { name: worker.display_name })}
          width={1200}
          height={1600}
          className="mx-auto h-auto w-56 rounded-lg"
        />
      ) : null}
      {shot === "unreadable" ? (
        <Alert kind="danger">
          <AlertDescription>{t("unreadable")}</AlertDescription>
        </Alert>
      ) : null}
      {demo ? <p>{codeMessage(codes, "demo.photos_fixed")}</p> : null}
      <ApiErrorAlert error={above} />
    </Sheet>
  );
}
