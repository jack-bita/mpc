// side-switch.test.tsx — Pande (SHOP-5): each side, on or off; the switch only for someone holding
// settings.manage on it; a question first, both ways, which Hapana answers with nothing sent (the card's fourth
// Done when); the switch sent alone with the version read; and the demo's refusal, and someone else's change,
// each said beside the switch. And Rangi (SHOP-4): each side's band, and Badilisha, which opens both bands, and Hifadhi
// sends the one picked, alone, with the version read as the form opened.
import { focusManager, onlineManager } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { OWNER } from "@/test/settings";

import { SideSwitches } from "./side-switch";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type Side = components["schemas"]["Side"];

const SIDES = "/api/v1/shops/sides/";

// A test that takes the network away puts it back after: navigator.onLine's spy, and TanStack's own note of the
// network, which an "offline" event also changes and which every later test's reads would wait on.
afterEach(() => {
  vi.restoreAllMocks();
  onlineManager.setOnline(true);
});

/** A side as the server sends it: Dawa on, at version 3, unless told otherwise. */
function side(fields: Partial<Side> = {}): Side {
  return {
    ...DAWA,
    sale_flow: "one_screen",
    is_live: true,
    created_at: "2026-10-01T07:00:00Z",
    updated_at: null,
    version: 3,
    ...fields,
  };
}

const DAWA_ON = side();
// Vyakula, not started yet: a new side starts off (SHOP-2).
const VYAKULA_OFF = side({
  ...VYAKULA,
  sale_flow: "writer_cashier_loader",
  is_live: false,
  version: 1,
});

/** The sides as the server lists them, in the order it made them: Vyakula first, so the page's own order shows. */
function sidesAnswer(...sides: Side[]) {
  answer("GET", SIDES, {
    status: 200,
    body: { next: null, previous: null, results: sides },
  });
}

/** One side's box on the page, found by its name. */
async function boxOf(name: string): Promise<HTMLElement> {
  const label = await screen.findByText(name, { selector: "span" });
  const box = label.closest("li");
  if (!(box instanceof HTMLElement)) throw new Error(`No side ${name}`);
  return box;
}

/** What the app sent to switch a side: its address and body. */
async function switches(): Promise<{ path: string; body: unknown }[]> {
  return Promise.all(
    sent
      .filter((request) => request.method === "PATCH")
      .map(async (request) => ({
        path: new URL(request.url).pathname,
        body: await request.json(),
      })),
  );
}

