// device-list.tsx — the shop's devices on the manager's phone: each one's name, number, side, whether it
// works and when it last reached the server; rename, block and unblock (UI-3, 03 §5.9, step 4).
//
// GET /api/v1/people/devices/ lists the devices of the sides the person sees, a seller included, who
// changes none of them (Jack, 2 Nov 2026). The buttons show only on a device whose home side the person
// holds device.manage on; the server checks the key again on every change (PPL-5).
//
// "Kilionekana dakika 3 zilizopita": a stolen phone that keeps calling shows when, as a block keeps it
// seen (AUTH-2). A block stops the device at its next request, and the laptop locks (device-lock.tsx);
// an unblock lets the same key work again, so what the device holds can still arrive (AUTH-1). Both ask
// why, which the audit trail keeps with who and when (rule 7).
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { useFormatter, useNow, useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { answerOf, ApiRefusal } from "@/api/refusal";
import type { components } from "@/api/schema";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/design/card";
import { Field } from "@/components/design/field";
import { sidesWhere, type WhoIsHere } from "@/features/people/who-is-here";

import type { Device } from "./confirm-device";

type DevicePage = components["schemas"]["PaginatedDeviceList"];

/** The list's place in the store of server answers. Sajili kifaa asks it again once a device is made. */
export const DEVICE_LIST = ["devices", "list"] as const;

/** Every device the person sees, page after page (50 a page, newest first), by their number. A shop has
 * a handful, so one screen holds them all. */
async function allDevices(): Promise<Device[]> {
  const devices: Device[] = [];
  let cursor: string | null = null;
  do {
    // Named, as TypeScript can't work out a type that the loop's own cursor feeds back into.
    const page: DevicePage = await answerOf(
      api.GET("/api/v1/people/devices/", {
        params: { query: cursor === null ? {} : { cursor } },
      }),
    );
    devices.push(...page.results);
    // The next page's address, in full; only its cursor is ours to send back.
    cursor = page.next ? new URL(page.next).searchParams.get("cursor") : null;
  } while (cursor !== null);
  // By number, as the shop counts them (D7): the first laptop first.
  return devices.sort((first, second) => first.code - second.code);
}

export function DeviceList({ me }: { me: WhoIsHere }) {
  const t = useTranslations("device.list");
  const list = useQuery({ queryKey: DEVICE_LIST, queryFn: allDevices });

  // The sides' names, from `me`: the list shows only devices of the sides the person sees, and `me`
  // names every one of those (MePermissionsSerializer).
  const sideNames = new Map(
    me.permissions.sides.map((side) => [side.id, side.name]),
  );
  const managed = new Set(
    sidesWhere(me, "device.manage").map((side) => side.id),
  );

  // A failed read shows above the list, not in its place: when a refresh fails (the window came back
  // to the front after the session ended, or the network dropped), the devices last read stay on the
  // screen, with the reason above them. TanStack keeps the last answer beside the new error.
  const failure = <ApiErrorAlert error={list.error} />;
  if (!list.data) return failure;
  return (
    <>
      {failure}
      {list.data.length === 0 ? (
        <p>{t("empty")}</p>
      ) : (
        // A list, so a screen reader says how many devices there are.
        <ul className="grid gap-4">
          {list.data.map((device) => (
            <li key={device.id}>
              <DeviceCard
                device={device}
                side={sideNames.get(device.home_side) ?? ""}
                mayChange={managed.has(device.home_side)}
              />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

// What the card shows under its name: nothing to type, or one of the three forms.
type Mode = "view" | "rename" | "block" | "unblock";

function DeviceCard({
  device,
  side,
  mayChange,
}: {
  device: Device;
  side: string;
  mayChange: boolean;
}) {
  const t = useTranslations("device.list");
  const format = useFormatter();
  // The clock "Kilionekana dakika 3 zilizopita" counts from, moved on every minute.
  const now = useNow({ updateInterval: 60_000 });
  const [mode, setMode] = useState<Mode>("view");

  // Where the keyboard goes when a form closes: back to the button that opened it, as the form and the
  // box that had focus are gone (laptops are keyboard first). After a block it lands on Zuia, which
  // becomes Fungua when the list answers again: React keeps the one <button> in that place and changes
  // its words, so the focus stays. A new object each time, so each close moves it.
  const renameButton = useRef<HTMLButtonElement>(null);
  const statusButton = useRef<HTMLButtonElement>(null);
  const [backTo, setBackTo] = useState<{ button: "rename" | "status" } | null>(
    null,
  );
  useEffect(() => {
    if (backTo === null) return;
    (backTo.button === "rename" ? renameButton : statusButton).current?.focus();
  }, [backTo]);
  function close(button: "rename" | "status") {
    setMode("view");
    setBackTo({ button });
  }
  const blocked = device.status === "blocked";

  // The browser writes some of these with a capital ("Sekunde 10 zilizopita"), and the phrase sits
  // mid-sentence. No English one starts with a name, so lowering the first letter is safe in both.
  const seen = device.last_seen_at
    ? format.relativeTime(new Date(device.last_seen_at), now)
    : null;
  const seenText = seen
    ? t("seen", { when: seen.charAt(0).toLowerCase() + seen.slice(1) })
    : t("neverSeen");

  return (
    <Card>
      <CardHeader>
        {/* A heading under the page's "Vifaa", so a screen reader can jump from device to device. The
            card's title is a <div> (shadcn's), so the role says it. */}
        <CardTitle role="heading" aria-level={2}>
          {device.name}
        </CardTitle>
        <CardDescription>
          {t("number", { code: device.code, side })}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {/* In words, and the blocked one in red too: the words alone say it, for anyone who can't tell
            the colours apart. */}
        <p
          className={
            blocked ? "font-semibold text-destructive" : "font-semibold"
          }
        >
          {blocked ? t("blocked") : t("active")}
        </p>
        <p className="text-muted-foreground">{seenText}</p>
        {mode === "rename" ? (
          <RenameForm device={device} onClose={() => close("rename")} />
        ) : mode === "block" || mode === "unblock" ? (
          <StatusForm
            device={device}
            change={mode}
            onClose={() => close("status")}
          />
        ) : mayChange ? (
          <div className="flex flex-wrap gap-3">
            <Button
              ref={renameButton}
              kind="second"
              size="normal"
              onClick={() => setMode("rename")}
            >
              {t("rename")}
            </Button>
            {blocked ? (
              <Button
                ref={statusButton}
                kind="second"
                size="normal"
                onClick={() => setMode("unblock")}
              >
                {t("unblock")}
              </Button>
            ) : (
              <Button
                ref={statusButton}
                kind="danger"
                size="normal"
                onClick={() => setMode("block")}
              >
                {t("block")}
              </Button>
            )}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** The sentence for a refusal that belongs to the one box a form has, or nothing. A service's refusal
 * names no field (apps/core/api/errors.py); `codes` says which of them are about the box. */
function boxError(
  error: unknown,
  field: string,
  codes: RegExp,
  words: ReturnType<typeof useApiErrorWords>,
): string | undefined {
  const byField = words.fieldMessages(error)[field];
  if (byField) return byField;
  if (error instanceof ApiRefusal && codes.test(error.body.code))
    return words.message(error);
  return undefined;
}

function RenameForm({
  device,
  onClose,
}: {
  device: Device;
  onClose: () => void;
}) {
  const t = useTranslations("device.list");
  const words = useApiErrorWords();
  const client = useQueryClient();
  const [name, setName] = useState(device.name);

  const rename = useMutation({
    // The version the list showed goes back with the new name: if someone renamed the device since, the
    // server refuses (409 version_conflict), and nobody's name is lost unseen (apps/core/editing.py).
    mutationFn: () =>
      answerOf(
        api.PATCH("/api/v1/people/devices/{id}/", {
          params: { path: { id: device.id } },
          body: { name, version: device.version },
        }),
      ),
    onSuccess: onClose,
    // Asked again whatever happened: after a change it shows the new name, and after a conflict it
    // holds the other person's name and the new version, so the next try can pass.
    onSettled: () => client.invalidateQueries({ queryKey: DEVICE_LIST }),
  });

  const nameError = boxError(rename.error, "name", /^device\.name_/, words);

  function send(event: FormEvent) {
    event.preventDefault();
    rename.mutate();
  }

  return (
    <form noValidate onSubmit={send} className="grid gap-4">
      <Field
        label={t("newName")}
        error={nameError}
        value={name}
        onChange={(event) => setName(event.target.value)}
        // The person just asked for this form: the keyboard starts in its box.
        autoFocus
        autoComplete="off"
        maxLength={40}
      />
      {/* What the box can't show: someone renamed it meanwhile, no network, no key. */}
      <ApiErrorAlert error={nameError ? null : rename.error} />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" size="normal" disabled={rename.isPending}>
          {t("save")}
        </Button>
        <Button kind="second" size="normal" onClick={onClose}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}

function StatusForm({
  device,
  change,
  onClose,
}: {
  device: Device;
  change: "block" | "unblock";
  onClose: () => void;
}) {
  const t = useTranslations("device.list");
  const words = useApiErrorWords();
  const client = useQueryClient();
  const [reason, setReason] = useState("");

  const send = useMutation({
    // No version: a block is urgent, and never refused because someone renamed the device a moment ago
    // (AUTH-1). Sent twice, the second is refused as already done (device.not_active, .not_blocked).
    mutationFn: () =>
      answerOf(
        change === "block"
          ? api.POST("/api/v1/people/devices/{id}/block/", {
              params: { path: { id: device.id } },
              body: { reason },
            })
          : api.POST("/api/v1/people/devices/{id}/unblock/", {
              params: { path: { id: device.id } },
              body: { reason },
            }),
      ),
    onSuccess: onClose,
    onSettled: () => client.invalidateQueries({ queryKey: DEVICE_LIST }),
  });

  const reasonError = boxError(
    send.error,
    "reason",
    /^device\.reason_required$/,
    words,
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    send.mutate();
  }

  const blocking = change === "block";
  return (
    <form noValidate onSubmit={submit} className="grid gap-4">
      <Field
        label={blocking ? t("blockReason") : t("unblockReason")}
        hint={blocking ? t("blockHint") : t("unblockHint")}
        error={reasonError}
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        // The person just asked for this form: the keyboard starts in its box.
        autoFocus
        maxLength={500}
      />
      <ApiErrorAlert error={reasonError ? null : send.error} />
      <div className="flex flex-wrap gap-3">
        {/* A block takes the device away from the shop's work: the danger kind. An unblock gives it
            back: the main kind. */}
        <Button
          type="submit"
          kind={blocking ? "danger" : "main"}
          size="normal"
          disabled={send.isPending}
        >
          {blocking ? t("blockConfirm") : t("unblockConfirm")}
        </Button>
        <Button kind="second" size="normal" onClick={onClose}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}
