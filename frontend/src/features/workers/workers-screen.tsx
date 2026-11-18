// workers-screen.tsx — Wafanyakazi, the shop's workers, on the owner's phone (PPL-6, 03 §5.10): each worker's
// nickname and full name, the roles they hold with their sides, and whether they work, are suspended, or left.
//
// As Jack pictured it at PPL-4 (17 Nov 2026): the list first; a name opens the worker's own page, with everything
// of theirs and the buttons. Those still at the shop come first, newest first as the server sends them, so a worker
// just added is at the top; those who left sit under their own heading at the bottom (a default of the card), so
// the list a manager reads each day stays short as the years add names.
//
// Above the list, Ongeza opens the form for a new worker (worker-form.tsx); once he is added, one line says so, and
// that his name reaches the shop's laptops once PPL-8 gives him a PIN. On the demo, its Simu box is off (PPL-11).
//
// An office screen: it asks the server through the store of server answers (rule 5), and needs the internet,
// which the office area says while it is gone. Its routes ask staff.manage on the whole shop (PPL-4); someone
// without it has no button on the office home, and opening the address shows the server's refusal.
//
// "use client": it asks use-intl for words (use-client.test.ts), and calls the server.
"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useFormatter, useTranslations } from "use-intl";

import { ApiErrorAlert } from "@/components/api-error-alert";
import { Alert, AlertDescription } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { Card, CardContent } from "@/components/design/card";
import { PageHeader } from "@/components/design/page-header";
import { TextLink } from "@/components/design/text-link";
import { askDemoOpen, DEMO_OPEN } from "@/features/devices/demo";
import { useWhoIsHere, type WhoIsHere } from "@/features/people/who-is-here";
import { shopToday } from "@/offline/rules";

import { WorkerForm } from "./worker-form";
import {
  type GivenRole,
  mayManageStaff,
  useRoleWords,
  useWorkers,
  type Worker,
  workerPage,
  WORKERS,
} from "./workers";

export function WorkersScreen() {
  const t = useTranslations("workers");
  // The PIN login's book, for its "Subiri kidogo…", which the office says the same way.
  const loginWords = useTranslations("login");
  const who = useWhoIsHere();
  const workers = useWorkers();
  // Until both answer the first time: "Subiri kidogo…", never a title with nothing under it. The line is on the
  // page from the start and only its words change, as one that comes with its words in it often goes unsaid
  // (offline-banner.tsx). Through the store's own tries too: a read that found no network, or a 5xx, is asked again
  // for some 3 seconds before it fails for good, and is pending all that time, with no answer and no error yet, so
  // a wait that counted only the first try left a page with nothing on it (PPL-6's review).
  const waiting = who.isPending || workers.isPending;

  return (
    <div className="grid max-w-2xl gap-6">
      <PageHeader title={t("title")} intro={t("intro")} />
      <p role="status" className={waiting ? "text-lg" : "sr-only"}>
        {waiting ? loginWords("waiting") : null}
      </p>
      {/* Not logged in ("Ingia kwanza"), no network, or the server's own problem. */}
      <ApiErrorAlert error={who.error} />
      {/* As soon as the page knows who is here, never tied to the list's wait: a list whose first read failed goes
          back to waiting at each new read (TanStack sets a query with no answer back to pending), and Ongeza would
          go with it, the half-typed form, its id and the line that says who was added (PPL-6's review). */}
      {who.data ? <AddWorker me={who.data} /> : null}
      {/* The list is asked here alone and handed down, never asked again by the part that shows it: a part
          that mounts on a failed read asks it again (TanStack's retryOnMount), which brings the wait back,
          which takes the part away, which mounts again on the next failure, round and round, asking the
          server many times a second. */}
      {who.data && !waiting ? (
        <WorkerList me={who.data} list={workers} />
      ) : null}
    </div>
  );
}

/** Ongeza, its form, and the line that says who was added. Only for someone holding staff.manage on the whole
 * shop, as the server asks; anyone else, who reached the page by its address, sees the list's refusal alone. */
function AddWorker({ me }: { me: WhoIsHere }) {
  const t = useTranslations("workers");
  const store = useQueryClient();
  // The shop's today, read as the form opens, not as the page did: a page left open overnight starts the first day's
  // box on the new day.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const [added, setAdded] = useState<Worker | null>(null);
  // Whether this is the demo, where no worker gets a phone (PPL-10, PPL-11), as the worker's page asks it: here, the
  // part always on the page once the person is known, only once the form opens, and once a visit. Unknown, or not
  // answered, the box is on: the server refuses a phone on the demo all the same (demo.phones_fixed).
  const demo = useQuery({
    queryKey: DEMO_OPEN,
    queryFn: askDemoOpen,
    staleTime: Infinity,
    enabled: openOn !== null,
  });

  // Where the keyboard goes when the form closes: back to Ongeza, as the form and the box that had focus are gone
  // (laptops are keyboard first). Counted, so each close moves it (devices-screen.tsx).
  const opener = useRef<HTMLButtonElement>(null);
  const [closes, setCloses] = useState(0);
  useEffect(() => {
    if (closes > 0) opener.current?.focus();
  }, [closes]);
  function closeTheForm() {
    setOpenOn(null);
    setCloses((count) => count + 1);
  }

  if (!mayManageStaff(me)) return null;
  return (
    <>
      {/* Always on the page, empty and hidden until a worker is added: a role="status" box is read when its words
          change, and one that appears with its words already in it may not be read at all (offline-banner.tsx). */}
      <div className={added ? undefined : "sr-only"}>
        <Alert kind="info">
          {added ? (
            <AlertDescription>
              {/* No field says who has a PIN, so it is said here, once, for the worker just added (a default of the
                  card): a laptop shows a tile only for someone with one (PPL-4's review), which PPL-8 gives. */}
              {t("added", { name: added.display_name })}
            </AlertDescription>
          ) : null}
        </Alert>
      </div>
      {openOn !== null ? (
        <Card>
          <CardContent>
            <WorkerForm
              today={openOn}
              demo={demo.data === true}
              onSaved={(worker) => {
                setAdded(worker);
                closeTheForm();
              }}
              onCancel={() => {
                closeTheForm();
                // Asked again here too: a send whose answer was lost may have added the worker.
                void store.invalidateQueries({ queryKey: WORKERS });
              }}
            />
          </CardContent>
        </Card>
      ) : (
        <div>
          <Button
            ref={opener}
            onClick={() => {
              setAdded(null);
              setOpenOn(shopToday(me.shop.timezone, Date.now()));
            }}
          >
            {t("add")}
          </Button>
        </div>
      )}
    </>
  );
}