describe("Pande", () => {
  it("shows each side, on or off, by its letter", async () => {
    sidesAnswer(VYAKULA_OFF, DAWA_ON);

    render(<SideSwitches me={OWNER} />);

    await boxOf("Dawa");
    expect(
      screen.getAllByRole("listitem").map((item) => item.textContent),
    ).toEqual([
      expect.stringMatching(/^DawaImewashwa/),
      expect.stringMatching(/^VyakulaImezimwa/),
    ]);
  });

  it("gives no switch to someone without the key, who sees only on or off", async () => {
    sidesAnswer(DAWA_ON, VYAKULA_OFF);

    render(
      <SideSwitches
        me={whoIsHere([
          { side: DAWA, permissions: ["sale.create"] },
          { side: VYAKULA, permissions: ["sale.create"] },
        ])}
      />,
    );

    await boxOf("Dawa");
    expect(screen.getByText("Imewashwa")).toBeTruthy();
    // Each side's band too, in words beside its colour (SHOP-4), with no Badilisha.
    expect(screen.getByText("Bluu")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("gives the switch only on the side where the key is held", async () => {
    sidesAnswer(DAWA_ON, VYAKULA_OFF);

    render(
      <SideSwitches
        me={whoIsHere([
          { side: DAWA, permissions: ["settings.manage"] },
          { side: VYAKULA, permissions: ["sale.create"] },
        ])}
      />,
    );

    await boxOf("Dawa");
    expect(
      screen
        .getAllByRole("button")
        .map((button) => button.getAttribute("aria-label")),
    ).toEqual(["Zima: Dawa", "Badilisha rangi: Dawa"]);
  });
});

describe("Rangi", () => {
  /** One side's band, as its box shows it: the word beside the colour. */
  function bandOf(box: HTMLElement): string | null {
    return box.querySelector("[data-look]")?.closest("p")?.textContent ?? null;
  }

  it("shows each side's band, the colour beside its word (SHOP-4)", async () => {
    sidesAnswer(DAWA_ON, VYAKULA_OFF);
    render(<SideSwitches me={OWNER} />);

    const dawa = await boxOf("Dawa");
    const vyakula = await boxOf("Vyakula");
    expect(bandOf(dawa)).toBe("RangiBluu");
    expect(dawa.querySelector("[data-look]")?.getAttribute("data-look")).toBe(
      "blue",
    );
    expect(bandOf(vyakula)).toBe("RangiMistari");
  });

  it("opens both bands with the side's own picked, and Ghairi sends nothing", async () => {
    sidesAnswer(DAWA_ON, VYAKULA_OFF);
    render(<SideSwitches me={OWNER} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Badilisha rangi: Dawa" }),
    );

    const dawa = await boxOf("Dawa");
    const choice = within(dawa).getByRole("radiogroup", {
      name: "Rangi ya Dawa",
    });
    // Each row shows the band itself beside its word, so the owner sees what he picks.
    expect(
      [...choice.querySelectorAll("[data-look]")].map((band) =>
        band.getAttribute("data-look"),
      ),
    ).toEqual(["blue", "striped"]);
    const blue = within(choice).getByRole("radio", { name: "Bluu" });
    expect(blue.getAttribute("aria-checked")).toBe("true");
    // The keyboard starts on the side's own band, where the Badilisha button that had it was.
    expect(document.activeElement).toBe(blue);

    fireEvent.click(within(dawa).getByRole("button", { name: "Ghairi" }));

    expect(within(dawa).queryByRole("radiogroup")).toBeNull();
    expect(await switches()).toEqual([]);
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("button", { name: "Badilisha rangi: Dawa" }),
      ),
    );
  });

  it("saves the band picked, sending it alone with the version read as the form opened", async () => {
    sidesAnswer(DAWA_ON, VYAKULA_OFF);
    answer("PATCH", `${SIDES}${DAWA.id}/`, {
      status: 200,
      body: side({ band: "striped", version: 4 }),
    });
    render(<SideSwitches me={OWNER} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Badilisha rangi: Dawa" }),
    );
    fireEvent.click(screen.getByRole("radio", { name: "Mistari" }));
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));

    const dawa = await boxOf("Dawa");
    expect(
      await within(dawa).findByText("Rangi ya Dawa imehifadhiwa."),
    ).toBeTruthy();
    expect(bandOf(dawa)).toBe("RangiMistari");
    expect(within(dawa).queryByRole("radiogroup")).toBeNull();
    expect(await switches()).toEqual([
      { path: `${SIDES}${DAWA.id}/`, body: { band: "striped", version: 3 } },
    ]);
  });

  it("sends nothing when the band picked is the one the side has", async () => {
    // Nothing changed: Hifadhi closes the form, as Ghairi does, with no new version and no change for the laptops.
    sidesAnswer(DAWA_ON, VYAKULA_OFF);
    render(<SideSwitches me={OWNER} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Badilisha rangi: Dawa" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));

    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(await switches()).toEqual([]);
  });

  it("switches Badilisha and Hifadhi off while there is no network", async () => {
    sidesAnswer(DAWA_ON, VYAKULA_OFF);
    const online = vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    render(<SideSwitches me={OWNER} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Badilisha rangi: Dawa" }),
    );

    online.mockReturnValue(false);
    act(() => window.dispatchEvent(new Event("offline")));

    expect(screen.getByRole("button", { name: "Hifadhi" })).toHaveProperty(
      "disabled",
      true,
    );
    fireEvent.click(screen.getByRole("button", { name: "Ghairi" }));
    expect(
      screen.getByRole("button", { name: "Badilisha rangi: Dawa" }),
    ).toHaveProperty("disabled", true);
  });

  it("says the demo's refusal beside the band, and the band stays as it was", async () => {
    // On the demo, a visitor's colour would greet every visitor after them (Jack, SHOP-4).
    sidesAnswer(DAWA_ON, VYAKULA_OFF);
    answer("PATCH", `${SIDES}${DAWA.id}/`, refusal(400, "demo.sides_fixed"));
    render(<SideSwitches me={OWNER} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Badilisha rangi: Dawa" }),
    );
    fireEvent.click(screen.getByRole("radio", { name: "Mistari" }));
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));

    const dawa = await boxOf("Dawa");
    expect((await within(dawa).findByRole("alert")).textContent).toContain(
      "Kwenye demo, pande hazibadilishwi",
    );
    expect(bandOf(dawa)).toBe("RangiBluu");
  });

  it("says someone else changed the side meanwhile, and reads it again", async () => {
    // Another manager made Dawa striped from her phone while this page was open: the form sends the version read as
    // it opened, which the server refuses, and the page reads the side again.
    let reads = 0;
    answer("GET", SIDES, () => {
      reads += 1;
      return Response.json({
        next: null,
        previous: null,
        results:
          reads === 1
            ? [DAWA_ON, VYAKULA_OFF]
            : [side({ band: "striped", version: 4 }), VYAKULA_OFF],
      });
    });
    answer("PATCH", `${SIDES}${DAWA.id}/`, refusal(409, "version_conflict"));
    render(<SideSwitches me={OWNER} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Badilisha rangi: Dawa" }),
    );
    fireEvent.click(screen.getByRole("radio", { name: "Mistari" }));
    fireEvent.click(screen.getByRole("button", { name: "Hifadhi" }));

    const dawa = await boxOf("Dawa");
    expect((await within(dawa).findByRole("alert")).textContent).toContain(
      "Mtu mwingine amebadilisha hiki wakati huo huo.",
    );
    await waitFor(() => expect(bandOf(dawa)).toBe("RangiMistari"));
    expect(reads).toBe(2);
  });
});

