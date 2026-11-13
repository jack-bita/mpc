// rescue.tsx — the Kompyuta hii screen's part for a dying laptop (SYNC-12, 03 §6.7): how many records wait
// here, a button that saves them to a file, and, for a manager, a button that loads such a file from another
// laptop of the shop. The file's shape and both sides of it live in offline/rescue.ts; this owns the buttons
// and what they say.
//
// Who may do which (Jack's plan): anyone logged in saves the file, as a dying laptop can't wait for the
// manager to arrive; only someone with device.manage on this laptop's side loads one, as a file edited by
// hand could clock in a colleague who never came.
//
// "use client": it asks use-intl for words, and reads the laptop's database and files, in the browser only.
"use client";

import { useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { Alert, AlertDescription } from "@/components/design/alert";
import { Button } from "@/components/design/button";
import { useThisDevice } from "@/features/devices/this-device";
import { usePersonAtCounter } from "@/features/login/at-the-counter";
import { holdsOnSide } from "@/features/people/side-of-row";
import { NeverFilled, useWaitingCount } from "@/offline/outbox";
import {
  exportWaiting,
  type ImportResult,
  importWaiting,
  type RescueProblem,
  RescueRefused,
} from "@/offline/rescue";
import { shopToday } from "@/offline/rules";
import { useShopDatabase } from "@/offline/this-shop";

/** How long the download's link is kept after its click, in ms: long enough for any browser to start. */
const LET_GO_AFTER = 60 * 1000;

/** The key that lets a person load a file: the manager's, who pairs and blocks laptops too. */
const LOADS_FILES = "device.manage";

// Each problem's words in the book: a refusal of the file, or a laptop not filled yet, or anything else.
type ProblemWords =
  "notRescueFile" | "wrongShop" | "brokenRecord" | "firstSync" | "failed";
const PROBLEM_WORDS: Record<RescueProblem, ProblemWords> = {
  not_rescue_file: "notRescueFile",
  wrong_shop: "wrongShop",
  broken_record: "brokenRecord",
};

export function Rescue() {
  const t = useTranslations("thisLaptop.rescue");
  const db = useShopDatabase();
  const device = useThisDevice();
  const person = usePersonAtCounter();
  const waiting = useWaitingCount();
  const chooser = useRef<HTMLInputElement>(null);
  const [loaded, setLoaded] = useState<ImportResult | null>(null);
  const [problem, setProblem] = useState<ProblemWords | null>(null);

  // Nothing before the laptop and its database are known: the frame shows this page only to someone at a
  // registered laptop, so it is a moment at most.
  if (db === null || device === null || waiting === undefined) return null;
  const mayLoad =
    person != null && holdsOnSide(person.row, LOADS_FILES, device.homeSide.id);

  async function save() {
    if (db === null || device === null) return;
    setProblem(null);
    setLoaded(null);
    try {
      const file = await exportWaiting(db, device.shop.id, device.id);
      // The browser's own download: a link to the file, clicked. The name says which laptop and which day, the
      // shop's day, not the laptop's zone's: a file saved at 01:00 in Arusha is that day's, not yesterday's.
      const day = shopToday(device.shop.timezone, Date.parse(file.made_at));
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(file, null, 2)], { type: "application/json" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `mpc-unsent-laptop-${device.code}-${day}.json`;
      link.click();
      // Let go a minute later, not at once: Firefox and Safari read the link after the click returns, and
      // one let go too soon cancels the download.
      setTimeout(() => URL.revokeObjectURL(url), LET_GO_AFTER);
    } catch (error) {
      // A database that refused to read: nothing was saved, and she must know, as a load's failure says.
      console.error("the unsent records were not saved to a file", error);
      setProblem("failed");
    }
  }

  async function load(file: File) {
    if (db === null || device === null || person == null) return;
    setProblem(null);
    setLoaded(null);
    try {
      // Loaded by whoever is at the counter: the push names them to the server, which checks their key.
      setLoaded(
        await importWaiting(
          db,
          device.shop.id,
          device.id,
          await file.text(),
          person.row.id,
        ),
      );
    } catch (error) {
      if (error instanceof RescueRefused)
        setProblem(PROBLEM_WORDS[error.problem]);
      else if (error instanceof NeverFilled) setProblem("firstSync");
      else {
        // A database that refused, or a full disk: nothing was added (one transaction), and she must know.
        console.error("a rescue file was not loaded", error);
        setProblem("failed");
      }
    }
  }

  return (
    <section className="grid gap-3">
      <h2 className="text-xl font-semibold">{t("title")}</h2>
      <p>{waiting === 0 ? t("none") : t("waiting", { count: waiting })}</p>
      <p>{t("why")}</p>
      {/* role="status": a screen reader says what the load did. */}
      <p role="status" className={loaded ? undefined : "sr-only"}>
        {loaded &&
          [
            t("added", { count: loaded.added }),
            loaded.alreadyHere > 0
              ? t("alreadyHere", { count: loaded.alreadyHere })
              : null,
          ]
            .filter(Boolean)
            .join(" ")}
      </p>
      {problem && (
        <Alert kind="danger">
          <AlertDescription>{t(problem)}</AlertDescription>
        </Alert>
      )}
      <div className="flex flex-wrap gap-3">
        {/* Only with something to save: an empty file would only confuse the one loading it. */}
        {waiting > 0 && (
          <Button size="normal" onClick={() => void save()}>
            {t("save")}
          </Button>
        )}
        {mayLoad && (
          <>
            <Button
              kind="second"
              size="normal"
              onClick={() => chooser.current?.click()}
            >
              {t("load")}
            </Button>
            {/* The browser's own file chooser, hidden: the button above opens it. Emptied after each
                choice, so the same file chosen again still counts as a choice. */}
            <input
              ref={chooser}
              type="file"
              accept="application/json,.json"
              aria-label={t("load")}
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) void load(file);
              }}
            />
          </>
        )}
      </div>
    </section>
  );
}
