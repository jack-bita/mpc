// worker-details.test.tsx — Badilisha (PPL-10), on a page of its own since UI-11: the phone shown on the worker's page
// as the shop writes it; the details in boxes on Badilisha taarifa za Asha, opened on her own read; only the changed
// boxes sent with the version read and why; what the form and the server refuse and where each shows; a fix someone
// else made first; the way back to her page, with its line, and no Ghairi; what the page says for a worker it can't
// act on; and no phone on the demo.
import { focusManager, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import type { components } from "@/api/schema";
import { MOVED_IN_APP } from "@/components/in-app-moves";
import { DAWA } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { router } from "@/test/router";
import { MANAGER, role, STAFF, worker } from "@/test/workers";

import { EditWorkerScreen } from "./edit-worker-screen";
import { forgetNews, peekNews } from "./page-news";
import { WorkerScreen } from "./worker-page";
import { workerPage, WORKERS } from "./workers";

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
  // A test that takes the network away puts it back after (navigator.onLine's spy).
  vi.restoreAllMocks();
  // A line left by a test is never read by the next one's page; nor a move noted by one, by the next one's way back.
  forgetNews();
  window.sessionStorage.clear();
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

/** Opens Badilisha taarifa za Asha, and waits for its form. */
async function openTheFix(id: string = ASHA.id) {
  render(<EditWorkerScreen id={id} />);
  await screen.findByLabelText("Jina kamili");
}

/** Asha's page came before this one, in the app (in-app-moves.tsx): the arrow, and Hifadhi, go back to it. */
function cameFromHerPage() {
  window.sessionStorage.setItem(MOVED_IN_APP, "1");
  vi.spyOn(window.history, "length", "get").mockReturnValue(3);
}

/** Waits for Hifadhi's move to the worker's page, and gives the line it left for Taarifa zake there. */
async function landedWith(): Promise<string | undefined> {
  await waitFor(() =>
    expect(
      router.back.mock.calls.length + router.replace.mock.calls.length,
    ).toBe(1),
  );
  const news = peekNews();
  expect(news?.card).toBe("details");
  return news?.sentence;
}

describe("a worker's phone on their page", () => {
  it("shows as the shop writes it, and Hakuna when there is none", async () => {
    theServerHas({ ...ASHA, phone: "+255712345678" });
    const { unmount } = render(<WorkerScreen id={ASHA.id} />);
    expect(await screen.findByText("0712 345 678")).toBeTruthy();
    unmount();

    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);
    // A link to Badilisha's own page (UI-11).
    await screen.findByRole("link", { name: "Badilisha" });
    const phone = screen.getByText("Simu").nextElementSibling;
    expect(phone?.textContent).toBe("Hakuna");
  });
});

