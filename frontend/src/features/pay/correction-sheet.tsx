// correction-sheet.tsx — Ongeza marekebisho: the button on a worker's pay page, and the sheet that puts right a mistake
// of an earlier month in this one (WAGE-10), as Jack pictured it (27 Nov 2026):
//
//   ┌────────────────────────────────────────────────┐
//   │ Marekebisho ya Juma                            │
//   │ Desemba 2026                                   │
//   │ (•) Ongeza malipo      ( ) Punguza malipo      │
//   │ Kiasi (TSh)   [ 9000                         ] │
//   │ Sababu        [ Novemba: siku ya 12/11 haikuhesabiwa ] │
//   │ [ Ghairi ]                       [ Hifadhi ]   │
//   └────────────────────────────────────────────────┘
//
// The month is the page's, the one the correction goes in: the server says whether it takes one (`no_correction`), and
// the page offers the button only then, to whoever approves pay, never on their own (offersCorrection). Ongeza malipo is
// picked at first, as Jack drew it; Punguza malipo sends the amount below 0, as the server keeps it. What the sheet can
// see itself is said at once, beside its box, in the server's own sentences: an amount that isn't whole shillings above
// 0, no reason. On the demo the reason is one of the ready ones, picked, as every visitor is the same Meneja.
//
// The id is made here and sent again with every try of the same correction (ADR-0007): a save whose answer the network
// lost, tried again, gets the row the first made, never a second; anything changed is another row, under a new id. Once
// saved, the sheet closes, the pay is asked again, with the new line in it, and a line says what was written, with the
// keyboard on it.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert } from "lucide-react";
import { type RefObject, useRef, useState } from "react";
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
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { Decimal } from "@/lib/decimal";
import { newId } from "@/lib/ids";
import { typedAmount } from "@/lib/typed-amount";
import { useOnline } from "@/offline/network";

import { useReasonWords } from "./corrections";
import { PAY, type WorkerPayMonth } from "./pay";
import { useSignedAmount } from "./pay-lines";

/** The server's longest reason (PayCorrection.reason, 200 characters). */
const REASON_LONGEST = 200;

// The fields with a box, beside which their refusals show. A refusal of any other field, a clashing id, shows above the
// buttons.
const ON_A_BOX = new Set(["amount", "reason"]);

/** Which way the correction goes: added to the pay, or taken off it. */
type Way = "add" | "take";

/** The form's own checks, by box, as the codes the server would send. */
type Checks = { amount?: string; reason?: string };

export function AddCorrection({
  answer,
  month,
  openAtStart,
  onOpened,
}: {
  /** The worker's pay of the page's month, as the server answered it. */
  answer: WorkerPayMonth;
  /** The month in words, "Desemba 2026", as the page's heading says it. */
  month: string;
  /** Opened as the page opens: the address asked for it, as the flag of a late tap does (CORRECTION_PARAM). */
  openAtStart: boolean;
  /** The sheet opened, or closed: the page takes the address's word away, so going back never opens it again. */
  onOpened: () => void;
}) {
  const t = useTranslations("pay.correction");
  const [open, setOpen] = useState(openAtStart);
  // The line that says what the last save wrote.
  const [news, setNews] = useState<string | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const newsLine = useRef<HTMLDivElement>(null);
  // Whether the last close was a save, for the sheet to give the keyboard to the line: read as the sheet goes, after the
  // draw that took it away, so a ref, not the state (record-advance.tsx).
  const afterSave = useRef(false);

  return (
    <div className="grid gap-3">
      <div>
        <Button
          ref={button}
          kind="second"
          onClick={() => {
            afterSave.current = false;
            setNews(null);
            setOpen(true);
          }}
        >
          {t("button")}
        </Button>
      </div>
      {/* Always on the page, empty and hidden until something happens: a status box is read when its words change
          (record-advance.tsx). */}
      <NewsLine news={news} line={newsLine} />
      {open ? (
        <CorrectionSheet
          answer={answer}
          month={month}
          onSaved={(sentence) => {
            afterSave.current = true;
            setOpen(false);
            setNews(sentence);
            onOpened();
          }}
          onClose={() => {
            setOpen(false);
            onOpened();
          }}
          finalFocus={() =>
            afterSave.current ? newsLine.current : button.current
          }
        />
      ) : null}
    </div>
  );
}

function NewsLine({
  news,
  line,
}: {
  news: string | null;
  line: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div ref={line} tabIndex={-1} className={news ? "outline-none" : "sr-only"}>
      <Alert kind="info">
        {news ? <AlertDescription>{news}</AlertDescription> : null}
      </Alert>
    </div>
  );
}

