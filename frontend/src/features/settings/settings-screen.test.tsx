// settings-screen.test.tsx — Mipangilio ya duka (SHOP-5): every rule of the registry on one page, under its area, then
// the closed days (ATT-9) and the sides; a side's rule with a line per side; each value written its own way; a value
// set to start later shown beside today's; the page in English; and why, when the server refuses. Then each line's
// button: Badilisha where the person holds settings.manage, Historia everywhere else, and what each opens.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { setLanguage } from "@/i18n/language";
import { closuresAnswer } from "@/test/closures";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal } from "@/test/fake-server";
import { render } from "@/test/render";
import { line, OWNER, row, SHOP_RULES, withRule } from "@/test/settings";

import { SettingsScreen } from "./settings-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const RULES = "/api/v1/shops/settings/";
const SIDES = "/api/v1/shops/sides/";
const CLOSURES = "/api/v1/shops/closures/";

// A seller on each side: reading the rules needs no key.
const SELLER = whoIsHere([
  { side: DAWA, permissions: ["sale.create"] },
  { side: VYAKULA, permissions: ["sale.create"] },
]);

function rulesAnswer(rules = SHOP_RULES, me: typeof SELLER = SELLER) {
  answer("GET", ME, { status: 200, body: me });
  answer("GET", RULES, { status: 200, body: rules });
  // Siku duka limefungwa, under the rules, reads the closures: none here, as closures-section.test.tsx tests them.
  answer("GET", CLOSURES, { status: 200, body: closuresAnswer() });
  // Pande, at the bottom of the page, reads the sides: none here, as side-switch.test.tsx tests them.
  answer("GET", SIDES, {
    status: 200,
    body: { next: null, previous: null, results: [] },
  });
}

/** One rule's card, found by its name. Given 5 s, not Testing Library's 1, as the first test of a file pays
 * for the page's first load (device-health.test.tsx). */
async function cardOf(name: string): Promise<HTMLElement> {
  const heading = await screen.findByRole(
    "heading",
    { name, level: 3 },
    { timeout: 5_000 },
  );
  const card = heading.closest("[data-slot=card]");
  if (!(card instanceof HTMLElement)) throw new Error(`No card for ${name}`);
  return card;
}

// "TSh 1,000" is written with a space that never breaks (format.ts). textContent keeps it, so cardText's checks
// have that space; getByText first turns every space into a plain one, so its words have a plain space.

/** What a card says, its lines' words run together as a screen shows them. */
async function cardText(name: string): Promise<string> {
  return (await cardOf(name)).textContent ?? "";
}

