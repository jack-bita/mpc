// record-advance.tsx — Andika advansi: the button, and the sheet that types money given to a worker before payday
// (WAGE-8), as Jack pictured it (25 Nov 2026):
//
//   ┌──────────────────────────────────┐
//   │ Andika advansi                   │
//   │ Mfanyakazi          ( ) Asha     │
//   │                     (•) Juma     │
//   │ Siku                [ 25/11/2026 ]│
//   │ Kiasi (TSh)         [ 20000      ]│
//   │ Maelezo (si lazima) [ Ada ya shule ]│
//   │ [ Ghairi ]           [ Hifadhi ] │
//   └──────────────────────────────────┘
//
// The workers are the ones the server named for the page's month: paid by the day, with a day of the job in it, and never
// the person here (Jack: A); none is picked at first, so nobody's money goes to the first name by a careless tap. It
// starts on today when the page shows this month, and on no day for a month gone by, as today isn't in it. While a month
// is on its way the button waits where it is, and a sheet already open keeps what is typed in it: neither hangs on the
// list's wait (the review). Who may, and
// what an advance takes, are the server's (record_advance, apps/staffpay/services/money.py); what the sheet can see
// itself is said at once, beside its box, in the server's own sentences: nobody picked, an empty day or one to come, an
// amount that isn't whole shillings above 0. A Sunday is taken: money is asked for on any day. On the demo a note isn't
// kept (demo.no_note), said beside its box.
//
// The id is made here and sent again with every try of the same money (ADR-0007): a save whose answer the network lost,
// tried again, gets the row the first made, never a second. Anything changed is another row, under a new id, as the
// server answers an old id with the row it kept, whatever the new try carries: the list, read again, shows both, for the
// person to cross out the one they didn't mean. Once saved, the sheet closes and a line says what was written, with the
// keyboard on it, as the day may be in a month the list doesn't show.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { useApiErrorWords } from "@/api/errors";
import { aboutTheWholeRequest, answerOf } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription, AlertTitle } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { Choice } from "@/components/design/choice";
import { Field } from "@/components/design/field";
import { Sheet } from "@/components/design/sheet";
import { monthOf, type Weekday } from "@/features/attendance/attendance-month";
import { PAY } from "@/features/pay/pay";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { Decimal } from "@/lib/decimal";
import { formatDay, formatMoney, weekdayOf } from "@/lib/format";
import { newId } from "@/lib/ids";
import { typedAmount } from "@/lib/typed-amount";
import { useOnline } from "@/offline/network";

import { ADVANCES, type AdvancesMonth } from "./advances";

/** The server's longest note (Advance.note, 200 characters). */
const NOTE_LONGEST = 200;

// The fields with a box, beside which their refusals show. A refusal of any other field, a clashing id, shows above the
// buttons.
const ON_A_BOX = new Set(["staff", "date", "amount", "note"]);

/** The form's own checks, by box, as the codes the server would send. */
type Checks = { staff?: string; date?: string; amount?: string };

export function RecordAdvance({
  month,
}: {
  /** The month the page shows, as the server answered it: whom one may be typed for in it, and the shop's today. None
   * while it is on its way. */
  month: AdvancesMonth | undefined;
}) {
  const t = useTranslations("advances.record");
  const [open, setOpen] = useState(false);
  // The month last answered, which an open sheet goes on by while another comes.
  const [lastRead, setLastRead] = useState(month);
  if (month !== undefined && month !== lastRead) setLastRead(month);
  // The line that says what the last save wrote.
  const [news, setNews] = useState<string | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const newsLine = useRef<HTMLDivElement>(null);
  // Whether the last close was a save, for the sheet to give the keyboard to the line: read as the sheet goes, after the
  // draw that took it away, so a ref, not the state (worker-pay.tsx).
  const afterSave = useRef(false);

  return (
    <div className="grid gap-3">
      <Button
        ref={button}
        // Held, not gone, so the page doesn't jump; and the workers of the month before are never offered for this one.
        disabled={month === undefined}
        onClick={() => {
          afterSave.current = false;
          setNews(null);
          setOpen(true);
        }}
      >
        {t("title")}
      </Button>
      {/* Always on the page, empty and hidden until something happens: a status box is read when its words change, and
          one that appears with its words already in it may not be read at all (worker-roles.tsx). */}
      <div
        ref={newsLine}
        tabIndex={-1}
        className={news ? "outline-none" : "sr-only"}
      >
        <Alert kind="info">
          {news ? <AlertDescription>{news}</AlertDescription> : null}
        </Alert>
      </div>
      {open && lastRead !== undefined ? (
        <RecordSheet
          // Today, the shop's, when the month is this one; on a month gone by, no day, as today isn't in it.
          startingDay={
            monthOf(lastRead.today) === lastRead.month ? lastRead.today : ""
          }
          today={lastRead.today}
          workers={lastRead.workers}
          onSaved={(sentence) => {
            afterSave.current = true;
            setOpen(false);
            setNews(sentence);
          }}
          onClose={() => setOpen(false)}
          finalFocus={() =>
            afterSave.current ? newsLine.current : button.current
          }
        />
      ) : null}
    </div>
  );
}