describe("Badilisha", () => {
  it("shows the details in boxes on a page of its own, filled in, with the keyboard in the first (the card's second Done when)", async () => {
    theServerHas({ ...ASHA, phone: "+255712345678" });

    await openTheFix();

    // The page's own title, its one heading (UI-11), where it was an <h2> inside the card's <h2>.
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Badilisha taarifa za Asha",
    );
    expect(box("Jina kamili").value).toBe("Asha Mfano");
    expect(box("Jina la kuitwa").value).toBe("Asha");
    expect(box("Kazi").value).toBe("Muuzji");
    expect(box("Siku ya kwanza").value).toBe("2026-11-03");
    expect(box("Simu").value).toBe("0712 345 678");
    expect(box("Sababu").value).toBe("");
    expect(document.activeElement).toBe(box("Jina kamili"));
    // Hifadhi alone: the arrow is the way out (Jack's yes to the screens).
    expect(screen.queryByRole("button", { name: "Ghairi" })).toBeNull();
  });

  it("sends only the boxes that changed, with the version it read and why, and goes back to Asha's page, which shows her as saved with its line (the card's third Done when)", async () => {
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
    cameFromHerPage();
    // One store for both pages, as the app has.
    const store = makeQueryClient();
    const { unmount } = render(
      <QueryClientProvider client={store}>
        <EditWorkerScreen id={ASHA.id} />
      </QueryClientProvider>,
    );
    await screen.findByLabelText("Jina kamili");

    typeInto(box("Kazi"), "Muuzaji ");
    typeInto(box("Simu"), "0754 000 111");
    typeInto(box("Sababu"), ` ${WHY} `);
    fireEvent.click(button("Hifadhi"));

    // Back where the arrow goes: her page, which the person came from.
    expect(await landedWith()).toBe("Taarifa za Asha zimehifadhiwa.");
    expect(router.back).toHaveBeenCalledOnce();
    // The spaces around each taken off, as the server keeps them; the phone as typed, which the server cleans.
    expect(await fixesSent()).toEqual([
      { version: 1, reason: WHY, job_title: "Muuzaji", phone: "0754 000 111" },
    ]);

    // Her page, as the move lands on it: as saved, the line on Taarifa zake, and the keyboard on it.
    unmount();
    render(
      <QueryClientProvider client={store}>
        <WorkerScreen id={ASHA.id} />
      </QueryClientProvider>,
    );
    const line = await screen.findByText("Taarifa za Asha zimehifadhiwa.");
    expect(
      screen.getByRole("region", { name: "Taarifa zake" }).contains(line),
    ).toBe(true);
    expect(await screen.findByText("0754 000 111")).toBeTruthy();
    expect(screen.getByText("Muuzaji")).toBeTruthy();
    await waitFor(() =>
      expect(document.activeElement?.textContent).toBe(
        "Taarifa za Asha zimehifadhiwa.",
      ),
    );
  });

  it("goes to Asha's page in its own place when opened from a bookmark, so the arrow there leads to the list", async () => {
    const server = theServerHas(ASHA);
    answer("PATCH", ASHAS, () => {
      const fixed = { ...ASHA, job_title: "Muuzaji", version: 2 };
      server.now(fixed);
      return Response.json(fixed);
    });
    // No page of the app before this one.
    vi.spyOn(window.history, "length", "get").mockReturnValue(1);
    await openTheFix();

    typeInto(box("Kazi"), "Muuzaji");
    typeInto(box("Sababu"), WHY);
    fireEvent.click(button("Hifadhi"));

    expect(await landedWith()).toBe("Taarifa za Asha zimehifadhiwa.");
    expect(router.replace).toHaveBeenCalledWith(workerPage(ASHA.id));
    expect(router.back).not.toHaveBeenCalled();
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

    expect(await landedWith()).toBe("Taarifa za Asha zimehifadhiwa.");
    expect(await fixesSent()).toEqual([{ version: 1, reason: WHY, phone: "" }]);
  });

  it("goes back saying nothing was changed, and sends nothing, when every box is as it was", async () => {
    theServerHas(ASHA);
    await openTheFix();

    // Typed back as it was, spaces and all.
    typeInto(box("Kazi"), " Muuzji ");
    fireEvent.click(button("Hifadhi"));

    expect(await landedWith()).toBe("Hukubadilisha chochote.");
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

  it("says beside Simu that a phone someone logs in by can't be taken off (PPL-10's review)", async () => {
    // Asha has a password and no email: her phone is her only way in.
    theServerHas({ ...ASHA, phone: "+255712345678" });
    answer(
      "PATCH",
      ASHAS,
      refusal(400, "invalid", {}, { phone: ["phone.needed_to_log_in"] }),
    );
    await openTheFix();

    typeInto(box("Simu"), "");
    typeInto(box("Sababu"), WHY);
    fireEvent.click(button("Hifadhi"));

    await waitFor(() =>
      expect(errorOf(box("Simu"))).toBe(
        "Mtu huyu anaingia kwa namba hii. Weka namba nyingine badala ya kuiondoa.",
      ),
    );
  });

  it("shows who may above the buttons, and keeps the boxes and the page", async () => {
    theServerHas(ASHA);
    answer("PATCH", ASHAS, refusal(400, "staff.superuser_only"));
    await openTheFix();

    typeInto(box("Kazi"), "Muuzaji");
    typeInto(box("Sababu"), WHY);
    fireEvent.click(button("Hifadhi"));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Hali ya kazi, taarifa, malipo, vyeo na ruhusa za mtu huyu zinabadilishwa na msimamizi wa mfumo tu.",
    );
    expect(box("Kazi").value).toBe("Muuzaji");
    expect(router.back).not.toHaveBeenCalled();
    expect(router.replace).not.toHaveBeenCalled();
    expect(peekNews()).toBeNull();
  });

  it("after someone else's fix, goes back to Asha's page, which says so and shows her as she is now (PPL-10's third Done when)", async () => {
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
    const store = makeQueryClient();
    const { unmount } = render(
      <QueryClientProvider client={store}>
        <EditWorkerScreen id={ASHA.id} />
      </QueryClientProvider>,
    );
    await screen.findByLabelText("Jina kamili");

    typeInto(box("Kazi"), "Muuzaji");
    typeInto(box("Sababu"), WHY);
    fireEvent.click(button("Hifadhi"));

    const changed =
      "Taarifa za Asha zimebadilika tangu ulipozifungua. Hizi ndizo taarifa zake sasa: jaribu tena kama bado kuna cha kurekebisha.";
    expect(await landedWith()).toBe(changed);
    // Her page reads her again: Baba's fix on it, nothing of Meneja's.
    unmount();
    render(
      <QueryClientProvider client={store}>
        <WorkerScreen id={ASHA.id} />
      </QueryClientProvider>,
    );
    expect(await screen.findByText(changed)).toBeTruthy();
    expect(await screen.findByText("Fundi")).toBeTruthy();
  });

  it("switches Hifadhi off while there is no network, so nothing waits unsent while it looks done", async () => {
    theServerHas(ASHA);
    const store = makeQueryClient();
    // Asha read once, so the page has her when the network goes.
    store.setQueryData([...WORKERS, ASHA.id], ASHA);
    // The network gone as the form opens, which reads it as it draws (useOnline). No "offline" event: TanStack's own
    // network watcher would hear it and pause every later test's reads (worker-actions.test.tsx).
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    render(
      <QueryClientProvider client={store}>
        <EditWorkerScreen id={ASHA.id} />
      </QueryClientProvider>,
    );

    expect(((await findButton("Hifadhi")) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("switches Hifadhi off while the fix is on its way, so a second tap sends nothing", async () => {
    theServerHas(ASHA);
    // The server holds its answer until the test lets it go.
    let answerNow: () => void = () => undefined;
    answer(
      "PATCH",
      ASHAS,
      () =>
        new Promise<Response>((resolve) => {
          answerNow = () =>
            resolve(
              Response.json({ ...ASHA, job_title: "Muuzaji", version: 2 }),
            );
        }),
    );
    await openTheFix();

    typeInto(box("Kazi"), "Muuzaji");
    typeInto(box("Sababu"), WHY);
    fireEvent.click(button("Hifadhi"));
    await waitFor(() =>
      expect((button("Hifadhi") as HTMLButtonElement).disabled).toBe(true),
    );
    fireEvent.click(button("Hifadhi"));
    answerNow();

    expect(await landedWith()).toBe("Taarifa za Asha zimehifadhiwa.");
    expect(await fixesSent()).toHaveLength(1);
  });

  it("starts afresh on Baraka when the address moves from Asha's, so her boxes never go to him", async () => {
    // The browser's back and forward move the address while the page stays: the same screen, another worker.
    theServerHas(ASHA);
    const baraka = worker({
      full_name: "Baraka Mfano",
      display_name: "Baraka",
      job_title: "Mpakiaji",
    });
    answer("GET", `${STAFF}${baraka.id}/`, { status: 200, body: baraka });
    const { rerender } = render(<EditWorkerScreen id={ASHA.id} />);
    await screen.findByLabelText("Jina kamili");
    typeInto(box("Kazi"), "Muuzaji");

    rerender(<EditWorkerScreen id={baraka.id} />);

    await screen.findByRole("heading", {
      level: 1,
      name: "Badilisha taarifa za Baraka",
    });
    await waitFor(() => expect(box("Kazi").value).toBe("Mpakiaji"));
    expect(box("Jina kamili").value).toBe("Baraka Mfano");
    expect(await fixesSent()).toEqual([]);
  });

  it("has no Ghairi: the arrow goes back to Asha's page, with nothing sent and no line (Jack's yes to the screens)", async () => {
    theServerHas(ASHA);
    cameFromHerPage();
    await openTheFix();

    typeInto(box("Kazi"), "Muuzaji");
    expect(screen.queryByRole("button", { name: "Ghairi" })).toBeNull();
    fireEvent.click(button("Rudi ulipotoka"));

    expect(router.back).toHaveBeenCalledOnce();
    expect(await fixesSent()).toEqual([]);
    expect(peekNews()).toBeNull();
  });

  it("opens on Asha's own read, never the list's older copy, as the version it sends decides whose fix wins", async () => {
    // The list, read before Baba fixed her, still holds version 1; the server holds his fix, version 2.
    const store = makeQueryClient();
    store.setQueryData(WORKERS, [ASHA]);
    theServerHas({ ...ASHA, job_title: "Fundi", version: 2 });
    answer("PATCH", ASHAS, () =>
      Response.json({ ...ASHA, job_title: "Muuzaji", version: 3 }),
    );
    render(
      <QueryClientProvider client={store}>
        <EditWorkerScreen id={ASHA.id} />
      </QueryClientProvider>,
    );

    // The title comes from the list's copy at once; the boxes wait for her own read.
    expect(screen.getByText("Subiri kidogo…")).toBeTruthy();
    expect(screen.queryByLabelText("Kazi")).toBeNull();
    await waitFor(() => expect(box("Kazi").value).toBe("Fundi"));
    typeInto(box("Kazi"), "Muuzaji");
    typeInto(box("Sababu"), WHY);
    fireEvent.click(button("Hifadhi"));

    await landedWith();
    expect(await fixesSent()).toEqual([
      { version: 2, reason: WHY, job_title: "Muuzaji" },
    ]);
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
    expect(await landedWith()).toMatch(
      /^Taarifa za Asha zimebadilika tangu ulipozifungua/,
    );
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
    expect(await landedWith()).toBe("Taarifa za Asha zimehifadhiwa.");
    expect(await fixesSent()).toEqual([
      { version: 1, reason: WHY, started_on: "2025-11-03" },
    ]);
  });

  it("asks nothing when a long-time worker's first day moves by a few days (PPL-10's review)", async () => {
    // Juma started in March 2024; the owner finds it was the 4th, not the 2nd. Far from today, but no slip.
    const juma = worker({ started_on: "2024-03-02" });
    theServerHas(juma);
    answer("PATCH", `${STAFF}${juma.id}/`, () =>
      Response.json({ ...juma, started_on: "2024-03-04", version: 2 }),
    );
    await openTheFix(juma.id);

    typeInto(box("Siku ya kwanza"), "2024-03-04");
    typeInto(box("Sababu"), WHY);
    fireEvent.click(button("Hifadhi"));

    expect(await landedWith()).toBe("Taarifa za Juma zimehifadhiwa.");
    expect(await fixesSent()).toEqual([
      { version: 1, reason: WHY, started_on: "2024-03-04" },
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

    expect(await landedWith()).toBe("Taarifa za Asha zimehifadhiwa.");
    expect(await fixesSent()).toEqual([
      { version: 1, reason: WHY, job_title: "Mpakiaji" },
    ]);
  });
});

describe("a page that can't act (UI-11)", () => {
  it("says why for a worker who left, whose job keeps what it said then, and offers no form", async () => {
    const hamisi = worker({
      display_name: "Hamisi",
      status: "left",
      left_on: "2026-11-10",
    });
    theServerHas(hamisi);

    render(<EditWorkerScreen id={hamisi.id} />);

    expect(await screen.findByText("Mtu huyu ameshaacha kazi.")).toBeTruthy();
    expect(screen.queryByLabelText("Jina kamili")).toBeNull();
  });

  it("says why on one's own job, and offers no form", async () => {
    const neema = worker({ id: MANAGER.staff.id, display_name: "Neema" });
    theServerHas(neema);

    render(<EditWorkerScreen id={neema.id} />);

    expect(
      await screen.findByText(
        "Huwezi kubadilisha hali yako ya kazi, taarifa zako, malipo yako, wala vyeo na ruhusa zako mwenyewe.",
      ),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Jina kamili")).toBeNull();
  });

  it("says no worker was chosen, and asks nothing, with no id in the address", async () => {
    answer("GET", ME, { status: 200, body: MANAGER });

    render(<EditWorkerScreen id={null} />);

    expect(
      await screen.findByText(
        "Hakuna mfanyakazi aliyechaguliwa. Rudi kwenye orodha ya wafanyakazi.",
      ),
    ).toBeTruthy();
    expect(sent.filter((request) => request.url.includes(STAFF))).toEqual([]);
  });

  it("shows the server's refusal of the worker's read, and no form", async () => {
    // Someone without staff.manage on the whole shop, who came by the address.
    answer("GET", ME, { status: 200, body: MANAGER });
    answer("GET", ASHAS, refusal(403, "permission_denied"));

    render(<EditWorkerScreen id={ASHA.id} />);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Huna ruhusa ya kufanya hili.",
    );
    expect(screen.queryByLabelText("Jina kamili")).toBeNull();
  });
});
