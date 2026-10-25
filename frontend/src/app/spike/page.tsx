// spike/page.tsx — a throwaway page for SPIKE-1: does the app keep its data on the shop's devices?
//
// It saves rows in the browser's database (IndexedDB, through Dexie), asks for persistent storage, and
// shows what the device answers, with the facts the spike report needs: the browser's version, the
// device model, online or not. PR 2 removes it (04 SPIKE-1); the real database comes with SYNC-6.
"use client";

import Dexie, { type EntityTable } from "dexie";
import { useCallback, useEffect, useState } from "react";

import { APP_VERSION } from "@/lib/version";

import sw from "../../../messages/sw.json";

/** One saved row: an id, and the time it was saved. */
interface SpikeRow {
  id: string;
  savedAt: string;
}

// A database of its own, "mpc-spike", so these rows never meet the real database (SYNC-6).
// Version 1, with one table, `rows`, where each row is found by its id.
const db = new Dexie("mpc-spike") as Dexie & {
  rows: EntityTable<SpikeRow, "id">;
};
db.version(1).stores({ rows: "id" });

/** Chrome's extra facts about the device. Only Chrome and Edge have them, and TypeScript doesn't know
 * them yet, so this describes the little we use. */
interface UserAgentData {
  getHighEntropyValues(hints: string[]): Promise<{
    model?: string;
    platform?: string;
    platformVersion?: string;
    fullVersionList?: { brand: string; version: string }[];
  }>;
}

/** The browser and the device for the spike report, e.g. "Google Chrome 141.0.7390.122 · Android 14 ·
 * SM-A155F". Chrome hides the model and its full version from the plain user-agent text, so we ask for
 * them; a browser that can't answer gives that plain text instead. */
async function describeDevice(): Promise<string> {
  const uaData = (navigator as Navigator & { userAgentData?: UserAgentData })
    .userAgentData;
  if (!uaData) return navigator.userAgent;
  const {
    model,
    platform,
    platformVersion,
    fullVersionList = [],
  } = await uaData.getHighEntropyValues([
    "model",
    "platformVersion",
    "fullVersionList",
  ]);
  // The list also holds made-up brands ("Not A;Brand") and the engine (Chromium); keep the real one.
  const browser =
    fullVersionList.find(
      (b) => b.brand === "Google Chrome" || b.brand === "Microsoft Edge",
    ) ?? fullVersionList.find((b) => b.brand === "Chromium");
  return [
    browser && `${browser.brand} ${browser.version}`,
    platform && `${platform} ${platformVersion ?? ""}`,
    model,
  ]
    .filter(Boolean)
    .join(" · ");
}

/** Everything the page shows, read from the browser in one go. */
interface SpikeState {
  device: string;
  online: boolean;
  controlled: boolean;
  persisted: boolean;
  storage: string;
  rows: SpikeRow[];
}

/** Bytes as megabytes, with one decimal. */
const megabytes = (bytes: number) => (bytes / 1024 / 1024).toFixed(1);

async function readState(): Promise<SpikeState> {
  const { usage = 0, quota = 0 } = await navigator.storage.estimate();
  const rows = await db.rows.toArray();
  return {
    device: await describeDevice(),
    online: navigator.onLine,
    // A page opened before the worker took charge isn't looked after yet: it wouldn't open offline.
    controlled:
      "serviceWorker" in navigator &&
      navigator.serviceWorker.controller !== null,
    persisted: await navigator.storage.persisted(),
    storage: `${megabytes(usage)} / ${megabytes(quota)} MB`,
    // Oldest first: times in ISO form sort as text in time order.
    rows: rows.sort((a, b) => a.savedAt.localeCompare(b.savedAt)),
  };
}

export default function SpikePage() {
  // null until the browser has answered for the first time.
  const [state, setState] = useState<SpikeState | null>(null);
  // The browser's own words when it refuses something, shown on screen: a phone has no console to
  // read them in, and the spike report needs the reason (04 SPIKE-1, box 3).
  const [error, setError] = useState<string | null>(null);

  // Runs one step of the page. If the browser refuses, its words are kept instead of lost.
  // useCallback keeps each function the same on every redraw, so the effect below doesn't start over
  // each time the page redraws.
  const attempt = useCallback(async (step: () => Promise<void>) => {
    try {
      await step();
      setError(null);
    } catch (problem) {
      setError(String(problem));
    }
  }, []);

  // Reads every fact again, through attempt.
  const refresh = useCallback(
    () => attempt(async () => setState(await readState())),
    [attempt],
  );

  useEffect(() => {
    // Read once when the page opens, and again whenever the device goes online or offline.
    const onChange = () => void refresh();
    onChange();
    window.addEventListener("online", onChange);
    window.addEventListener("offline", onChange);
    // When the page closes, stop listening.
    return () => {
      window.removeEventListener("online", onChange);
      window.removeEventListener("offline", onChange);
    };
  }, [refresh]);

  // The buttons run through attempt themselves, so these read the facts directly, not through
  // refresh: a second attempt inside the first would clear the error the first one needs to show.

  /** Hifadhi mstari: one more row, with the time now. */
  async function saveRow() {
    await db.rows.add({
      id: crypto.randomUUID(),
      savedAt: new Date().toISOString(),
    });
    setState(await readState());
  }

  /** Omba hifadhi ya kudumu: Chrome answers by itself, with no popup (lesson 3); the page then shows it. */
  async function askPersist() {
    await navigator.storage.persist();
    setState(await readState());
  }

  const yesNo = (value: boolean) => (value ? sw.spike.yes : sw.spike.no);

  return (
    <main className="mx-auto flex max-w-xl flex-col gap-6 p-4">
      <h1 className="text-2xl font-semibold">{sw.spike.title}</h1>

      {/* What the browser refused, in its own words. Those words come from the browser, in English. */}
      {error && (
        <p role="alert" className="break-words text-sm text-destructive">
          {`${sw.spike.error}: ${error}`}
        </p>
      )}

      {/* The facts, as label and value. Until the browser answers, only the version shows. */}
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt>{sw.spike.version}</dt>
        <dd>{APP_VERSION}</dd>
        {state && (
          <>
            <dt>{sw.spike.device}</dt>
            <dd className="break-words">{state.device}</dd>
            <dt>{sw.spike.online}</dt>
            <dd>{yesNo(state.online)}</dd>
            <dt>{sw.spike.worker}</dt>
            <dd>{yesNo(state.controlled)}</dd>
            <dt>{sw.spike.persisted}</dt>
            <dd>{yesNo(state.persisted)}</dd>
            <dt>{sw.spike.storage}</dt>
            <dd>{state.storage}</dd>
          </>
        )}
      </dl>

      {/* Big tap targets for phones (03 §7.3). */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void attempt(saveRow)}
          className="min-h-12 rounded-md bg-primary px-5 font-semibold text-primary-foreground"
        >
          {sw.spike.save}
        </button>
        <button
          type="button"
          onClick={() => void attempt(askPersist)}
          className="min-h-12 rounded-md border px-5 font-semibold"
        >
          {sw.spike.persist}
        </button>
      </div>

      <section className="flex flex-col gap-2">
        <h2 className="font-semibold">{`${sw.spike.rows} (${state?.rows.length ?? 0})`}</h2>
        {/* Each row's time in the device's own clock, written the Swahili way. */}
        <ol className="list-decimal pl-6 text-sm">
          {state?.rows.map((row) => (
            <li key={row.id}>
              {new Date(row.savedAt).toLocaleString("sw-TZ")}
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
