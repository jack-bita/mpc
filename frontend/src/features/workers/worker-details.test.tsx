// worker-details.test.tsx — Badilisha on a worker's own page (PPL-10): the phone shown as the shop writes it, the
// details turned into boxes in their place, only the changed boxes sent with the version read and why, what the form
// and the server refuse and where each shows, a fix someone else made first, Ghairi, and no phone on the demo.
import { focusManager } from "@tanstack/react-query";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { DAWA } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { MANAGER, role, STAFF, worker } from "@/test/workers";

import { WorkerScreen } from "./worker-page";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type Worker = components["schemas"]["Staff"];

const ME = "/api/auth/me/";
const DEMO_OPEN = "/api/devices/v1/demo/open/";
const WHY = "Niliandika vibaya";

// Wednesday 18 Nov 2026, 12:00 in Dar es Salaam: the shop's today in these tests. Only the date is faked, so the
// store's and the tests' own timers run as ever.
beforeEach(() => {
  vi.useFakeTimers({
    now: Date.parse("2026-11-18T09:00:00Z"),
    toFake: ["Date"],
  });
});
afterEach(() => {
  vi.useRealTimers();
  // A test that moved the window's focus gives it back to the browser's own (focusManager).
  focusManager.setFocused(undefined);
});

/** Asha, a seller on Dawa since 3 Nov, with no phone yet, never fixed since she was added (version 1). */
const ASHA = worker({
  full_name: "Asha Mfano",
  display_name: "Asha",
  job_title: "Muuzji",
  started_on: "2026-11-03",
  roles: [role("seller", DAWA.id)],
});

/** The manager is logged in, and the server holds `start`; `now` changes what it answers from then on, as a change
 * the server made would. */
function theServerHas(start: Worker) {
  let held = start;
  answer("GET", ME, { status: 200, body: MANAGER });
  answer("GET", `${STAFF}${start.id}/`, () => Response.json(held));
  return {
    now(changed: Worker) {
      held = changed;
    },
  };
}

/** Asha's own address, where a fix is sent. */
const ASHAS = `${STAFF}${ASHA.id}/`;

/** What the app sent to fix a worker, as the server would read it. */
async function fixesSent(): Promise<Record<string, unknown>[]> {
  return Promise.all(
    sent
      .filter((request) => request.method === "PATCH")
      .map((request) => request.json() as Promise<Record<string, unknown>>),
  );
}

/** The error beside a box: the one its aria-describedby names, after its hint (field.tsx). */
function errorOf(box: HTMLElement): string {
  const ids = box.getAttribute("aria-describedby")?.split(" ") ?? [];
  const error = ids.find((id) => id.endsWith("-error"));
  return error ? (document.getElementById(error)?.textContent ?? "") : "";
}

function typeInto(box: HTMLElement, text: string) {
  fireEvent.change(box, { target: { value: text } });
}

const button = (name: string) => screen.getByRole("button", { name });
const findButton = (name: string) => screen.findByRole("button", { name });
const box = (label: string) => screen.getByLabelText(label) as HTMLInputElement;

/** Opens Badilisha on Asha's page. */
async function openTheFix() {
  render(<WorkerScreen id={ASHA.id} />);
  fireEvent.click(await findButton("Badilisha"));
}

describe("a worker's phone on their page", () => {
  it("shows as the shop writes it, and Hakuna when there is none", async () => {
    theServerHas({ ...ASHA, phone: "+255712345678" });
    const { unmount } = render(<WorkerScreen id={ASHA.id} />);
    expect(await screen.findByText("0712 345 678")).toBeTruthy();
    unmount();

    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);
    await findButton("Badilisha");
    const phone = screen.getByText("Simu").nextElementSibling;
    expect(phone?.textContent).toBe("Hakuna");
  });
});