describe("Mipangilio ya duka", () => {
  it("shows every rule of the registry once, under its area, then the closed days, and the sides at the bottom", async () => {
    rulesAnswer();

    render(<SettingsScreen />);

    await cardOf("Faini ya kwanza ya kuchelewa");
    expect(
      screen
        .getAllByRole("heading", { level: 2 })
        .map((each) => each.textContent),
      // The closed days under the rules and above the sides, as Jack pictured it (ATT-9); the sides and their
      // switches last (side-switch.tsx).
    ).toEqual([
      "Mahudhurio",
      "Pesa",
      "Kompyuta",
      "Mzigo",
      "Siku duka limefungwa",
      "Pande",
    ]);
    expect(
      screen
        .getAllByRole("heading", { level: 3 })
        .map((each) => each.textContent),
    ).toEqual([
      // The attendance day in its order, its switch first (ATT-2).
      "Mahudhurio yamewashwa",
      "Mwisho wa kufika kwa wakati",
      "Faini ya kwanza ya kuchelewa",
      "Faini ya pili kuanzia",
      "Faini ya pili ya kuchelewa",
      "Dharura kuanzia",
      "Nusu siku ya mchana: kufika kuanzia",
      "Saa ya mchana",
      "Nusu siku ya asubuhi: kuondoka hadi",
      "Saa ya kufunga",
      "Kuzungusha hesabu hadi",
      "Tofauti ya droo inayokubalika",
      "Funga baada ya kukaa bila kazi",
      "Tofauti ya kuhesabu mzigo inayokubalika",
      "Onya kabla bidhaa haijaisha muda",
      "Zuia kuuza zaidi ya mzigo uliopo",
    ]);
  });

  it("gives a side's rule a line for each side, and a shop's rule one line with no side", async () => {
    rulesAnswer();

    render(<SettingsScreen />);

    // Dawa's tolerance and Vyakula's are two values, each set on its own (SHOP-3).
    const drawer = await cardOf("Tofauti ya droo inayokubalika");
    expect(within(drawer).getByText("Dawa")).toBeTruthy();
    expect(within(drawer).getByText("Vyakula")).toBeTruthy();
    const fine = await cardOf("Faini ya kwanza ya kuchelewa");
    expect(within(fine).queryByText("Dawa")).toBeNull();
    expect(within(fine).queryByText("Vyakula")).toBeNull();
  });

  it("writes each kind of value its own way", async () => {
    rulesAnswer();

    render(<SettingsScreen />);

    // A time with its part of the day, as on the clock-in, so nobody reads it as Swahili time (SYNC-11).
    expect(await cardText("Mwisho wa kufika kwa wakati")).toContain(
      "07:35 asubuhi",
    );
    // No fine until the owner types one (ATT-2).
    expect(await cardText("Faini ya kwanza ya kuchelewa")).toContain("TSh 0");
    expect(await cardText("Kuzungusha hesabu hadi")).toContain("TSh 1");
    expect(await cardText("Funga baada ya kukaa bila kazi")).toContain(
      "Dakika 15",
    );
    expect(await cardText("Tofauti ya kuhesabu mzigo inayokubalika")).toContain(
      "0%",
    );
    expect(await cardText("Onya kabla bidhaa haijaisha muda")).toContain(
      "Siku 90",
    );
    expect(await cardText("Zuia kuuza zaidi ya mzigo uliopo")).toContain(
      "Hapana",
    );
  });

  it("gives each rule its line of help", async () => {
    rulesAnswer();

    render(<SettingsScreen />);

    expect(await cardText("Faini ya kwanza ya kuchelewa")).toContain(
      "Inakatwa kwenye mshahara kwa kila siku aliyochelewa, kabla ya saa ya faini ya pili.",
    );
  });

  it("shows the late fine today, and the 2,000 set to start tomorrow (the card's first Done when)", async () => {
    // The owner set 2,000 from tomorrow, 16 Nov: today is still 1,000, the default.
    rulesAnswer(
      withRule(
        line({
          value: "1000.00",
          rows: [row({ value: "2000.00", effective_from: "2026-11-16" })],
        }),
      ),
    );

    render(<SettingsScreen />);

    const fine = await cardOf("Faini ya kwanza ya kuchelewa");
    expect(within(fine).getByText("TSh 1,000")).toBeTruthy();
    expect(
      within(fine).getByText("Kuanzia 16/11/2026: TSh 2,000"),
    ).toBeTruthy();
  });

  it("shows a value to come on its own side's line only", async () => {
    // Vyakula's drawer may be 500 off from 1 December; Dawa's stays as it is.
    const changed = withRule(
      line({
        key: "cash.tolerance",
        kind: "money",
        scope: "side",
        side: VYAKULA.id,
        default: "0.00",
        value: "0.00",
        rows: [
          row({
            key: "cash.tolerance",
            side: VYAKULA.id,
            value: "500.00",
            effective_from: "2026-12-01",
          }),
        ],
      }),
    );
    rulesAnswer(changed);

    render(<SettingsScreen />);

    const drawer = await cardOf("Tofauti ya droo inayokubalika");
    const coming = within(drawer).getByText("Kuanzia 01/12/2026: TSh 500");
    // On the line that names Vyakula, the second of the two.
    expect(coming.parentElement?.textContent).toContain("Vyakula");
    expect(coming.parentElement?.textContent).not.toContain("Dawa");
  });

  it("speaks English for someone who reads English", async () => {
    setLanguage("en");
    rulesAnswer();

    render(<SettingsScreen />);

    expect(await cardText("First late fine")).toContain("TSh 0");
    // English writes the time alone, as the clock-in does.
    expect(await cardText("On time until")).toContain("07:35");
    expect(await cardText("Lock after no use")).toContain("Minutes: 15");
    // The noun first, as the Swahili's "Dakika 15": one minute never reads "1 minutes" (SHOP-5's review).
    expect(await cardText("Warn before expiry")).toContain("Days: 90");
    expect(await cardText("Block selling more than is in stock")).toContain(
      "No",
    );
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Shop settings",
    );
  });

  it("says to wait while it asks, so the page is never only its title", () => {
    answer("GET", ME, { status: 200, body: SELLER });
    answer("GET", RULES, () => new Promise<Response>(() => undefined));

    render(<SettingsScreen />);

    const line = screen.getByText("Subiri kidogo…");
    expect(line.getAttribute("role")).toBe("status");
  });

  it("says why when the server refuses, as for someone no longer logged in", async () => {
    answer("GET", ME, refusal(403, "not_authenticated"));
    answer("GET", RULES, refusal(403, "not_authenticated"));

    render(<SettingsScreen />);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Ingia kwanza",
    );
    expect(screen.queryByRole("heading", { level: 2 })).toBeNull();
  });

  it("leaves out a rule the app has no words for yet, and shows the rest", async () => {
    // A newer server, with a rule a later card adds, meets this older app (03 §6.5).
    rulesAnswer({
      ...SHOP_RULES,
      rules: [
        ...SHOP_RULES.rules,
        line({
          key: "attendance.half_day_after" as never,
          kind: "time",
          value: "11:00",
        }),
      ],
    });

    render(<SettingsScreen />);

    await cardOf("Faini ya kwanza ya kuchelewa");
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(16);
    expect(screen.queryByText(/half_day_after/)).toBeNull();
  });
});

