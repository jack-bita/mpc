// give-form.tsx — Ongeza kazi (PPL-8): give a worker one of the shop's roles, or one extra key, on one side or on every
// side, through PPL-7's routes (POST …/staff/{id}/give-role/ and …/give-key/). Opens under the worker's roles and
// keys (worker-roles.tsx).
//
// As Jack pictured it (19 Nov 2026): Anapewa nini? first, Cheo or Ruhusa moja ya ziada; then the role or the key;
// then Upande, Pande zote and each side by its name, with its band. No side is picked at first (Jack: yes), so a role
// on every side, a side added later included, is never one careless tap away.
//
// The lists offer only what the server would let this person give (giving.ts, the card's default), and never the
// Owner role. Each list narrows the other: a side picked leaves what may be given there, a role or key picked leaves the
// sides where it may be; a pick no longer on its list counts as no pick (the card: "a choice no longer on them is
// cleared"), worked out on each draw, never stored. The 38 keys show in their eight groups (keys.ts), each group a
// Choice of its own under its heading, all picking the one key (Jack, PPL-8: A), so no shared design piece changes.
//
// The give sends an id the app made (ADR-0007): the same id for a try of the same choices, so a give whose answer the
// network lost, sent again, finds the row the first made and answers as now, never a second row nor
// role.already_given; a new id for choices not sent before, as the server answers an old id with new choices id.taken
// (PPL-7's review). Each set of choices keeps its id for as long as the form is open, not only the last one (PPL-8's
// review): Seller on Dawa sent, its answer lost; Vyakula tried; then Dawa again goes under Dawa's first id, and gets
// the row back, where a new id would hear role.already_given for the person's own give. `side` null is every side.
//
// What the form sees itself is said at once, beside its question, and nothing is sent: a question with no answer
// (`required`). The server's refusals show above the buttons, each in its sentence: role.already_given and
// permission.already_given (another manager got there first), role.superuser_only, staff.temporary_password_open
// (whoever set Juma's temporary password lacks this key: he chooses his own first), demo.people_fixed, id.taken, and
// the giver rule's bare 403 (permission_denied), which the lists make rare. The give has no box of the server's own, so
// a field's code (id.taken comes on `id`) shows there too. staff.left closes the form, says it, and reads the worker
// again: someone marked them left since the page read them, and a worker who left keeps what they held as history.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { api } from "@/api/client";
import { answerOf, ApiRefusal } from "@/api/refusal";
import { ApiErrorAlert } from "@/components/api-error-alert";
import { Button } from "@/components/design/button";
import { Choice, type ChoiceOption } from "@/components/design/choice";
import { SideBand } from "@/components/design/side-band";
import type { WhoIsHere } from "@/features/people/who-is-here";
import { codeMessage, useCodeWords } from "@/i18n/codes";
import { newId } from "@/lib/ids";
import { useOnline } from "@/offline/network";

import {
  type Giving,
  keysOffered,
  rolesOffered,
  type Side,
  sidesOffered,
} from "./giving";
import {
  groupOf,
  isPermission,
  KEY_GROUPS,
  type Permission,
  useKeyWords,
} from "./keys";
import {
  aboutTheChange,
  keepWorker,
  type RolesRead,
  useOnSide,
  useRoleWords,
  type Worker,
  WORKERS,
} from "./workers";

type Kind = Giving["kind"];

/** Pande zote's value among the sides' choices: a Choice's values are text, and the server's every side is null. */
const EVERY_SIDE = "every-side";

/** A side's band in its row: as on Mipangilio ya duka, taller than under the bar, so its colour reads (SHOP-4). */
const SWATCH = "h-3 w-16 rounded-sm";

/** The form's own checks, by question, as the codes the server would send. */
type Checks = { what?: string; choice?: string; side?: string };

/** One send: its id, what it gives where, and the done line's words, worked out as it is sent. */
type Send = { id: string; giving: Giving; side: Side; done: string };