describe("Badilisha", () => {
  it("turns the details into boxes in their place, filled in, with the keyboard in the first (Jack's picture)", async () => {
    theServerHas({ ...ASHA, phone: "+255712345678" });

    await openTheFix();

    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe(
      "Badilisha taarifa za Asha",
    );
    expect(box("Jina kamili").value).toBe("Asha Mfano");
    expect(box("Jina la kuitwa").value).toBe("Asha");
    expect(box("Kazi").value).toBe("Muuzji");
    expect(box("Siku ya kwanza").value).toBe("2026-11-03");
    expect(box("Simu").value).toBe("0712 345 678");
    expect(box("Sababu").value).toBe("");
    expect(document.activeElement).toBe(box("Jina kamili"));
    // The details are in the boxes now, not shown twice, and the other buttons wait until the form closes.
    expect(screen.queryByText("Hali")).toBeNull();
    expect(screen.queryByRole("button", { name: "Simamisha" })).toBeNull();
  });

  it("sends only the boxes that changed, with the version it read and why, and shows Asha as saved (the card's first two Done when)", async () => {
    const server = theServerHas(ASHA);
    const fixed = {
      ...ASHA,
      job_title: "Muuzaji",
      phone: "+255754000111",
      version: 2,
    };
    answer("PATCH", ASHAS, () => {
      server.now(fixed);
      return Response.json(fixed);
    });
    await openTheFix();

    typeInto(box("Kazi"), "Muuzaji ");
    typeInto(box("Simu"), "0754 000 111");
    typeInto(box("Sababu"), ` ${WHY} `);
    fireEvent.click(button("Hifadhi"));

    expect(
      await screen.findByText("Taarifa za Asha zimehifadhiwa."),
    ).toBeTruthy();
    // The spaces around each taken off, as the server keeps them; the phone as typed, which the server cleans.
    expect(await fixesSent()).toEqual([
      { version: 1, reason: WHY, job_title: "Muuzaji", phone: "0754 000 111" },
    ]);
    // The details back in their place, as saved.
    expect(await screen.findByText("0754 000 111")).toBeTruthy();
    expect(screen.getByText("Muuzaji")).toBeTruthy();
    // The keyboard on the line that says what happened.
    expect(document.activeElement?.textContent).toBe(
      "Taarifa za Asha zimehifadhiwa.",
    );
  });

  it("takes the phone off with an empty box", async () => {
    const server = theServerHas({ ...ASHA, phone: "+255712345678" });
    answer("PATCH", ASHAS, () => {
      const fixed = { ...ASHA, phone: null, version: 2 };
      server.now(fixed);
      return Response.json(fixed);
    });
    await openTheFix();

    typeInto(box("Simu"), "");
    typeInto(box("Sababu"), WHY);
    fireEvent.click(button("Hifadhi"));

    await screen.findByText("Taarifa za Asha zimehifadhiwa.");
    expect(await fixesSent()).toEqual([{ version: 1, reason: WHY, phone: "" }]);
  });

  it("says nothing was changed, and sends nothing, when every box is as it was", async () => {
    theServerHas(ASHA);
    await openTheFix();

    // Typed back as it was, spaces and all.
    typeInto(box("Kazi"), " Muuzji ");
    fireEvent.click(button("Hifadhi"));

    expect(await screen.findByText("Hukubadilisha chochote.")).toBeTruthy();
    expect(await fixesSent()).toEqual([]);
  });

  it("says what it can see beside each box, and sends nothing", async () => {
    theServerHas(ASHA);
    await openTheFix();

    typeInto(box("Jina kamili"), "   ");
    typeInto(box("Jina la kuitwa"), "");
    fireEvent.click(button("Hifadhi"));

    expect(errorOf(box("Jina kamili"))).toBe("Sehemu hii haiwezi kuwa tupu.");
    expect(errorOf(box("Jina la kuitwa"))).toBe(
      "Sehemu hii haiwezi kuwa tupu.",
    );
    expect(errorOf(box("Sababu"))).toBe("Andika sababu.");
    expect(await fixesSent()).toEqual([]);
  });

  it("shows the server's refusals beside their boxes: a phone wrong or taken, a nickname taken", async () => {
    theServerHas(ASHA);
    answer(
      "PATCH",
      ASHAS,
      refusal(400, "invalid", {}, { phone: ["phone.invalid"] }),
    );
    await openTheFix();

    typeInto(box("Simu"), "12345");
    typeInto(box("Sababu"), WHY);
    fireEvent.click(button("Hifadhi"));
    await waitFor(() =>
      expect(errorOf(box("Simu"))).toBe("Namba hii ya simu si sahihi."),
    );

    // Someone else has the number: the server says only that it is in use, never whose.
    answer("PATCH", ASHAS, refusal(400, "invalid", {}, { phone: ["unique"] }));
    typeInto(box("Simu"), "0712 345 678");
    fireEvent.click(button("Hifadhi"));
    await waitFor(() => expect(errorOf(box("Simu"))).toBe("Hiki tayari kipo."));

    // The nickname another current worker has: the whole request's code, shown where the owner fixes it.
    answer("PATCH", ASHAS, refusal(400, "staff.display_name_taken"));
    typeInto(box("Jina la kuitwa"), "Neema");
    fireEvent.click(button("Hifadhi"));
    await waitFor(() =>
      expect(errorOf(box("Jina la kuitwa"))).toBe(
        "Mfanyakazi mwingine tayari ana jina hili la kuitwa. Chagua jingine.",
      ),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows who may above the buttons, and keeps the boxes", async () => {
    theServerHas(ASHA);
    answer("PATCH", ASHAS, refusal(400, "staff.superuser_only"));
    await openTheFix();

    typeInto(box("Kazi"), "Muuzaji");
    typeInto(box("Sababu"), WHY);
    fireEvent.click(button("Hifadhi"));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Hali ya kazi ya mtu huyu inabadilishwa na msimamizi wa mfumo tu.",
    );
    expect(box("Kazi").value).toBe("Muuzaji");
  });

  it("after someone else's fix, closes, says so, and shows Asha as she is now (the card's third Done when)", async () => {
    // Baba fixed Asha while Meneja's form was open: Meneja's fix, from version 1, would undo his.
    const server = theServerHas(ASHA);
    answer("PATCH", ASHAS, () => {
      server.now({ ...ASHA, job_title: "Fundi", version: 2 });
      return Response.json(
        {
          code: "version_conflict",
          message: "version_conflict",
          fields: {},
          params: {},
        },
        { status: 409 },
      );
    });
    await openTheFix();

    typeInto(box("Kazi"), "Muuzaji");
    typeInto(box("Sababu"), WHY);
    fireEvent.click(button("Hifadhi"));

    expect(
      await screen.findByText(
        "Mtu mwingine amebadilisha taarifa za Asha kabla yako. Hizi ndizo taarifa zake sasa: jaribu tena kama bado kuna cha kurekebisha.",
      ),
    ).toBeTruthy();
    // Read again: Baba's fix on the page, nothing of Meneja's.
    expect(await screen.findByText("Fundi")).toBeTruthy();
    expect(screen.queryByLabelText("Kazi")).toBeNull();
  });

  it("closes with Ghairi, shows the details again, and puts the keyboard back on Badilisha", async () => {
    theServerHas(ASHA);
    await openTheFix();

    typeInto(box("Kazi"), "Muuzaji");
    fireEvent.click(button("Ghairi"));

    await waitFor(() =>
      expect(document.activeElement).toBe(button("Badilisha")),
    );
    expect(screen.getByText("Muuzji")).toBeTruthy();
    expect(await fixesSent()).toEqual([]);
  });

  it("sends the version it opened on, even after the page reads a newer Asha behind it", async () => {
    // Baba fixes Asha while Meneja types. The page reads her again behind the open form, as it does when the window
    // gets its focus back. Meneja's boxes were typed on the copy he opened: sent with Baba's newer version, they
    // would undo Baba's fix all the same, so the form keeps its own, and the server says someone got there first.
    const server = theServerHas(ASHA);
    answer("PATCH", ASHAS, refusal(409, "version_conflict"));
    await openTheFix();
    typeInto(box("Kazi"), "Muuzaji");
    server.now({ ...ASHA, job_title: "Fundi", version: 2 });
    const reads = () =>
      sent.filter(
        (request) =>
          request.method === "GET" && new URL(request.url).pathname === ASHAS,
      ).length;
    const before = reads();

    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    await waitFor(() => expect(reads()).toBeGreaterThan(before));

    // Meneja's typing stays, on the copy he opened.
    expect(box("Kazi").value).toBe("Muuzaji");
    typeInto(box("Sababu"), WHY);
    fireEvent.click(button("Hifadhi"));
    await screen.findByText(/Mtu mwingine amebadilisha taarifa za Asha/);
    expect(await fixesSent()).toEqual([
      { version: 1, reason: WHY, job_title: "Muuzaji" },
    ]);
  });

  it("asks once about a first day moved far from today, and sends it the second time", async () => {
    theServerHas(ASHA);
    answer("PATCH", ASHAS, () =>
      Response.json({ ...ASHA, started_on: "2025-11-03", version: 2 }),
    );
    await openTheFix();

    // 2025 for 2026, a year typed wrong: every pay and attendance count would start in the wrong place.
    typeInto(box("Siku ya kwanza"), "2025-11-03");
    typeInto(box("Sababu"), WHY);
    fireEvent.click(button("Hifadhi"));
    expect(
      await screen.findByText(
        "03/11/2025 iko mbali na leo. Kama ni sahihi, bonyeza Hifadhi tena.",
      ),
    ).toBeTruthy();
    expect(await fixesSent()).toEqual([]);

    fireEvent.click(button("Hifadhi"));
    await screen.findByText("Taarifa za Asha zimehifadhiwa.");
    expect(await fixesSent()).toEqual([
      { version: 1, reason: WHY, started_on: "2025-11-03" },
    ]);
  });
});

describe("on the demo", () => {
  it("keeps the phone box off and says why, while the other boxes still fix (Jack, PPL-10: A)", async () => {
    theServerHas(ASHA);
    answer("GET", DEMO_OPEN, { status: 200, body: { open: true } });
    answer("PATCH", ASHAS, () =>
      Response.json({ ...ASHA, job_title: "Mpakiaji", version: 2 }),
    );
    await openTheFix();

    await waitFor(() => expect(box("Simu").disabled).toBe(true));
    expect(
      screen.getByText(
        "Kwenye demo, wafanyakazi hawawekewi namba ya simu, ili namba halisi ya mtu isionekane kwa kila mgeni.",
      ),
    ).toBeTruthy();
    typeInto(box("Kazi"), "Mpakiaji");
    typeInto(box("Sababu"), WHY);
    fireEvent.click(button("Hifadhi"));

    await screen.findByText("Taarifa za Asha zimehifadhiwa.");
    expect(await fixesSent()).toEqual([
      { version: 1, reason: WHY, job_title: "Mpakiaji" },
    ]);
  });
});