function CorrectionSheet({
  answer,
  month,
  onSaved,
  onClose,
  finalFocus,
}: {
  answer: WorkerPayMonth;
  month: string;
  onSaved: (sentence: string) => void;
  onClose: () => void;
  finalFocus: () => HTMLElement | null;
}) {
  const t = useTranslations("pay.correction");
  const apiError = useTranslations("apiError");
  const codes = useCodeWords();
  const reasonWords = useReasonWords();
  const signed = useSignedAmount();
  const { fieldMessages } = useApiErrorWords();
  const online = useOnline();
  const store = useQueryClient();
  const [way, setWay] = useState<Way>("add");
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  const [own, setOwn] = useState<Checks>({});
  // The last send: its id, and what it carried, so a try of the same keeps its id (see the top).
  const lastSend = useRef<{ id: string; carried: string } | null>(null);
  // On the demo, the ready reasons alone, picked as a Choice; anywhere else, the person's own words.
  const ready = answer.correction_reasons;

  const save = useMutation({
    mutationFn: (body: {
      id: string;
      staff: string;
      month: string;
      amount: string;
      reason: string;
    }) => answerOf(api.POST("/api/v1/staffpay/pay-corrections/", { body })),
    onSuccess: (row) => onSaved(t("saved", { amount: signed(row.amount) })),
    onSettled: () => {
      // The pay asked again, whatever the answer: with none, the row may have been made all the same, and the page then
      // shows it, every month's and everyone's, as a correction moves the whole of Mishahara too.
      void store.invalidateQueries({ queryKey: PAY });
    },
  });

  function send() {
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    save.reset();
    const amount = typedAmount(typed);
    const said = reason.trim();
    const checks: Checks = {
      amount: amount === null ? "correction.amount_invalid" : undefined,
      reason: said === "" ? "correction.reason_missing" : undefined,
    };
    setOwn(checks);
    if (amount === null || said === "") return;
    const body = {
      staff: answer.worker.staff,
      month: answer.month,
      // Below 0 for Punguza malipo, as the server keeps it; negated by the shared Decimal, never by a minus typed on
      // text (rule 3).
      amount: way === "add" ? amount : new Decimal(amount).neg().toFixed(),
      reason: said,
    };
    const carried = JSON.stringify(body);
    if (lastSend.current?.carried !== carried)
      lastSend.current = { id: newId(), carried };
    save.mutate({ id: lastSend.current.id, ...body });
  }

  // Where each refusal shows: beside its box, the form's own first, then the server's; a field with no box above the
  // buttons, in its own sentence; a refusal of the whole request is ApiErrorAlert's (record-advance.tsx).
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
      title={t("title", { name: answer.worker.display_name })}
      description={month}
      actionLabel={t("save")}
      onAction={send}
      busy={save.isPending}
      // Offline, nothing is sent, so nothing waits unsent while it looks done (setting-form.tsx).
      actionDisabled={!online}
      finalFocus={finalFocus}
    >
      <Choice
        label={t("way")}
        options={[
          { value: "add", label: t("add") },
          { value: "take", label: t("take") },
        ]}
        value={way}
        onValueChange={(value) => setWay(value as Way)}
      />
      <Field
        label={t("amount")}
        error={said(own.amount) ?? byField.amount}
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
        // Digits only on a phone's keypad: the shop's money is whole shillings, and the way is picked above.
        inputMode="numeric"
        autoComplete="off"
      />
      {ready.length > 0 ? (
        <Choice
          label={t("reason")}
          hint={t("readyHint")}
          error={said(own.reason) ?? byField.reason}
          options={ready.map((code) => ({
            value: code,
            label: reasonWords(code),
          }))}
          value={reason === "" ? null : reason}
          onValueChange={setReason}
        />
      ) : (
        <Field
          label={t("reason")}
          error={said(own.reason) ?? byField.reason}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          autoComplete="off"
          maxLength={REASON_LONGEST}
        />
      )}
      {noBox.length > 0 ? (
        <Alert kind="danger">
          {/* The icon says what the title says, so a screen reader skips it (api-error-alert.tsx). */}
          <CircleAlert aria-hidden="true" />
          <AlertTitle>{apiError("title")}</AlertTitle>
          <AlertDescription>{noBox.join(" ")}</AlertDescription>
        </Alert>
      ) : (
        // What no field names: one's own, a month approved meanwhile, who may, no network, the server's own problem.
        <ApiErrorAlert error={aboutTheWholeRequest(save.error)} />
      )}
    </Sheet>
  );
}
