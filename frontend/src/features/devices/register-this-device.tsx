// register-this-device.tsx — Sajili kifaa hiki: a new device asks to join the shop, shows its code, and
// waits for the manager's yes (UI-3, 03 §5.9, steps 1 and 3).
//
// Three views, by what the device knows:
//   not registered   what to do, and a button that gets a code
//   waiting          the code, big, to read out to the manager; the time it has left; "waiting"
//   registered       its name, side and shop, so a code typed by the wrong shop's manager is seen at once
//
// While it waits, it asks the server every 3 seconds who it is: the same check as the device's own
// (device-check.tsx), sharing its one answer, only faster. Once the manager says yes, the check saves the
// device, and every screen, this one and the top bar, shows it. An expired code stops the asking: the
// manager can't confirm it any more, and a new code is one tap away.
//
// Its route, /register-device/, lives in app/(setup)/, outside the counter's lock on the API (rule 5):
// registering needs the server.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button, ButtonLink } from "@/components/design/button";
import { Card, CardContent } from "@/components/design/card";

import { checkThisDevice, DEVICE_CHECK } from "./device-check";
import {
  codeForReading,
  type Pairing,
  startPairing,
  timeLeft,
} from "./pairing";
import { type ThisDevice, useThisDevice } from "./this-device";

/** How often a waiting device asks whether the manager said yes: soon enough that the laptop shows it
 * while the manager still holds their phone. The device's own check isn't limited (AUTH-5), and 10
 * minutes of it is 200 small requests. */
export const WAIT_CHECK_EVERY = 3000;

export function RegisterThisDevice() {
  const t = useTranslations("device.register");
  const device = useThisDevice();
  // The code on show, kept here, not read from the start's own answer: TanStack empties that the moment
  // a new start is sent, and the screen would flash back to "not registered" while Pata namba mpya asks.
  // Kept, the old code's view stays, its button switched off, until the new code arrives; if the new
  // start is refused, the old view stays too, with the reason under it.
  const [pairing, setPairing] = useState<Pairing | null>(null);
  // A start is a change: never sent again by itself (query-client.ts). A tap sends a new one, and the
  // server retires the old code then, so only the newest code can be confirmed (AUTH-2).
  const client = useQueryClient();
  const start = useMutation({
    mutationFn: startPairing,
    onSuccess: setPairing,
    // pairing.already_paired: this browser's key opens a device now. The manager said yes in the code's
    // last second, after the laptop had stopped asking. The device's check, asked once more, saves the
    // device, and the screen shows it registered. Fetched, not refetched: no screen is watching the
    // check while the code shows as expired.
    onError: (error) => {
      if (
        error instanceof ApiRefusal &&
        error.body.code === "pairing.already_paired"
      )
        void client
          .fetchQuery({ queryKey: DEVICE_CHECK, queryFn: checkThisDevice })
          .catch(() => undefined);
    },
  });

  if (device) return <Registered device={device} />;

  return (
    <div className="flex max-w-xl flex-col gap-4">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      {pairing ? (
        <Waiting
          pairing={pairing}
          onNewCode={() => start.mutate()}
          asking={start.isPending}
        />
      ) : (
        <>
          <p>{t("intro")}</p>
          <div>
            <Button disabled={start.isPending} onClick={() => start.mutate()}>
              {t("start")}
            </Button>
          </div>
        </>
      )}
      {/* Too many starts from the shop's network (throttled, with its minutes), a device already
          registered, or no network. */}
      <ApiErrorAlert error={start.error} />
    </div>
  );
}

/** The time now, moved on every second while the screen is open: the countdown's clock. */
function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, []);
  return now;
}

function Waiting({
  pairing,
  onNewCode,
  asking,
}: {
  pairing: Pairing;
  onNewCode: () => void;
  asking: boolean;
}) {
  const t = useTranslations("device.register");
  const now = useNow();
  const expired = now >= pairing.deadline;

  // The device's check, every 3 seconds while the code works. A "not registered" is its normal answer
  // while the manager types, not a failure (checkThisDevice), so what fails here is only the network or
  // the server: failureReason shows it at the first try (device-lock.tsx says why not `error`).
  const check = useQuery({
    queryKey: DEVICE_CHECK,
    queryFn: checkThisDevice,
    enabled: !expired,
    refetchInterval: WAIT_CHECK_EVERY,
  });

  // The button that asked for the code is gone, and focus with it: it moves to the heading over the
  // code, so a screen reader says what to do next, and Tab goes on from here.
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), [pairing]);

  return (
    <Card>
      <CardContent className="flex flex-col gap-3">
        <h2
          ref={heading}
          tabIndex={-1}
          className="text-lg font-semibold outline-none"
        >
          {expired ? t("expired") : t("giveCode")}
        </h2>
        {expired ? (
          <div>
            <Button disabled={asking} onClick={onNewCode}>
              {t("newCode")}
            </Button>
          </div>
        ) : (
          <>
            {/* Big and spaced, to read out across the counter. The font tells look-alikes apart, and
                the server leaves out the ones it can't (0 and O, 1 and I). */}
            <p className="text-5xl font-semibold tracking-widest">
              {codeForReading(pairing.code)}
            </p>
            <p>{t("timeLeft", { time: timeLeft(pairing.deadline, now) })}</p>
            <p className="text-muted-foreground">{t("waiting")}</p>
          </>
        )}
        <p>{t("where")}</p>
        <ApiErrorAlert error={check.failureReason} />
      </CardContent>
    </Card>
  );
}

function Registered({ device }: { device: ThisDevice }) {
  const t = useTranslations("device.register");

  // The view changes by itself once the manager says yes: focus moves to its heading, so a screen
  // reader says it, as a sighted person sees it.
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);

  return (
    <div className="flex max-w-xl flex-col gap-4">
      <h1
        ref={heading}
        tabIndex={-1}
        className="text-2xl font-semibold outline-none"
      >
        {t("done")}
      </h1>
      {/* The shop by name: a code claimed by another shop's manager shows here at once (03 §5.9). */}
      <p>
        {t("which", {
          device: device.name,
          side: device.homeSide.name,
          shop: device.shop.name,
        })}
      </p>
      <div>
        <ButtonLink href="/">{t("continue")}</ButtonLink>
      </div>
    </div>
  );
}
