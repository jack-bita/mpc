// device-health.tsx — Hali ya vifaa, the device health page (SYNC-14, 03 §5.17): one card per device of
// the sides the person sees, by its number, saying when it last synced, how many records still wait on
// it, whether its clock is right, which app it runs, and its offline periods of the last week. A device
// that hasn't synced on the shop's today stands out, in words and in the warning colour.
//
// An office screen: it asks the server through the store of server answers (rule 5), GET
// /api/v1/people/devices/health/, and needs the internet, which the office area says while it is gone.
// Who sees which devices is the server's, as on Vifaa: whoever works on a side sees its devices. The
// office home's button for it is for those who look after the devices (office-home.tsx).
//
// The offline periods are by each laptop's own clock, as it reported them (02: DeviceOutage): the page
// says so once, under its title, and a period that ends before it starts, its clock put back meanwhile,
// is shown as the laptop said, with no length. The rules live in health.ts.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useQuery } from "@tanstack/react-query";
import { useNow, useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf } from "@/api/refusal";
import type { components } from "@/api/schema";
import { ApiErrorAlert } from "@/components/api-error-alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/design/card";
import { useWhoIsHere, type WhoIsHere } from "@/features/people/who-is-here";
import { dayPart, formatDate, formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import {
  clockState,
  duration,
  outageLength,
  syncedToday,
  weekOfOutages,
  type Duration,
} from "./health";

type DeviceHealth = components["schemas"]["DeviceHealth"];
type Outage = components["schemas"]["DeviceOutage"];

/** The page's place in the store of server answers. */
export const DEVICE_HEALTH = ["devices", "health"] as const;

/** How often an open page asks the server again, and moves its own clock: every minute. A laptop syncs
 * every 30 s (SYNC_EVERY), so a laptop that comes back shows within a minute or so; and the page left
 * open past midnight reads the new day with the syncs made since, not yesterday's answer alone. */
export const ASK_AGAIN_EVERY = 60_000;

export function DeviceHealthScreen() {
  const t = useTranslations("device.health");
  const who = useWhoIsHere();
  return (
    <div className="grid max-w-3xl gap-6">
      <div className="grid gap-2">
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <p className="text-muted-foreground">{t("intro")}</p>
      </div>
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {who.data ? <HealthList me={who.data} /> : null}
    </div>
  );
}

function HealthList({ me }: { me: WhoIsHere }) {
  const t = useTranslations("device.list");
  // Asked again every minute while the page is open, not only when the window comes back to the front
  // (TanStack's own moments): a manager watching for a laptop to come back sees it, and at midnight the
  // page doesn't mark a laptop that synced a moment later (SYNC-14's review).
  const health = useQuery({
    queryKey: DEVICE_HEALTH,
    queryFn: () => answerOf(api.GET("/api/v1/people/devices/health/")),
    refetchInterval: ASK_AGAIN_EVERY,
  });
  // The clock "today" is read by, moved on as often as the page asks again: at midnight every laptop's
  // last sync is yesterday's for a moment, until the next answer brings the syncs made since.
  const now = useNow({ updateInterval: ASK_AGAIN_EVERY }).getTime();
  // The sides' names, from `me`, as on Vifaa: the page shows only devices of the sides the person sees,
  // and `me` names every one of those.
  const sideNames = new Map(
    me.permissions.sides.map((side) => [side.id, side.name]),
  );

  // A failed read shows above the cards, not in their place: a refresh that fails keeps the last answer on
  // the screen, with the reason above it, as on Vifaa.
  const failure = <ApiErrorAlert error={health.error} />;
  if (!health.data) return failure;
  return (
    <>
      {failure}
      {health.data.length === 0 ? (
        <p>{t("empty")}</p>
      ) : (
        // role="list" written out: Safari with VoiceOver stops calling a <ul> a list once its bullets are
        // styled away, as Tailwind does (device-list.tsx).
        <ul role="list" className="grid gap-4">
          {health.data.map((device) => (
            <li key={device.id}>
              <HealthCard
                device={device}
                side={sideNames.get(device.home_side) ?? ""}
                timezone={me.shop.timezone}
                now={now}
              />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function HealthCard({
  device,
  side,
  timezone,
  now,
}: {
  device: DeviceHealth;
  side: string;
  timezone: string;
  now: number;
}) {
  const t = useTranslations("device.health");
  const list = useTranslations("device.list");
  const when = useWhen(timezone, now);
  const blocked = device.status === "blocked";
  // Marked only while it works: a blocked device can't sync, which its own line already says.
  const behind = !blocked && !syncedToday(device.last_synced_at, timezone, now);

  return (
    <Card className={cn(behind && "ring-2 ring-destructive")}>
      <CardHeader>
        {/* A heading under the page's title, so a screen reader can jump from device to device. The
            card's title is a <div> (shadcn's), so the role says it. */}
        <CardTitle role="heading" aria-level={2}>
          {device.name}
        </CardTitle>
        <CardDescription>
          {list("number", { code: device.code, side })}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2">
        {/* In words, and in the warning colour too: the words alone say it, for anyone who can't tell
            the colours apart. */}
        {blocked ? (
          <p className="font-semibold text-destructive">{list("blocked")}</p>
        ) : null}
        {device.last_synced_at === null ? (
          <p className={cn(behind && "font-semibold text-destructive")}>
            {t("neverSynced")}
          </p>
        ) : (
          <>
            <p className={cn(behind && "font-semibold text-destructive")}>
              {behind
                ? t("notToday", { when: when(device.last_synced_at) })
                : t("lastSync", { when: when(device.last_synced_at) })}
            </p>
            {device.unsent_count === null ? null : (
              <p>{t("waiting", { count: device.unsent_count })}</p>
            )}
            <ClockLine errorSeconds={device.clock_error_seconds} />
            {device.app_version === "" ? null : (
              <p className="text-muted-foreground">
                {t("version", { version: device.app_version })}
              </p>
            )}
          </>
        )}
        <Outages outages={device.outages} timezone={timezone} />
      </CardContent>
    </Card>
  );
}

function ClockLine({ errorSeconds }: { errorSeconds: number | null }) {
  const t = useTranslations("device.health");
  const clock = clockState(errorSeconds);
  if (clock.kind === "unknown") return <p>{t("clockUnknown")}</p>;
  if (clock.kind === "right") return <p>{t("clockRight")}</p>;
  // A clock out by more than the slack makes the laptop's clock-ins wait for review (02 §12): the warning
  // colour, beside the words, so the manager puts it right.
  return (
    <p className="font-semibold text-destructive">
      {clock.kind === "ahead"
        ? t("clockAhead", { minutes: clock.minutes })
        : t("clockBehind", { minutes: clock.minutes })}
    </p>
  );
}

function Outages({
  outages,
  timezone,
}: {
  outages: readonly Outage[];
  timezone: string;
}) {
  const t = useTranslations("device.health");
  const attendance = useTranslations("attendance");
  const length = useLength();
  if (outages.length === 0) return <p>{t("noOutages")}</p>;

  // "10:05 asubuhi" in Swahili, "10:05" in English, in the shop's zone (attendance.timeOfDay).
  const time = (at: string) =>
    attendance("timeOfDay", {
      time: formatTime(at, timezone),
      part: dayPart(at, timezone),
    });
  const week = weekOfOutages(outages);

  return (
    <div className="grid gap-1">
      <p>
        {week.total === null
          ? t("outagesCount", { count: week.count })
          : t("outages", {
              count: week.count,
              total: length(duration(week.total)),
            })}
      </p>
      {/* Newest first, as the server sends them. A period that ends on another day names that day too. */}
      <ul role="list" className="grid gap-1 text-muted-foreground">
        {outages.map((outage) => {
          const day = formatDate(outage.started_at, timezone);
          const endDay = formatDate(outage.ended_at, timezone);
          const to =
            endDay === day
              ? time(outage.ended_at)
              : t("atDay", { date: endDay, time: time(outage.ended_at) });
          const lasted = outageLength(outage);
          const words = { date: day, from: time(outage.started_at), to };
          return (
            <li key={outage.id}>
              {lasted === null
                ? t("periodOdd", words)
                : t("period", {
                    ...words,
                    length: length(duration(lasted)),
                  })}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** When a sync happened, as the page says it: "leo, saa 18:40 jioni" today, else with its date, in the
 * shop's zone. */
function useWhen(timezone: string, now: number): (at: string) => string {
  const t = useTranslations("device.health");
  const attendance = useTranslations("attendance");
  const today = formatDate(new Date(now).toISOString(), timezone);
  return (at) => {
    const time = attendance("timeOfDay", {
      time: formatTime(at, timezone),
      part: dayPart(at, timezone),
    });
    const date = formatDate(at, timezone);
    return date === today ? t("today", { time }) : t("onDay", { date, time });
  };
}

/** A length of time in words: "dakika 25", "saa 2 na dakika 15", "chini ya dakika moja". */
function useLength(): (length: Duration) => string {
  const t = useTranslations("device.health");
  return (length) => {
    if (length.kind === "underAMinute") return t("underAMinute");
    if (length.hours === 0) return t("minutes", { minutes: length.minutes });
    if (length.minutes === 0) return t("hours", { hours: length.hours });
    return t("hoursMinutes", { hours: length.hours, minutes: length.minutes });
  };
}
