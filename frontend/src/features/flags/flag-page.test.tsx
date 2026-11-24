// flag-page.test.tsx — one flag's own page says what happened, who it names, where and when, opens its tap's day, and
// shows every note (CTRL-4).
import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { setLanguage } from "@/i18n/language";
import { whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { flag, flagNote, flagRoute, JUMA_JOB, REVIEWER } from "@/test/flags";
import { render } from "@/test/render";

import { FlagScreen } from "./flag-page";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";

type Flag = components["schemas"]["Flag"];
type WhoIsHere = components["schemas"]["WhoIsHere"];

/** Meneja, who may close flags and fix attendance too, as the Manager's role does. */
const MENEJA: WhoIsHere = {
  ...REVIEWER,
  permissions: {
    ...REVIEWER.permissions,
    whole_shop: ["flag.review", "attendance.manage"],
  },
};

/** The page of `one`, as `me` sees it. */
function show(one: Flag, me: WhoIsHere = MENEJA) {
  answer("GET", ME, { status: 200, body: me });
  answer("GET", flagRoute(one.id), { status: 200, body: one });
  return render(<FlagScreen id={one.id} />);
}

/** What a detail says, by its name: "Upande" → "Dawa". */
function detail(name: string): string | null {
  const label = screen.queryByText(name);
  return label?.nextElementSibling?.textContent ?? null;
}

describe("one flag's page", () => {
  it("says what happened, who it names, where, which laptop and when", async () => {
    show(flag());

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Alisimamishwa au aliondoka, lakini alibonyeza",
      }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Juma alibonyeza Ingia kazini akiwa amesimamishwa, au baada ya kuondoka kazini.",
      ),
    ).toBeTruthy();
    expect(detail("Anayetajwa")).toBe("Juma");
    expect(detail("Upande")).toBe("Dawa");
    expect(detail("Kompyuta")).toBe("Laptop Dawa");
    // By the laptop's clock, in the shop's zone; and when the server found it, when the laptop next had a network.
    expect(detail("Lini (kwa saa ya kompyuta)")).toBe(
      "Jumapili 22/11/2026, saa 07:52 asubuhi",
    );
    expect(detail("Mfumo uliona")).toBe(
      "Jumatatu 23/11/2026, saa 09:10 asubuhi",
    );
    expect(detail("Hali")).toBe("Inasubiri");
    // Nothing a rescue file would say.
    expect(detail("Iliandikwa kwenye")).toBeNull();
    expect(detail("Faili lilipakiwa na")).toBeNull();
  });

  it("opens the tap's day for whoever may fix attendance, and offers it to nobody else", async () => {
    const { unmount } = show(flag());
    const link = await screen.findByRole("link", { name: "Fungua siku yake" });
    expect(link.getAttribute("href")).toMatch(
      new RegExp(
        `^/attendance-month/worker/?\\?staff=${JUMA_JOB}&month=2026-11&day=2026-11-22$`,
      ),
    );
    unmount();

    // flag.review without attendance.manage: the month's routes would refuse them.
    show(flag(), REVIEWER);
    await screen.findByText("Hali");
    expect(screen.queryByRole("link", { name: "Fungua siku yake" })).toBeNull();
  });

  it("offers no day for a flag about no tap", async () => {
    show(flag({ kind: "device_gap", tap: null, people: [] }));

    await screen.findByText("Hali");
    expect(screen.queryByRole("link", { name: "Fungua siku yake" })).toBeNull();
  });

  it.each<[string, Partial<Flag>, string]>([
    [
      "a tap with no time to trust",
      { kind: "unverified_time", people: ["Neema", "Asha"] },
      "Neema alibonyeza Ingia kazini kwenye kompyuta ambayo saa yake haikuaminika, kwa hiyo saa halisi haijulikani.",
    ],
    [
      "a Toka while suspended",
      { tap: { staff: JUMA_JOB, kind: "out", day: "2026-11-22" } },
      "Juma alibonyeza Toka kazini akiwa amesimamishwa, au baada ya kuondoka kazini.",
    ],
    [
      "another record while suspended",
      { tap: null },
      "Juma aliandika kumbukumbu akiwa amesimamishwa, au baada ya kuondoka kazini.",
    ],
    [
      "a file loaded while suspended",
      {
        loaded_by: "Juma",
        brought_from: "Laptop Vyakula",
        about_loading: true,
      },
      "Juma alipakia faili la kumbukumbu akiwa amesimamishwa, au baada ya kuondoka kazini.",
    ],
    [
      // Two people of one nickname, or one who loaded their own: the server tells them apart, never the names.
      "a tap in a file loaded by someone of the same nickname",
      { loaded_by: "Juma", brought_from: "Laptop Vyakula" },
      "Juma alibonyeza Ingia kazini akiwa amesimamishwa, au baada ya kuondoka kazini.",
    ],
    [
      "a record by someone with no key",
      { kind: "permission_break", tap: null },
      "Juma aliandika kumbukumbu ambayo hana ruhusa ya kuiandika.",
    ],
    [
      "a file loaded by someone with no key",
      { kind: "permission_break", loaded_by: "Juma", about_loading: true },
      "Juma alipakia faili la kumbukumbu bila ruhusa.",
    ],
    [
      "missing records",
      {
        kind: "device_gap",
        people: [],
        tap: null,
        expected: "42.000",
        actual: "45.000",
        difference: "3.000",
      },
      "Kompyuta hii ilituma kumbukumbu namba 45, lakini seva ilisubiri namba 42. Zinazokosekana: 3.",
    ],
    [
      "numbers gone back",
      {
        kind: "device_gap",
        people: [],
        tap: null,
        expected: "43.000",
        actual: "1.000",
        difference: "-42.000",
      },
      "Namba za kumbukumbu za kompyuta hii zimerudi nyuma: seva ilisubiri namba 43, ikaja namba 1.",
    ],
    [
      "a refused record",
      { kind: "invalid_document", tap: null, refused_for: "id.taken" },
      "Seva haikuweza kuhifadhi kumbukumbu iliyotumwa na kompyuta hii.",
    ],
    [
      "a kind newer than the app",
      { kind: "negative_stock", tap: null },
      "Mfumo umeona tofauti ambayo toleo hili la programu halijui kuieleza.",
    ],
  ])("says %s in a sentence", async (_, fields, sentence) => {
    show(flag(fields));

    expect(await screen.findByText(sentence)).toBeTruthy();
  });

  it.each([
    ["document.type_unknown", "Seva haipokei aina hii ya kumbukumbu."],
    // Its shape was wrong, the push's own code for it: no box to look at, as a form's words would say.
    ["invalid", "Baadhi ya taarifa za kumbukumbu hii si sahihi."],
    // Nothing to try again: the record is refused for good.
    [
      "id.taken",
      "Seva ina kumbukumbu nyingine yenye namba hii ya utambulisho.",
    ],
    // A code newer than the app: named, so the manager can still look it up.
    ["sale.some_new_rule", "Seva imeikataa. Msimbo: sale.some_new_rule"],
  ])(
    "says why the server refused a record for %s, in a record's words, never a form's",
    async (code, words) => {
      show(flag({ kind: "invalid_document", tap: null, refused_for: code }));

      expect(await screen.findByText(`Kwa nini: ${words}`)).toBeTruthy();
    },
  );

  it("says where a rescued record was made, and who loaded its file", async () => {
    show(flag({ brought_from: "Laptop Vyakula", loaded_by: "Asha" }));

    await screen.findByText("Hali");
    expect(detail("Kompyuta")).toBe("Laptop Dawa");
    expect(detail("Iliandikwa kwenye")).toBe("Laptop Vyakula");
    expect(detail("Faili lilipakiwa na")).toBe("Asha");
    // Loaded by Asha, and about Juma's own record: the sentence is his.
    expect(screen.getByText(/^Juma alibonyeza Ingia kazini/)).toBeTruthy();
  });

  it("names everyone it names, and leaves out what it doesn't know", async () => {
    const { unmount } = show(
      flag({ people: ["Neema", "Asha"], side: null, kind: "unverified_time" }),
    );
    await screen.findByText("Hali");
    expect(detail("Wanaotajwa")).toBe("Neema na Asha");
    expect(detail("Upande")).toBe("Duka zima");
    unmount();

    show(
      flag({
        kind: "device_gap",
        people: [],
        tap: null,
        device: null,
        made_at: null,
        expected: "42.000",
        actual: "43.000",
        difference: "1.000",
      }),
    );
    await screen.findByText("Hali");
    for (const unknown of [
      "Anayetajwa",
      "Wanaotajwa",
      "Kompyuta",
      "Lini (kwa saa ya kompyuta)",
    ])
      expect(detail(unknown)).toBeNull();
  });

  it("says a moment on the shop's own calendar", async () => {
    // 00:30 on Monday in Arusha, Sunday still in UTC: the weekday, the date and the time are all the shop's.
    show(flag({ made_at: "2026-11-22T21:30:00Z" }));

    await screen.findByText("Hali");
    expect(detail("Lini (kwa saa ya kompyuta)")).toBe(
      "Jumatatu 23/11/2026, saa 00:30 usiku",
    );
  });

  it("speaks English to someone who chose it", async () => {
    setLanguage("en");
    show(flag());

    expect(
      await screen.findByText(
        "Juma tapped Clock in while suspended, or after leaving the job.",
      ),
    ).toBeTruthy();
    expect(detail("When (by the laptop's clock)")).toBe(
      "Sunday 22/11/2026, 07:52",
    );
  });
});