describe("each line's button", () => {
  it("is Badilisha on every line for the owner, who holds the key on the whole shop", async () => {
    rulesAnswer(SHOP_RULES, OWNER);

    render(<SettingsScreen />);

    await cardOf("Faini ya kwanza ya kuchelewa");
    // Twelve shop's rules, and four side's rules on two sides: twenty lines.
    expect(screen.getAllByRole("button", { name: /^Badilisha/ })).toHaveLength(
      20,
    );
    expect(screen.queryByRole("button", { name: /^Historia/ })).toBeNull();
    // Each says which rule and which side, as a screen reader reads a list of buttons.
    expect(
      screen.getByRole("button", {
        name: "Badilisha: Tofauti ya droo inayokubalika, Vyakula",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", {
        name: "Badilisha: Faini ya kwanza ya kuchelewa",
      }),
    ).toBeTruthy();
  });

  it("is Historia for a seller, who reads the rules and changes none", async () => {
    rulesAnswer();

    render(<SettingsScreen />);

    await cardOf("Faini ya kwanza ya kuchelewa");
    expect(screen.queryByRole("button", { name: /^Badilisha/ })).toBeNull();
    expect(screen.getAllByRole("button", { name: /^Historia/ })).toHaveLength(
      20,
    );
  });

  it("is Badilisha only where the key is held: Dawa's lines for a manager given it on Dawa", async () => {
    // The key on one side, not on the whole shop: Dawa's tolerance is his, the late fine is not.
    rulesAnswer(
      SHOP_RULES,
      whoIsHere([
        { side: DAWA, permissions: ["settings.manage"] },
        { side: VYAKULA, permissions: ["sale.create"] },
      ]),
    );

    render(<SettingsScreen />);

    await cardOf("Faini ya kwanza ya kuchelewa");
    expect(
      screen
        .getAllByRole("button", { name: /^Badilisha/ })
        .map((button) => button.getAttribute("aria-label")),
    ).toEqual([
      "Badilisha: Tofauti ya droo inayokubalika, Dawa",
      "Badilisha: Tofauti ya kuhesabu mzigo inayokubalika, Dawa",
      "Badilisha: Onya kabla bidhaa haijaisha muda, Dawa",
      "Badilisha: Zuia kuuza zaidi ya mzigo uliopo, Dawa",
    ]);
    expect(
      screen.getByRole("button", {
        name: "Historia: Faini ya kwanza ya kuchelewa",
      }),
    ).toBeTruthy();
  });
});

