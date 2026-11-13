// send-now.tsx — Tuma sasa, on the counter's first screen (SYNC-11, SYNC-9, 03 §6.5): how many records wait
// to leave this laptop, and a button to send them now rather than at the sync's next moment. It owns what a
// seller is told about her records' way to the server.
//
// The count is the outbox's waiting rows, read live (useWaitingCount, outbox.ts): it drops by itself as the
// push sends them, with no reload. A record the server set aside is not counted: it reached the server
// already, as refused, and the needs-attention list shows it.
//
// The button calls nothing: it asks (askToSendNow, asks.ts), and the sync's moments, which may call the
// server, send at once, even during the wait after a failed push (Jack, SYNC-9). With no network at all
// (navigator.onLine false, useOnline) no sync runs (triggers.tsx), so a press would leave her waiting for
// nothing: the button is switched off, and the screen says they go once the network is back, as the
// network's return is a moment of its own. Nothing waiting, no button: there is nothing to send.
//
// "use client": it asks use-intl for words, and reads the laptop's database and network, in the browser only.
"use client";

import { useTranslations } from "use-intl";

import { Button } from "@/components/design/button";
import { useOnline } from "@/offline/network";
import { useWaitingCount } from "@/offline/outbox";
import { askToSendNow } from "@/offline/sync/asks";

export function SendNow() {
  const t = useTranslations("attendance.sendNow");
  const waiting = useWaitingCount();
  const online = useOnline();

  // Nothing until the first read: a "0" that is only "not read yet" would say all were sent.
  if (waiting === undefined) return null;
  if (waiting === 0) return <p>{t("allSent")}</p>;

  return (
    <div className="grid gap-3">
      <p>{t("waiting", { count: waiting })}</p>
      {!online && <p>{t("offline")}</p>}
      <div>
        <Button
          kind="second"
          size="normal"
          disabled={!online}
          onClick={askToSendNow}
        >
          {t("button")}
        </Button>
      </div>
    </div>
  );
}