describe("its notes", () => {
  it("shows each one's words, what it did, who wrote it and when, oldest first", async () => {
    show(
      flag({
        status: "resolved",
        notes: [
          flagNote(),
          flagNote({
            step: "resolved",
            text: "Nimezungumza naye.",
            by: "Baba",
            at: "2026-11-24T14:30:00Z",
          }),
        ],
      }),
    );

    const notes = await screen.findByRole("region", { name: "Maelezo (2)" });
    const [first, second] = within(notes).getAllByRole("listitem");
    expect(
      within(first!).getByText("Alikuja kuchukua vitu vyake tu."),
    ).toBeTruthy();
    expect(
      within(first!).getByText(
        "Imeelezwa · Neema · Jumatatu 23/11/2026, saa 09:10 asubuhi",
      ),
    ).toBeTruthy();
    expect(within(second!).getByText("Nimezungumza naye.")).toBeTruthy();
    expect(
      within(second!).getByText(
        "Imetatuliwa · Baba · Jumanne 24/11/2026, saa 17:30 jioni",
      ),
    ).toBeTruthy();
  });

  it("says the system's own note in the reader's language, by the system", async () => {
    show(
      flag({
        kind: "device_gap",
        people: [],
        tap: null,
        status: "resolved",
        notes: [
          flagNote({
            step: "resolved",
            text: "flag.device_gap_filled",
            by: null,
          }),
        ],
      }),
    );

    expect(
      await screen.findByText("Kumbukumbu zote zilizokosekana zimefika."),
    ).toBeTruthy();
    expect(screen.getByText(/^Imetatuliwa · Mfumo · /)).toBeTruthy();
  });

  it("never reads a person's words as a code of the system's", async () => {
    show(flag({ notes: [flagNote({ text: "flag.device_gap_filled" })] }));

    expect(await screen.findByText("flag.device_gap_filled")).toBeTruthy();
  });

  it("says so when nothing was written", async () => {
    show(flag());

    expect(await screen.findByText("Bado hakuna maelezo.")).toBeTruthy();
    expect(screen.getByRole("region", { name: "Maelezo (0)" })).toBeTruthy();
  });
});

describe("with no flag to show", () => {
  it("says so for an address that names none, and asks for none", async () => {
    answer("GET", ME, { status: 200, body: REVIEWER });

    render(<FlagScreen id={null} />);

    expect(
      await screen.findByText("Hakuna tofauti iliyochaguliwa."),
    ).toBeTruthy();
    // Once the page knows who is here, it waits for nothing.
    await waitFor(() =>
      expect(screen.queryByText("Subiri kidogo…")).toBeNull(),
    );
    expect(sent.every((request) => request.url.endsWith(ME))).toBe(true);
  });

  it("shows the server's refusal for one the person may not close", async () => {
    answer("GET", ME, { status: 200, body: whoIsHere([]) });
    answer("GET", flagRoute("gone"), refusal(404, "not_found"));

    render(<FlagScreen id="gone" />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("Subiri kidogo…")).toBeNull();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Tofauti",
    );
  });
});
