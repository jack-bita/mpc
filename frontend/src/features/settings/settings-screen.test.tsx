// settings-screen.test.tsx — Mipangilio ya duka (SHOP-5): every rule of the registry on one page, under its
// area, a side's rule with a line per side; each value written its own way; a value set to start later shown
// beside today's; the page in English; and why, when the server refuses.
import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { setLanguage } from "@/i18n/language";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal } from "@/test/fake-server";
import { render } from "@/test/render";
import { line, row, SHOP_RULES, withRule } from "@/test/settings";

import { SettingsScreen } from "./settings-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const RULES = "/api/v1/shops/settings/";

// A seller on each side: reading the rules needs no key.
const SELLER = whoIsHere([
  { side: DAWA, permissions: ["sale.create"] },
  { side: VYAKULA, permissions: ["sale.create"] },
]);

function rulesAnswer(rules = SHOP_RULES) {
  answer("GET", ME, { status: 200, body: SELLER });
  answer("GET", RULES, { status: 200, body: rules });
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
  it("shows every rule of the registry once, under its area", async () => {
    rulesAnswer();

    render(<SettingsScreen />);

    await cardOf("Faini ya kuchelewa");
    expect(
      screen
        .getAllByRole("heading", { level: 2 })
        .map((each) => each.textContent),
    ).toEqual(["Mahudhurio", "Pesa", "Kompyuta", "Mzigo"]);
    expect(
      screen
        .getAllByRole("heading", { level: 3 })
        .map((each) => each.textContent),
    ).toEqual([
      "Mwisho wa kufika kwa wakati",
      "Faini ya kuchelewa",
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
    const fine = await cardOf("Faini ya kuchelewa");
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
    expect(await cardText("Faini ya kuchelewa")).toContain("TSh 1,000");
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

    expect(await cardText("Faini ya kuchelewa")).toContain(
      "Inakatwa kwenye mshahara kwa kila siku ya kuchelewa.",
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

    const fine = await cardOf("Faini ya kuchelewa");
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

    expect(await cardText("Late fine")).toContain("TSh 1,000");
    // English writes the time alone, as the clock-in does.
    expect(await cardText("On time until")).toContain("07:35");
    expect(await cardText("Lock after no use")).toContain("15 minutes");
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

    await cardOf("Faini ya kuchelewa");
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(8);
    expect(screen.queryByText(/half_day_after/)).toBeNull();
  });
});