describe("the history", () => {
  it("shows the 2,000 coming and the 1,000 in use, newest first (the card's first Done when)", async () => {
    rulesAnswer(
      withRule(
        line({
          value: "1000.00",
          rows: [
            row({
              value: "2000.00",
              effective_from: "2026-11-16",
              note: "Mkutano wa Novemba",
            }),
          ],
        }),
      ),
      OWNER,
    );

    render(<SettingsScreen />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Badilisha: Faini ya kwanza ya kuchelewa",
      }),
    );

    const fine = await cardOf("Faini ya kwanza ya kuchelewa");
    const lines = within(fine)
      .getAllByRole("listitem")
      .map((item) => item.textContent);
    expect(lines).toEqual([
      "TSh 2,000, kuanzia 16/11/2026InakujaImewekwa na Neema, 15/11/2026Maelezo: Mkutano wa Novemba",
      "TSh 1,000, ya awaliInatumika sasa",
    ]);
  });

  it("marks the row in use, says who set each and when, and the system's rows as the system's", async () => {
    // 1,500 since 1 November, set by the seed; 1,200 before that, set by Neema.
    rulesAnswer(
      withRule(
        line({
          value: "1500.00",
          rows: [
            row({
              value: "1500.00",
              effective_from: "2026-11-01",
              set_by: null,
              created_at: "2026-10-31T09:00:00Z",
            }),
            row({
              value: "1200.00",
              effective_from: "2026-10-01",
              created_at: "2026-09-30T09:00:00Z",
            }),
          ],
        }),
      ),
    );

    render(<SettingsScreen />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Historia: Faini ya kwanza ya kuchelewa",
      }),
    );

    const fine = await cardOf("Faini ya kwanza ya kuchelewa");
    expect(
      within(fine)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([
      "TSh 1,500, kuanzia 01/11/2026Inatumika sasaImewekwa na mfumo, 31/10/2026",
      "TSh 1,200, kuanzia 01/10/2026Imewekwa na Neema, 30/09/2026",
      "TSh 1,000, ya awali",
    ]);
  });

  it("says a row of the whole shop's on a side's line is the shop's", async () => {
    // Only code that skips the form could write it; the page shows why Vyakula's value is so.
    rulesAnswer(
      withRule(
        line({
          key: "cash.tolerance",
          scope: "side",
          side: VYAKULA.id,
          default: "0.00",
          value: "300.00",
          rows: [
            row({
              key: "cash.tolerance",
              side: null,
              value: "300.00",
              effective_from: "2026-11-01",
            }),
          ],
        }),
      ),
    );

    render(<SettingsScreen />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Historia: Tofauti ya droo inayokubalika, Vyakula",
      }),
    );

    expect(await screen.findByText("Ya duka zima")).toBeTruthy();
  });

  it("opens on its own for a seller, with no form, and Funga closes it", async () => {
    rulesAnswer();

    render(<SettingsScreen />);
    const button = await screen.findByRole("button", {
      name: "Historia: Faini ya kwanza ya kuchelewa",
    });
    fireEvent.click(button);

    expect(
      await screen.findByRole("heading", { name: "Historia", level: 4 }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Hifadhi" })).toBeNull();
    const close = screen.getByRole("button", { name: "Funga" });
    expect(close.getAttribute("aria-expanded")).toBe("true");

    fireEvent.click(close);

    expect(
      screen.queryByRole("heading", { name: "Historia", level: 4 }),
    ).toBeNull();
  });
});

describe("a save from the page", () => {
  it("shows the late fine's 2,000 coming once saved, says so, and gives the keyboard back to Badilisha", async () => {
    // The card's first Done when, end to end on the page: the server's answer changes after the save.
    const saved = row({ value: "2000.00", effective_from: "2026-11-16" });
    let rules = SHOP_RULES;
    answer("GET", ME, { status: 200, body: OWNER });
    answer("GET", RULES, () => Response.json(rules));
    answer("GET", SIDES, {
      status: 200,
      body: { next: null, previous: null, results: [] },
    });
    answer("POST", RULES, () => {
      rules = withRule(line({ value: "1000.00", rows: [saved] }));
      return Response.json(saved, { status: 201 });
    });

    render(<SettingsScreen />);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Badilisha: Faini ya kwanza ya kuchelewa",
      }),
    );
    fireEvent.change(screen.getByLabelText("Kiasi kipya (TSh)"), {
      target: { value: "2,000" },
    });
    fireEvent.change(screen.getByLabelText("Kuanzia tarehe"), {
      target: { value: "2026-11-16" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));

    const fine = await cardOf("Faini ya kwanza ya kuchelewa");
    expect(
      await within(fine).findByText("Kuanzia 16/11/2026: TSh 2,000"),
    ).toBeTruthy();
    // Today's is still 1,000.
    expect(within(fine).getByText("TSh 1,000")).toBeTruthy();
    expect(
      within(fine)
        .getByText("Imehifadhiwa. Thamani mpya inaanza 16/11/2026.")
        .getAttribute("role"),
    ).toBe("status");
    // The form is gone, and the keyboard is back on the button that opened it.
    expect(screen.queryByRole("button", { name: "Hifadhi" })).toBeNull();
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("button", {
          name: "Badilisha: Faini ya kwanza ya kuchelewa",
        }),
      ),
    );
  });
});