function WorkerList({
  me,
  list,
}: {
  me: WhoIsHere;
  list: ReturnType<typeof useWorkers>;
}) {
  const t = useTranslations("workers");
  // The roles' words, the sides' names among them, worked out once for the whole list, not once a row.
  const { roleOnSide } = useRoleWords(me);

  // A failed read shows above the list, not in its place: a refresh that fails (the session ended, the network
  // dropped) keeps the workers last read on the screen, with the reason above them, as on Vifaa. A first read
  // refused, as someone without staff.manage is, shows the reason alone.
  const failure = <ApiErrorAlert error={list.error} />;
  if (!list.data) return failure;
  // Two groups, each keeping the server's order. Suspended workers stay with those working: they come back.
  const here = list.data.filter((worker) => worker.status !== "left");
  const gone = list.data.filter((worker) => worker.status === "left");
  return (
    <>
      {failure}
      <Workers workers={here} roleOnSide={roleOnSide} />
      <section className="grid gap-3" aria-labelledby="workers-left">
        <h2 id="workers-left" className="text-lg font-semibold">
          {t("leftHeading")}
        </h2>
        {gone.length === 0 ? (
          <p>{t("noneLeft")}</p>
        ) : (
          <Workers workers={gone} roleOnSide={roleOnSide} />
        )}
      </section>
    </>
  );
}

/** How a role is written with its side, "Muuzaji (Dawa)" (useRoleWords). */
type RoleOnSide = (given: GivenRole) => string;

/** One group of workers, in one panel, a row each. */
function Workers({
  workers,
  roleOnSide,
}: {
  workers: Worker[];
  roleOnSide: RoleOnSide;
}) {
  return (
    <Card className="py-0">
      {/* A list, so a screen reader says how many workers there are. role="list" written out: Safari with
          VoiceOver stops calling a <ul> a list once its bullets are styled away, as Tailwind does. */}
      <ul role="list" className="divide-y divide-border">
        {workers.map((worker) => (
          // relative: the name's link stretches over its whole row (WorkerRow).
          <li key={worker.id} className="relative grid gap-1 px-4 py-3">
            <WorkerRow worker={worker} roleOnSide={roleOnSide} />
          </li>
        ))}
      </ul>
    </Card>
  );
}

function WorkerRow({
  worker,
  roleOnSide,
}: {
  worker: Worker;
  roleOnSide: RoleOnSide;
}) {
  const t = useTranslations("workers");
  const format = useFormatter();
  // "Muuzaji (Dawa) na Keshia (Vyakula)": the browser joins them the language's own way.
  const roles =
    worker.roles.length === 0
      ? t("noRole")
      : format.list(worker.roles.map(roleOnSide), { type: "conjunction" });

  return (
    <>
      <p>
        {/* The name opens the worker's own page (Jack's picture). Its tap area is the whole row, an empty box laid
            over it (after:absolute), so a finger on the roles or the status opens it too; a screen reader still
            hears one link, named by the names alone. */}
        <TextLink
          href={workerPage(worker.id)}
          className="after:absolute after:inset-0"
        >
          {t("names", {
            nickname: worker.display_name,
            fullName: worker.full_name,
          })}
        </TextLink>
      </p>
      <p>{roles}</p>
      {/* A key given apart from any role: counted only. Their names come with PPL-8, which gives them. */}
      {worker.keys.length > 0 ? (
        <p className="text-muted-foreground">
          {t("extraKeys", { count: worker.keys.length })}
        </p>
      ) : null}
      {/* In words, and a suspension in red too: the words alone say it, for anyone who can't tell the colours
          apart. */}
      <p className={STATUS_LOOK[worker.status]}>
        {t(`status.${worker.status}`)}
      </p>
      {/* Apart from the job's status (PPL-4's review): the superuser switched the person off in the admin, on
          every shop at once, and only he switches them on again. Working here or not, they can't log in. */}
      {worker.switched_off ? (
        <p className="font-semibold text-destructive">{t("switchedOff")}</p>
      ) : null}
    </>
  );
}

/** How each status looks: a suspension stands out, as the owner looks for it; a worker who left fades. */
const STATUS_LOOK: Record<Worker["status"], string> = {
  active: "",
  suspended: "font-semibold text-destructive",
  left: "text-muted-foreground",
};
