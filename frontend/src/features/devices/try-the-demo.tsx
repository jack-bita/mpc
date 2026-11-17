// try-the-demo.tsx — Jaribu demo on the Karibu welcome: one tap makes this browser a laptop of the demo
// shop, with no code to read out and no manager to say yes (OPS-3, BP15). A recruiter has no manager.
//
// It shows only where the server says the demo is open (demo.ts): never on the real server, nor with no
// network, when the tap couldn't work anyway. The tap saves the device, as its own check does, and the
// home page then swaps to the PIN screen by itself, whose tiles show each seller's PIN (staff-picker.tsx).
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";

import { askDemoOpen, DEMO_OPEN, tryTheDemo } from "./demo";

export function TryTheDemo() {
  const t = useTranslations("device.demo");
  // Asked once per visit: whether the database holds a shop that isn't a demo changes only on a deploy.
  const open = useQuery({
    queryKey: DEMO_OPEN,
    queryFn: askDemoOpen,
    staleTime: Infinity,
  });
  // A change: never sent again by itself (query-client.ts). A second tap, after the first was refused, is
  // a new try.
  const tap = useMutation({ mutationFn: tryTheDemo });

  if (open.data !== true) return null;
  return (
    <div className="flex max-w-sm flex-col items-center gap-2 text-center">
      <Button disabled={tap.isPending} onClick={() => tap.mutate()}>
        {t("try")}
      </Button>
      <p className="text-sm text-muted-foreground">{t("explain")}</p>
      <ApiErrorAlert error={tap.error} />
    </div>
  );
}