describe("the switch", () => {
  it("asks before switching a side off, and Hapana changes nothing (the card's fourth Done when)", async () => {
    sidesAnswer(DAWA_ON, VYAKULA_OFF);
    render(<SideSwitches me={OWNER} />);

    fireEvent.click(await screen.findByRole("button", { name: "Zima: Dawa" }));

    const dawa = await boxOf("Dawa");
    expect(
      within(dawa).getByText(
        "Zima upande wa Dawa? Hautatumika kwenye kompyuta za duka hadi uuwashe tena.",
      ),
    ).toBeTruthy();
    // The keyboard starts on Hapana, so an Enter pressed by mistake changes nothing.
    const no = within(dawa).getByRole("button", { name: "Hapana" });
    expect(document.activeElement).toBe(no);

    fireEvent.click(no);

    expect(await switches()).toEqual([]);
    expect(within(dawa).getByText("Imewashwa")).toBeTruthy();
    // The keyboard is back on the switch.
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("button", { name: "Zima: Dawa" }),
      ),
    );
  });

  it("ties its question to both answers, so a screen reader says it with each (SHOP-5's review)", async () => {
    // The keyboard lands on Hapana: "Hapana, button" alone would skip the question the confirm is there to ask.
    sidesAnswer(DAWA_ON, VYAKULA_OFF);
    render(<SideSwitches me={OWNER} />);

    fireEvent.click(await screen.findByRole("button", { name: "Zima: Dawa" }));

    for (const reply of ["Hapana", "Ndiyo, zima"]) {
      const button = screen.getByRole("button", { name: reply });
      const said = document.getElementById(
        button.getAttribute("aria-describedby") ?? "",
      );
      expect(said?.textContent, reply).toBe(
        "Zima upande wa Dawa? Hautatumika kwenye kompyuta za duka hadi uuwashe tena.",
      );
    }
  });

  it("switches a side off after the yes, sending the switch alone with the version it read", async () => {
    sidesAnswer(DAWA_ON, VYAKULA_OFF);
    answer("PATCH", `${SIDES}${DAWA.id}/`, {
      status: 200,
      body: side({ is_live: false, version: 4 }),
    });
    render(<SideSwitches me={OWNER} />);

    fireEvent.click(await screen.findByRole("button", { name: "Zima: Dawa" }));
    fireEvent.click(screen.getByRole("button", { name: "Ndiyo, zima" }));

    const dawa = await boxOf("Dawa");
    expect(
      await within(dawa).findByText("Upande wa Dawa umezimwa."),
    ).toBeTruthy();
    expect(within(dawa).getByText("Imezimwa")).toBeTruthy();
    expect(await switches()).toEqual([
      {
        path: `${SIDES}${DAWA.id}/`,
        body: { is_live: false, version: 3 },
      },
    ]);
    // The next switch is Washa, and would send the new version, 4.
    expect(screen.getByRole("button", { name: "Washa: Dawa" })).toBeTruthy();
  });

  it("switches both answers off while the switch is on its way (SHOP-5's review)", async () => {
    // Sent, a switch can't be called back: a Hapana tapped then would close the question and hide a switch that still
    // goes through.
    sidesAnswer(DAWA_ON, VYAKULA_OFF);
    answer(
      "PATCH",
      `${SIDES}${DAWA.id}/`,
      () => new Promise<Response>(() => undefined),
    );
    render(<SideSwitches me={OWNER} />);

    fireEvent.click(await screen.findByRole("button", { name: "Zima: Dawa" }));
    fireEvent.click(screen.getByRole("button", { name: "Ndiyo, zima" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Hapana" })).toHaveProperty(
        "disabled",
        true,
      ),
    );
    expect(screen.getByRole("button", { name: "Ndiyo, zima" })).toHaveProperty(
      "disabled",
      true,
    );
  });

  it("switches the switch off while there is no network (SHOP-5's review)", async () => {
    // A switch can't be sent offline: the button waits for the network, as the office's every change does.
    sidesAnswer(DAWA_ON, VYAKULA_OFF);
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

    render(<SideSwitches me={OWNER} />);

    expect(
      await screen.findByRole("button", { name: "Zima: Dawa" }),
    ).toHaveProperty("disabled", true);
  });

  it("switches the question's yes off when the network goes while it is open", async () => {
    sidesAnswer(DAWA_ON, VYAKULA_OFF);
    const online = vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    render(<SideSwitches me={OWNER} />);
    fireEvent.click(await screen.findByRole("button", { name: "Zima: Dawa" }));

    online.mockReturnValue(false);
    act(() => window.dispatchEvent(new Event("offline")));

    expect(screen.getByRole("button", { name: "Ndiyo, zima" })).toHaveProperty(
      "disabled",
      true,
    );
  });

  it("asks before switching a side on too", async () => {
    // Vyakula reaches the shop's laptops once switched on: as big a change as switching one off.
    sidesAnswer(DAWA_ON, VYAKULA_OFF);
    answer("PATCH", `${SIDES}${VYAKULA.id}/`, {
      status: 200,
      body: { ...VYAKULA_OFF, is_live: true, version: 2 },
    });
    render(<SideSwitches me={OWNER} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Washa: Vyakula" }),
    );
    expect(
      screen.getByText(
        "Washa upande wa Vyakula? Utaanza kutumika kwenye kompyuta za duka.",
      ),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Ndiyo, washa" }));

    expect(
      await screen.findByText("Upande wa Vyakula umewashwa."),
    ).toBeTruthy();
    expect(await switches()).toEqual([
      {
        path: `${SIDES}${VYAKULA.id}/`,
        body: { is_live: true, version: 1 },
      },
    ]);
  });

  it("sends what its question asked, even after the page read the side again meanwhile (SHOP-5's review)", async () => {
    // The owner taps Zima on Dawa. While the question is open, another manager switches Dawa off from her phone, and
    // the owner's page reads the sides again as his phone comes back to it. The question still asks "Zima?", and Ndiyo
    // sends the version he read, so the server refuses it: never "Washa", with the new version, switching Dawa back on.
    let reads = 0;
    answer("GET", SIDES, () => {
      reads += 1;
      return Response.json({
        next: null,
        previous: null,
        results:
          reads === 1
            ? [DAWA_ON, VYAKULA_OFF]
            : [side({ is_live: false, version: 4 }), VYAKULA_OFF],
      });
    });
    answer("PATCH", `${SIDES}${DAWA.id}/`, refusal(409, "version_conflict"));
    render(<SideSwitches me={OWNER} />);
    fireEvent.click(await screen.findByRole("button", { name: "Zima: Dawa" }));

    // The phone goes to another app and comes back: TanStack reads the sides again (refetchOnWindowFocus).
    act(() => focusManager.setFocused(false));
    act(() => focusManager.setFocused(true));
    const dawa = await boxOf("Dawa");
    await waitFor(() =>
      expect(within(dawa).getByText("Imezimwa")).toBeTruthy(),
    );

    expect(
      within(dawa).getByText(
        "Zima upande wa Dawa? Hautatumika kwenye kompyuta za duka hadi uuwashe tena.",
      ),
    ).toBeTruthy();
    fireEvent.click(within(dawa).getByRole("button", { name: "Ndiyo, zima" }));

    expect(await within(dawa).findByRole("alert")).toBeTruthy();
    expect(await switches()).toEqual([
      { path: `${SIDES}${DAWA.id}/`, body: { is_live: false, version: 3 } },
    ]);
    act(() => focusManager.setFocused(undefined));
  });

  it("says the demo's refusal beside the switch, and the side stays as it was", async () => {
    // On the demo, the sides stay as the seed made them (SHOP-3's review).
    sidesAnswer(DAWA_ON, VYAKULA_OFF);
    answer("PATCH", `${SIDES}${DAWA.id}/`, refusal(400, "demo.sides_fixed"));
    render(<SideSwitches me={OWNER} />);

    fireEvent.click(await screen.findByRole("button", { name: "Zima: Dawa" }));
    fireEvent.click(screen.getByRole("button", { name: "Ndiyo, zima" }));

    const dawa = await boxOf("Dawa");
    expect((await within(dawa).findByRole("alert")).textContent).toContain(
      "Kwenye demo, pande hazibadilishwi",
    );
    expect(within(dawa).getByText("Imewashwa")).toBeTruthy();
  });

  it("says someone else changed the side meanwhile, and reads it again", async () => {
    // Another manager switched Dawa off from her phone while this page was open.
    let reads = 0;
    answer("GET", SIDES, () => {
      reads += 1;
      return Response.json({
        next: null,
        previous: null,
        results:
          reads === 1
            ? [DAWA_ON, VYAKULA_OFF]
            : [side({ is_live: false, version: 4 }), VYAKULA_OFF],
      });
    });
    answer("PATCH", `${SIDES}${DAWA.id}/`, refusal(409, "version_conflict"));
    render(<SideSwitches me={OWNER} />);

    fireEvent.click(await screen.findByRole("button", { name: "Zima: Dawa" }));
    fireEvent.click(screen.getByRole("button", { name: "Ndiyo, zima" }));

    const dawa = await boxOf("Dawa");
    expect((await within(dawa).findByRole("alert")).textContent).toContain(
      "Mtu mwingine amebadilisha hiki wakati huo huo.",
    );
    // Read again: the page now shows what she did.
    expect(await within(dawa).findByText("Imezimwa")).toBeTruthy();
    expect(reads).toBe(2);
  });
});