function RecordSheet({
  startingDay,
  today,
  workers,
  onSaved,
  onClose,
  finalFocus,
}: {
  startingDay: string;
  /** The shop's today, as the server last said it: nothing is given on a day after it yet. */
  today: string;
  /** Whom one may be typed for, as the server named them for the page's month. */
  workers: AdvancesMonth["workers"];
  /** Saved: the line that says what, in the person's words. */
  onSaved: (sentence: string) => void;
  onClose: () => void;
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("advances.record");
  const monthWords = useTranslations("attendanceMonth");
  const apiError = useTranslations("apiError");
  const codes = useCodeWords();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  const [staff, setStaff] = useState<string | null>(null);
  const [date, setDate] = useState(startingDay);
  const [typed, setTyped] = useState("");
  const [note, setNote] = useState("");
  const [own, setOwn] = useState<Checks>({});
  // The last send: its id, and what it carried, so a try of the same keeps its id (see the top).
  const lastSend = useRef<{ id: string; carried: string } | null>(null);

  const save = useMutation({
    mutationFn: (body: {
      id: string;
      staff: string;
      date: string;
      amount: string;
      note: string;
    }) => answerOf(api.POST("/api/v1/staffpay/advances/", { body })),
    onSuccess: (row) =>
      onSaved(
        t("saved", {
          amount: formatMoney(new Decimal(row.amount)),
          name: row.display_name,
          weekday: monthWords(
            `weekdays.${String(weekdayOf(row.date)) as Weekday}`,
          ),
          date: formatDay(row.date),
        }),
      ),
    onSettled: () => {
      // The month asked again, whatever the answer: with none, the row may have been made all the same, and the list then
      // shows it. And the pay it comes off (WAGE-2).
      void store.invalidateQueries({ queryKey: ADVANCES });
      void store.invalidateQueries({ queryKey: PAY });
    },
  });

  function send() {
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    save.reset();
    const amount = typedAmount(typed);
    // Days as text sort as days do. The box offers no day to come; one typed by hand is said here, as the server would.
    const checks: Checks = {
      staff: staff === null ? "required" : undefined,
      date:
        date === ""
          ? "required"
          : date > today
            ? "advance.in_future"
            : undefined,
      amount: amount === null ? "advance.amount_invalid" : undefined,
    };
    setOwn(checks);
    if (staff === null || amount === null || checks.date !== undefined) return;
    const body = { staff, date, amount, note };
    const carried = JSON.stringify(body);
    if (lastSend.current?.carried !== carried)
      lastSend.current = { id: newId(), carried };
    save.mutate({ id: lastSend.current.id, ...body });
  }

  // Where each refusal shows: beside its box, the form's own first, then the server's; a field with no box above the
  // buttons, in its own sentence; a refusal of the whole request is ApiErrorAlert's (pay-rate-form.tsx).
  const byField = fieldMessages(save.error);
  const said = (code?: string) =>
    code === undefined ? undefined : codeMessage(codes, code);
  const noBox = Object.entries(byField)
    .filter(([field]) => !ON_A_BOX.has(field))
    .map(([, sentence]) => sentence);

  return (
    <Sheet
      open
      onClose={onClose}
      title={t("title")}
      actionLabel={t("save")}
      onAction={send}
      busy={save.isPending}
      // Offline, nothing is sent, so nothing waits unsent while it looks done (setting-form.tsx); and with nobody to
      // pick there is nothing to send.
      actionDisabled={!online || workers.length === 0}
      finalFocus={finalFocus}
    >
      {workers.length === 0 ? (
        <p>{t("nobody")}</p>
      ) : (
        <Choice
          label={t("worker")}
          error={said(own.staff) ?? byField.staff}
          options={workers.map((worker) => ({
            value: worker.staff,
            // A person hired again in the month has two jobs of one name (PPL-11): the one that ended says when.
            label:
              worker.left_on === null
                ? worker.display_name
                : t("workerLeft", {
                    name: worker.display_name,
                    date: formatDay(worker.left_on),
                  }),
          }))}
          value={staff}
          onValueChange={setStaff}
        />
      )}
      <Field
        label={t("date")}
        error={said(own.date) ?? byField.date}
        type="date"
        max={today}
        value={date}
        onChange={(event) => setDate(event.target.value)}
      />
      <Field
        label={t("amount")}
        error={said(own.amount) ?? byField.amount}
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
        // Digits only on a phone's keypad: the shop's money is whole shillings.
        inputMode="numeric"
        autoComplete="off"
      />
      <Field
        label={t("note")}
        error={byField.note}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        autoComplete="off"
        maxLength={NOTE_LONGEST}
      />
      {noBox.length > 0 ? (
        <Alert kind="danger">
          {/* The icon says what the title says, so a screen reader skips it (api-error-alert.tsx). */}
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{apiError("title")}</AlertTitle>
          <AlertDescription>{noBox.join(" ")}</AlertDescription>
        </Alert>
      ) : (
        // What no field names: one's own, who may, no network, the server's own problem.
        <ApiErrorAlert error={aboutTheWholeRequest(save.error)} />
      )}
    </Sheet>
  );
}
