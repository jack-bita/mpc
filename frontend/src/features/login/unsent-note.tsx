// unsent-note.tsx — the note above the name tiles while records still wait to leave this laptop (SYNC-12,
// 03 §6.7). It owns what someone who has just pressed Toka is told about the records they leave behind.
//
// A note, not a stop (Jack, SYNC-12): logging out loses nothing. The records belong to the laptop, not to
// the person, and the laptop sends them with its own key whoever is logged in, even with the app closed
// (SYNC-8, SYNC-16). So Toka goes through, and the note only says how many wait and that they are safe:
// enough that nobody wipes this laptop's browser, or carries the laptop away, before it has sent them.
//
// Shown whenever the tiles show and records wait, not only straight after Toka: it is as true for the
// next person stepping up, and a note kept for "just after Toka" would need a memory of its own.
//
// "use client": it asks use-intl for words, and reads the laptop's database, in the browser only.
"use client";

import { useTranslations } from "use-intl";

import { Alert, AlertDescription } from "@/components/design/alert";
import { useWaitingCount } from "@/offline/outbox";

export function UnsentNote() {
  const t = useTranslations("login");
  // The outbox's waiting rows, live: the note goes by itself once the push has sent them. The set-aside
  // ones are not counted: they reached the server already, as refused (outbox.ts).
  const waiting = useWaitingCount();

  // Nothing before the first read, nor with nothing waiting.
  if (waiting === undefined || waiting === 0) return null;
  // The info kind: nothing is wrong, and a danger colour here would teach staff to ignore it.
  return (
    <Alert kind="info">
      <AlertDescription>{t("unsent", { count: waiting })}</AlertDescription>
    </Alert>
  );
}
