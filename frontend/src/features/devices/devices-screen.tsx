// devices-screen.tsx — Vifaa, the shop's devices, on the manager's phone: Sajili kifaa, for a laptop
// waiting with its code, and the list of the shop's devices, with rename, block and unblock (UI-3,
// 03 §5.9).
//
// An office screen: it asks the server through the store of server answers (rule 5), and needs the
// internet, which the office area says while it is gone. It reads who is logged in first, to offer
// Sajili kifaa only to someone who holds device.manage on some side; anyone else, a seller included,
// never sees the button, and sees the list without its buttons. Not logged in, it says to log in first.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { Card, CardContent } from "@/components/design/card";
import { sidesWhere, useWhoIsHere } from "@/features/people/who-is-here";

import { ConfirmDevice, type Device } from "./confirm-device";
import { DEVICE_LIST, DeviceList } from "./device-list";

export function DevicesScreen() {
  const t = useTranslations("device.office");
  const who = useWhoIsHere();
  const client = useQueryClient();
  const [registering, setRegistering] = useState(false);
  const [registered, setRegistered] = useState<Device | null>(null);

  // Where the keyboard goes when the form closes: back to the button that opened it, as the form and
  // the box that had focus are gone. Without it, focus falls to the page's start, and someone on a
  // keyboard or a screen reader is lost (laptops are keyboard first). Counted, so each close moves it.
  const opener = useRef<HTMLButtonElement>(null);
  const [closes, setCloses] = useState(0);
  useEffect(() => {
    if (closes > 0) opener.current?.focus();
  }, [closes]);
  function closeTheForm() {
    setRegistering(false);
    setCloses((count) => count + 1);
  }

  const manageable = who.data ? sidesWhere(who.data, "device.manage") : [];

  return (
    <div className="grid max-w-3xl gap-6">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {/* Always on the page, empty and hidden until a device is registered: a role="status" box is
          read when its words change, and one that appears with its words already in it may not be
          read at all (offline-banner.tsx). */}
      <div className={registered ? undefined : "sr-only"}>
        <Alert kind="info">
          {registered ? (
            <AlertDescription>
              {t("registered", { device: registered.name })}
            </AlertDescription>
          ) : null}
        </Alert>
      </div>
      {registering ? (
        <Card>
          <CardContent>
            <ConfirmDevice
              sides={manageable}
              onDone={(device) => {
                setRegistered(device);
                closeTheForm();
                // The list asks again, so the new laptop is on it.
                void client.invalidateQueries({ queryKey: DEVICE_LIST });
              }}
              onCancel={() => {
                closeTheForm();
                // Asked again here too: a send whose answer was lost may have made the device, and
                // the manager who gives up should still see it on the list.
                void client.invalidateQueries({ queryKey: DEVICE_LIST });
              }}
            />
          </CardContent>
        </Card>
      ) : manageable.length > 0 ? (
        <div>
          <Button
            ref={opener}
            onClick={() => {
              setRegistered(null);
              setRegistering(true);
            }}
          >
            {t("register")}
          </Button>
        </div>
      ) : null}
      {who.data ? <DeviceList me={who.data} /> : null}
    </div>
  );
}
