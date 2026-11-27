// my-days-and-pay-screen.tsx — Siku na malipo yangu, a worker's own days and pay (WAGE-4, 02 A4; 03 §5.10), as Jack
// pictured it (27 Nov 2026): opened from the PIN's welcome on the shop's laptop, or from the office's home after a
// password, by anyone who works here, with no key.
//
//   ←  Siku na malipo yangu
//      Siku zako na malipo yako.
//    ‹      Novemba 2026      ›
//   [ Siku ]  Malipo
//   ✓ 18 · Ch 2 · ½ 1 · H 0 · ! 0
//   Jt  Jn  Jtn  Al  Ij  Jm  Jp
//   …the month, each day its mark, a tapped day in a sheet (my-days.tsx)
//
// Two tabs, Siku (my-days.tsx) and Malipo (my-pay.tsx), the open one in the address (?tab=malipo), both of the month the
// switch shows. Each asked here, at the page's top, and handed down as values (frontend rules); each says its own
// refusal. A month with no daily pay says so in one sentence on both, in place of the calendar and the lines (WAGE-4's
// default), as the manager's month page lists only those the shop pays by the day (ATT-10).
// The month: this one, on the shop's clock, unless the address names an earlier one (?month=2026-10), as on Advansi,
// whose switch it wears; ‹ stops at the month the job began, and › at this one. Only their own: the server reads the
// job the login names, never an id the page could send (MineViewSet). Only to read: nothing on it changes anything.
//
// An office screen: it asks the server through the store of server answers (rule 5), so with the internet only; the
// laptop's welcome shows its button only to someone the server let in. Nothing of it is kept on the laptop (mine.ts).
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { PageHeader } from "@/components/design/page-header";
import { Tabs } from "@/components/design/tabs";
import { useTabInAddress, useWordInAddress } from "@/components/tab-in-address";
import {
  isMonth,
  MONTH_PARAM,
  monthOf,
} from "@/features/attendance/attendance-month";
import { MonthSwitch, usePagesClock } from "@/features/attendance/month-switch";
import { homeOf, useWhoIsHere } from "@/features/people/who-is-here";
import { shopToday } from "@/offline/rules";

import { useMyDays, useMyPay } from "./mine";
import { MyDays } from "./my-days";
import { MyPay } from "./my-pay";

/** The two tabs, by the word the address keeps: ?tab=malipo. Siku with none, or one it doesn't know. */
const TABS = ["siku", "malipo"] as const;

export function MyDaysAndPayScreen() {
  const t = useTranslations("mine");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  const [asked, choose] = useWordInAddress(MONTH_PARAM);
  // The page's clock, as Advansi keeps it: the month it opened on, kept until the person moves, and this month, as it
  // is now, which › stops at.
  const { openedAt, now } = usePagesClock();
  const timezone = who.data?.shop.timezone ?? null;
  const openedOn =
    timezone === null ? null : monthOf(shopToday(timezone, openedAt));
  const thisMonth =
    timezone === null ? null : monthOf(shopToday(timezone, now));
  // The month the address names, if it is one and not one to come; else the month the page opened on. One before the
  // job began is the server's to refuse, with its words (mine.before_job): the page can't know the job's first day
  // before its first answer.
  const month =
    openedOn === null || thisMonth === null
      ? null
      : asked !== null && isMonth(asked) && asked <= thisMonth
        ? asked
        : openedOn;
  const days = useMyDays(month);
  const pay = useMyPay(month);
  const [askedTab, chooseTab] = useTabInAddress();
  const tab = TABS.find((each) => each === askedTab) ?? "siku";
  // "Subiri kidogo…", through the store's own tries too, and only once there is something to wait for.
  const waiting =
    who.isPending || (month !== null && (days.isPending || pay.isPending));
  // ‹ stops at the job's first month, once the answer says it.
  const firstMonth = days.data ? monthOf(days.data.started_on) : undefined;
  // No line of theirs this month, once a working day of it has come: no daily pay, and no money given.
  const noPay =
    pay.data !== undefined && !pay.data.paid_by_day && !pay.data.no_day_yet;

  return (
    <div className="grid max-w-2xl gap-6">
      {/* The arrow goes back to where the person was; from a fresh tab, to their home: the PIN's welcome at the laptop,
          the office's home on a phone (homeOf). */}
      <PageHeader
        title={t("title")}
        intro={t("intro")}
        fallback={who.data ? homeOf(who.data) : undefined}
      />
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {month !== null && thisMonth !== null ? (
        <MonthSwitch
          month={month}
          thisMonth={thisMonth}
          firstMonth={firstMonth}
          onChoose={choose}
        />
      ) : null}
      {/* Each tab with its own read's refusal: a month refused, as one before the job, says why; a refresh that fails
          keeps the month last read, with the reason above it. */}
      <Tabs
        label={t("title")}
        value={tab}
        onChange={chooseTab}
        sections={[
          {
            value: "siku",
            label: t("days"),
            content: (
              <div className="grid gap-4">
                <ApiErrorAlert error={days.error} />
                {noPay ? (
                  <p>{t("noRate")}</p>
                ) : days.data && !days.isPending ? (
                  <MyDays answer={days.data} timezone={timezone} />
                ) : null}
              </div>
            ),
          },
          {
            value: "malipo",
            label: t("pay"),
            content: (
              <div className="grid gap-4">
                <ApiErrorAlert error={pay.error} />
                {pay.data && !pay.isPending && timezone !== null ? (
                  <MyPay answer={pay.data} timezone={timezone} />
                ) : null}
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}
