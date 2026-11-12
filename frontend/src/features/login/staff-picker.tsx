// staff-picker.tsx — the PIN screen's first step on a shared laptop: "Wewe ni nani?", with a tile for each
// person who works at the shop, and a tap on your own (UI-4, 03 §5.9). The PIN pad comes next.
//
// The people come from the laptop's own copy of the staff list (SYNC-2), which the sync keeps up to date
// every 30 seconds (SYNC-9): never from the server, so the tiles show the same with no network, the way
// in to an offline PIN login (SYNC-10). A person added in the office gets a tile at the next sync. Only
// those who can log in today: someone who left or was switched off isn't on the laptop at all, and a
// suspended person's row says so, so neither gets a tile, as the server's old route sent neither.
//
// A tile shows the full name in large letters with the nickname under it, until photos come (PPL-4; 02 §5).
//
// "use client": it reads the laptop's database and its words, both in the browser only.
"use client";

import { useLiveQuery } from "dexie-react-hooks";
import { useEffect, useRef } from "react";
import { useTranslations } from "use-intl";

import type { components } from "@/api/schema";
import { Button } from "@/components/design/button";
import { readCursor } from "@/offline/sync/meta";
import { useShopDatabase } from "@/offline/this-shop";

/** One person, as the laptop keeps them: their staff row (SYNC-2). */
export type StaffRow = components["schemas"]["StaffRecord"];

/**
 * Who gets a tile: the active people, A to Z. Undefined while the first read runs, so nothing flashes;
 * null while this laptop has had no first sync, whose copy the tiles wait for. Live: a sync that adds,
 * renames or suspends someone redraws the tiles by itself.
 */
function useTiles(): StaffRow[] | null | undefined {
  const db = useShopDatabase();
  return useLiveQuery(async () => {
    if (db === null) return null;
    // One read, so the cursor and the rows are seen as they stood together.
    return db.transaction("r", [db.meta, db.staff], async () => {
      // No cursor: no copy yet. An empty list then would say the shop has nobody, which isn't so.
      if ((await readCursor(db)) === null) return null;
      const people = await db.staff.toArray();
      return people.filter((person) => person.status === "active").sort(byName);
    });
  }, [db]);
}

// A to Z by full name, then nickname, then id: the order the server sends the rows in (staff_rows,
// apps/sync/selectors.py), so two people of one name keep one order on every laptop.
function byName(a: StaffRow, b: StaffRow): number {
  return (
    a.full_name.localeCompare(b.full_name) ||
    a.display_name.localeCompare(b.display_name) ||
    (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
  );
}

export function StaffPicker({
  onPick,
}: {
  /** Called with the person whose tile was tapped. */
  onPick: (person: StaffRow) => void;
}) {
  const t = useTranslations("login.picker");
  const people = useTiles();
  // The tiles' step has come, and whatever had focus (a tapped tile, Rudi, Toka) left with the last one:
  // focus moves to the question, so a screen reader says it, and Tab goes on from here (as UI-3's forms
  // do).
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);

  return (
    <div className="grid gap-6">
      {/* The heading of this step of the login screen: the PIN pad's step has the person's name. */}
      {/* tabIndex -1: code may focus it, and Tab passes it by. No ring: it isn't anything to press. */}
      <h1
        ref={heading}
        tabIndex={-1}
        className="text-3xl font-semibold outline-none"
      >
        {t("title")}
      </h1>
      {/* A laptop just registered, before its first sync: what it waits for, not an empty shop. */}
      {people === null && <p>{t("firstSync")}</p>}
      {/* A new shop, before the owner adds its people: the reason, not an empty screen. */}
      {people?.length === 0 && <p>{t("empty")}</p>}
      {people && people.length > 0 && (
        // A list, so a screen reader says how many people there are. role="list" written out: Safari with
        // VoiceOver stops calling a <ul> a list once Tailwind styles its bullets away.
        <ul role="list" className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {people.map((person) => (
            <li key={person.id}>
              {/* The shop's button, so a tile has its colours, focus ring and press look, all checked in
                  button.test.tsx. Two lines don't fit its 52 px, so it grows (h-auto), and never shrinks
                  below a finger's size (min-h, from the same token). */}
              <Button
                kind="second"
                className="h-auto min-h-(--control-big) w-full flex-col gap-1 py-4 whitespace-normal"
                onClick={() => onPick(person)}
              >
                <span className="text-2xl">{person.full_name}</span>
                {/* A space between the two names, so a screen reader says "Asha Mfano Asha", not
                    "Asha MfanoAsha". Invisible: the tile sets its lines one under the other. */}{" "}
                <span className="text-lg font-normal">
                  {person.display_name}
                </span>
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