export function GiveForm({
  worker,
  me,
  roles,
  onDone,
  onChangedMeanwhile,
  onCancel,
}: {
  worker: Worker;
  me: WhoIsHere;
  /** The shop's roles, asked by the page as this form opens (worker-page.tsx) and handed down. */
  roles: RolesRead;
  /** Given: the line that says what, in the person's words. */
  onDone: (sentence: string) => void;
  /** Someone else changed the worker first: what the server's code says. */
  onChangedMeanwhile: (sentence: string) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("workers.giving");
  const workerWords = useTranslations("workers");
  const loginWords = useTranslations("login");
  const codes = useCodeWords();
  const online = useOnline();
  const store = useQueryClient();
  const { roleName } = useRoleWords(me);
  const { keyName, groupName } = useKeyWords(me);
  const onSide = useOnSide(me);
  const keysId = useId();

  const [kind, setKind] = useState<Kind | null>(null);
  const [pickedRole, setPickedRole] = useState<string | null>(null);
  const [pickedKey, setPickedKey] = useState<Permission | null>(null);
  // EVERY_SIDE or a side's id; null: none picked yet.
  const [pickedSide, setPickedSide] = useState<string | null>(null);
  const [own, setOwn] = useState<Checks>({});
  // The id each set of choices was sent under, by those choices (see the top). A handful at most: a form is short-lived.
  const sentIds = useRef(new Map<string, string>());

  // The title takes the keyboard as the form opens, so a screen reader says what opened where the button was.
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => title.current?.focus(), []);

  // What is picked, as the lists allow it now (see the top). The side first, as it narrows the roles and keys.
  const side: Side | undefined =
    pickedSide === null
      ? undefined
      : pickedSide === EVERY_SIDE
        ? null
        : pickedSide;
  const roleList = rolesOffered(roles.data ?? [], me, worker, side);
  const keyList = keysOffered(me, worker, side);
  const role =
    kind === "role"
      ? roleList.find((each) => each.id === pickedRole)
      : undefined;
  const key =
    kind === "key" && pickedKey !== null && keyList.includes(pickedKey)
      ? pickedKey
      : undefined;
  const giving: Giving | undefined = role
    ? { kind: "role", role }
    : key
      ? { kind: "key", key }
      : undefined;
  const sideList = sidesOffered(me, worker, giving);
  const sideNow =
    side !== undefined && sideList.includes(side) ? side : undefined;
  // Nothing the form could send yet (PPL-8's review): the roles on their way or not read, or no role or key
  // left to give. The line on the form says which; Hifadhi waits meanwhile.
  const waitingForRoles = kind === "role" && roles.isPending;
  const nothingToPick =
    (kind === "role" && (roles.data === undefined || roleList.length === 0)) ||
    (kind === "key" && keyList.length === 0);

  const give = useMutation({
    mutationFn: (send: Send) => {
      const params = { path: { id: worker.id } };
      return send.giving.kind === "role"
        ? answerOf(
            api.POST("/api/v1/people/staff/{id}/give-role/", {
              params,
              body: { id: send.id, role: send.giving.role.id, side: send.side },
            }),
          )
        : answerOf(
            api.POST("/api/v1/people/staff/{id}/give-key/", {
              params,
              body: {
                id: send.id,
                permission: send.giving.key,
                side: send.side,
              },
            }),
          );
    },
    onSuccess: (changed, send) => {
      // The worker as they are now, on their page and in the list at once, then both asked again (workers.ts).
      keepWorker(store, changed);
      void store.invalidateQueries({ queryKey: WORKERS });
      onDone(send.done);
    },
    onError: (error) => {
      // Marked left since the page read them: read them again, so the page shows no buttons (worker-actions.tsx).
      if (error instanceof ApiRefusal && error.body.code === "staff.left") {
        void store.invalidateQueries({ queryKey: WORKERS });
        onChangedMeanwhile(codeMessage(codes, error.body.code));
      }
    },
  });

  function send(event: FormEvent) {
    // The browser would send the form itself and load a new page; the app sends it instead.
    event.preventDefault();
    // The last send's refusal is about what was sent then: each tap shows only what it finds (setting-form.tsx).
    give.reset();
    const checks: Checks = {};
    if (kind === null) checks.what = "required";
    else if (giving === undefined) checks.choice = "required";
    if (sideNow === undefined) checks.side = "required";
    setOwn(checks);
    if (giving === undefined || sideNow === undefined) return;
    // The same id for choices sent before, whenever; a new one for choices never sent (see the top).
    const carried = JSON.stringify([
      giving.kind,
      giving.kind === "role" ? giving.role.id : giving.key,
      sideNow,
    ]);
    const id = sentIds.current.get(carried) ?? newId();
    sentIds.current.set(carried, id);
    const what =
      giving.kind === "role" ? roleName(giving.role) : keyName(giving.key);
    give.mutate({
      id,
      giving,
      side: sideNow,
      done: t("done", {
        name: worker.display_name,
        what: onSide(what, sideNow),
      }),
    });
  }

  const sayCode = (code?: string) =>
    code === undefined ? undefined : codeMessage(codes, code);

  // Pande zote first, then each side by its name and band, as `me` lists them.
  const sideOptions: ChoiceOption[] = sideList.map((each) => {
    if (each === null)
      return { value: EVERY_SIDE, label: workerWords("allSides") };
    const found = me.permissions.sides.find((one) => one.id === each);
    return {
      value: each,
      label: found?.name ?? each,
      picture: found ? (
        <SideBand look={found.band} className={SWATCH} />
      ) : undefined,
    };
  });

  return (
    // noValidate: the browser's own checks would speak its language, not the shop's.
    <form noValidate onSubmit={send} className="grid gap-6">
      <h2
        ref={title}
        tabIndex={-1}
        className="text-lg font-semibold outline-none"
      >
        {t("title", { name: worker.display_name })}
      </h2>
      <Choice
        label={t("what")}
        hint={t("whatHint")}
        error={sayCode(own.what)}
        options={[
          { value: "role", label: t("aRole") },
          { value: "key", label: t("aKey") },
        ]}
        value={kind}
        onValueChange={(value) => setKind(value === "key" ? "key" : "role")}
      />
      {/* The roles are asked as the form opens: a moment's wait, said as the office says it. Always on the form, empty
          until then: a role="status" box is read when its words change, not when it appears with them (PPL-8's
          review, offline-banner.tsx). */}
      <p role="status" className={waitingForRoles ? undefined : "sr-only"}>
        {waitingForRoles ? loginWords("waiting") : null}
      </p>
      {/* A read of the roles that failed: above the list if one came before (a refresh), else in its place. */}
      {kind === "role" ? <ApiErrorAlert error={roles.error} /> : null}
      {kind === "role" ? (
        roles.data === undefined ? null : roleList.length === 0 ? (
          <p>{t("noRole")}</p>
        ) : (
          <Choice
            label={t("role")}
            error={sayCode(own.choice)}
            options={roleList.map((each) => ({
              value: each.id,
              label: roleName(each),
            }))}
            value={role?.id ?? null}
            onValueChange={setPickedRole}
          />
        )
      ) : null}
      {kind === "key" ? (
        keyList.length === 0 ? (
          <p>{t("noKey")}</p>
        ) : (
          // One question, Ruhusa gani?, over eight groups: each group its own Choice under its heading, picking the one
          // key. The question names the whole, as Choice's own name does (choice.tsx).
          <div
            role="group"
            aria-labelledby={`${keysId}-label`}
            aria-describedby={own.choice ? `${keysId}-error` : undefined}
            className="grid gap-4"
          >
            <p
              id={`${keysId}-label`}
              className="text-base leading-snug font-semibold"
            >
              {t("key")}
            </p>
            {own.choice ? (
              <p
                id={`${keysId}-error`}
                className="text-base font-medium text-destructive"
              >
                {sayCode(own.choice)}
              </p>
            ) : null}
            {KEY_GROUPS.map((group) => {
              const inGroup = keyList.filter((each) => groupOf(each) === group);
              // A group with nothing to offer stays off the form, heading and all.
              return inGroup.length === 0 ? null : (
                <Choice
                  key={group}
                  label={groupName(group)}
                  options={inGroup.map((each) => ({
                    value: each,
                    label: keyName(each),
                  }))}
                  value={key ?? null}
                  onValueChange={(value) => {
                    if (isPermission(value)) setPickedKey(value);
                  }}
                />
              );
            })}
          </div>
        )
      ) : null}
      <Choice
        label={t("side")}
        hint={t("sideHint")}
        error={sayCode(own.side)}
        options={sideOptions}
        value={
          sideNow === undefined ? null : sideNow === null ? EVERY_SIDE : sideNow
        }
        onValueChange={setPickedSide}
      />
      {/* Who may and what is already there (see the top), no network, the server's own problem. */}
      <ApiErrorAlert
        error={
          // staff.left closes the form instead (see the top).
          give.error instanceof ApiRefusal &&
          give.error.body.code === "staff.left"
            ? null
            : aboutTheChange(give.error)
        }
      />
      <div className="flex flex-wrap gap-3">
        {/* Switched off while it is sent, so a second tap sends nothing, and while offline, so nothing waits unsent
            while it looks done (setting-form.tsx). */}
        {/* And while there is nothing to pick, as the line above it says why: the roles on their way, their read
            failed, or nothing left to give (PPL-8's review). */}
        <Button
          type="submit"
          disabled={give.isPending || !online || nothingToPick}
        >
          {workerWords("actions.save")}
        </Button>
        <Button kind="second" onClick={onCancel}>
          {workerWords("actions.cancel")}
        </Button>
      </div>
    </form>
  );
}
