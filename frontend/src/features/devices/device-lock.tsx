// device-lock.tsx — a blocked device shows only the lock, on every page (UI-3, 03 §5.9, step 4).
//
// The manager blocks a stolen or lost laptop from their own phone. At the laptop's next request the
// server answers device.blocked, device-check.tsx keeps it, and this covers every page with one message:
// which device this is, and who can open it. Nothing of the shop's work shows behind it.
//
// The block is kept on the device, so a reload with no network stays locked (this-device.ts says the
// honest limit). An unblock opens it at the next check, or at once when someone taps Jaribu tena. The
// laptop's key never changed, so what it holds can still reach the server then (03 §5.9).
//
// The root layout puts it around every page. The device's check stays outside it, so it goes on asking
// while the lock is shown, and so does the new-version bar.
//
// "use client": it reads the device's saved copy, and asks use-intl for words (use-client.test.ts).
"use client";

import { useQuery } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslations } from "use-intl";

import { ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription, AlertTitle } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { TopBar } from "@/components/design/top-bar";
import { LanguageButton } from "@/components/language-button";
import { OfflineBanner } from "@/components/offline-banner";

import { checkThisDevice, DEVICE_CHECK } from "./device-check";
import { useDeviceBlocked, useThisDevice } from "./this-device";

/** The page, or the lock in its place while the device is blocked. */
export function DeviceLock({ children }: { children: ReactNode }) {
  const blocked = useDeviceBlocked();
  return blocked ? <LockScreen /> : children;
}

function LockScreen() {
  const t = useTranslations("device.lock");
  const device = useThisDevice();
  // The device's own check, the same answer DeviceCheck keeps (one place in the store). enabled: false,
  // as DeviceCheck already asks on its own times: this only reads how the last check went, and asks
  // again when the button is tapped.
  const check = useQuery({
    queryKey: DEVICE_CHECK,
    queryFn: checkThisDevice,
    enabled: false,
  });
  // A failed check that is the block itself says nothing new: the lock already says it. Anything else,
  // like a server that can't be reached, is shown, so a tap that changes nothing still says why.
  // failureReason, not error: a lost answer is tried twice more, about 3 seconds in all
  // (query-client.ts), and `error` stays empty until the last try; failureReason holds each try's
  // failure at once, and empties on success. While the browser itself says it is offline, no try is
  // made at all (TanStack pauses it), so no failure comes: the offline banner under the bar says why.
  const failure =
    check.failureReason instanceof ApiRefusal &&
    check.failureReason.body.code === "device.blocked"
      ? null
      : check.failureReason;

  return (
    // The same frame as every screen (AppFrame), with the shop's name if the device knew it, so the
    // person holding it sees whose laptop this is. No area: the lock belongs to none.
    <div className="flex min-h-svh flex-col">
      <TopBar
        shop={device?.shop.name}
        side={device ? { name: device.homeSide.name } : undefined}
        actions={<LanguageButton />}
      />
      {/* Inahitaji mtandao while the network is gone, as on office screens: a tap on Jaribu tena then
          asks nothing, and without it the lock would say nothing either. */}
      <OfflineBanner />
      {/* The page's one <main>: the lock takes the place of the page, and of its <main>. */}
      <main className="flex flex-1 flex-col gap-4 p-4">
        <Alert kind="danger">
          {/* The icon says what the title says, so a screen reader skips it. */}
          <Lock aria-hidden="true" />
          <AlertTitle>{t("title")}</AlertTitle>
          <AlertDescription>
            {/* Which device, so the manager knows which one to unblock: the name on their list. */}
            {device ? (
              <p>
                {t("which", { device: device.name, shop: device.shop.name })}
              </p>
            ) : null}
            <p>{t("ask")}</p>
          </AlertDescription>
        </Alert>
        <ApiErrorAlert error={failure} />
        <div>
          <Button
            kind="main"
            disabled={check.isFetching}
            onClick={() => void check.refetch()}
          >
            {t("tryAgain")}
          </Button>
        </div>
      </main>
    </div>
  );
}
