// worker-actions.test.tsx — Simamisha, Rudisha and Ameondoka on a worker's own page (PPL-6): which show for which
// status, each in its sheet (UI-10) with its reason, the last day's limits, where each refusal shows, and a worker
// someone else changed first read again. And Mwajiri tena on a worker who left (PPL-11): the boxes filled from the old
// job, what is sent, the move to the new job's page, and the old job's link to it once the person is back.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { components } from "@/api/schema";
import { DAWA } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { router } from "@/test/router";
import { MANAGER, role, STAFF, worker } from "@/test/workers";

import { WorkerScreen } from "./worker-page";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type Worker = components["schemas"]["Staff"];

const ME = "/api/auth/me/";

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
  // A test that takes the network away puts it back after (navigator.onLine's spy).
  vi.restoreAllMocks();
});

/** Asha, a seller on Dawa since 3 Nov, working. */
const ASHA = worker({
  full_name: "Asha Mfano",
  display_name: "Asha",
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

/** The route of one of the three changes, for Asha. */
const route = (action: "suspend" | "unsuspend" | "leave") =>
  `${STAFF}${ASHA.id}/${action}/`;

/** What the app sent to change a worker, as the server would read it. */
async function sentBodies(): Promise<Record<string, unknown>[]> {
  return Promise.all(
    sent
      .filter((request) => request.method === "POST")
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
const reasonBox = () => screen.getByLabelText("Sababu");
/** The line that says what happened, found on its own card, never only somewhere on the page (UI-10's review). */
const onTheCard = (card: string, line: string) =>
  waitFor(() =>
    within(screen.getByRole("region", { name: card })).getByText(line),
  );

/** The sheet open over the page, named by its title (UI-10). */
const theSheet = (name: string) => screen.getByRole("dialog", { name });
/** A button inside the open sheet: its main one, which names the action, or Ghairi. */
const sheetButton = (name: string) =>
  within(screen.getByRole("dialog")).getByRole("button", { name });
const lastDayBox = () =>
  screen.getByLabelText("Siku ya mwisho") as HTMLInputElement;

describe("the buttons on a worker's page", () => {
  it("offers Badilisha, Simamisha and Ameondoka to a working worker", async () => {
    theServerHas(ASHA);

    render(<WorkerScreen id={ASHA.id} />);

    await findButton("Simamisha");
    // A link, to its own page (UI-11).
    expect(screen.getByRole("link", { name: "Badilisha" })).toBeTruthy();
    expect(button("Ameondoka")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Rudisha" })).toBeNull();
  });

  it("offers Badilisha, Rudisha and Ameondoka to a suspended one, and only Mwajiri tena to one who left", async () => {
    const suspended = { ...ASHA, status: "suspended" as const };
    theServerHas(suspended);

    const { unmount } = render(<WorkerScreen id={ASHA.id} />);

    await findButton("Rudisha");
    // A suspended worker's details can still be fixed (02 §5, PPL-10).
    expect(screen.getByRole("link", { name: "Badilisha" })).toBeTruthy();
    expect(button("Ameondoka")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Simamisha" })).toBeNull();
    unmount();

    // Leaving is for good: a job that ended keeps what it said then, so it can't be fixed either (staff.left). A
    // worker who comes back gets a new job (PPL-11).
    const hamisi = worker({
      display_name: "Hamisi",
      status: "left",
      left_on: "2026-11-10",
    });
    theServerHas(hamisi);
    render(<WorkerScreen id={hamisi.id} />);

    await findButton("Mwajiri tena");
    expect(screen.queryByRole("link", { name: "Badilisha" })).toBeNull();
    for (const name of ["Simamisha", "Rudisha", "Ameondoka"])
      expect(screen.queryByRole("button", { name })).toBeNull();
  });

  it("suspends Asha with a reason, says so, and offers Rudisha (the card's third Done when)", async () => {
    const server = theServerHas(ASHA);
    const suspended = { ...ASHA, status: "suspended" as const };
    answer("POST", route("suspend"), () => {
      server.now(suspended);
      return Response.json(suspended);
    });
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Simamisha"));
    // A sheet over the page, its title saying what and who; the keyboard starts in Sababu.
    expect(theSheet("Simamisha Asha")).toBeTruthy();
    expect(document.activeElement).toBe(reasonBox());
    typeInto(reasonBox(), "  Hakuja siku tatu bila ruhusa ");
    // Its main button names the action (UI-10), the main green, as a suspension is undone by Rudisha.
    expect(sheetButton("Simamisha").className).not.toContain(
      "text-destructive",
    );
    fireEvent.click(sheetButton("Simamisha"));

    expect(await onTheCard("Taarifa zake", "Asha amesimamishwa.")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
    const [body] = await sentBodies();
    // The spaces around the reason off, as the server keeps it.
    expect(body).toEqual({ reason: "Hakuja siku tatu bila ruhusa" });
    await findButton("Rudisha");
    expect(
      screen.getByText("Amesimamishwa", { selector: "span" }),
    ).toBeTruthy();
    // The keyboard on the line that says what happened, as Simamisha is gone; still there once the sheet's own
    // return of it (a moment later) is over.
    await waitFor(() =>
      expect(document.activeElement?.textContent).toBe("Asha amesimamishwa."),
    );
  });

  it("brings Asha back with a reason", async () => {
    const suspended = { ...ASHA, status: "suspended" as const };
    const server = theServerHas(suspended);
    answer("POST", route("unsuspend"), () => {
      server.now(ASHA);
      return Response.json(ASHA);
    });
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Rudisha"));
    expect(theSheet("Mrudishe Asha kazini")).toBeTruthy();
    typeInto(reasonBox(), "Ameomba radhi");
    fireEvent.click(sheetButton("Mrudishe"));

    expect(
      await onTheCard("Taarifa zake", "Asha amerudishwa kazini."),
    ).toBeTruthy();
    await findButton("Simamisha");
  });

  it("marks Asha left on a last day that starts at today, with nothing after it nor before her first day", async () => {
    const server = theServerHas(ASHA);
    const left = { ...ASHA, status: "left" as const, left_on: "2026-11-18" };
    answer("POST", route("leave"), () => {
      server.now(left);
      return Response.json(left);
    });
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Ameondoka"));
    expect(theSheet("Asha ameondoka kazini")).toBeTruthy();
    expect(lastDayBox().value).toBe("2026-11-18");
    expect(lastDayBox().max).toBe("2026-11-18");
    expect(lastDayBox().min).toBe("2026-11-03");
    typeInto(reasonBox(), "Amepata kazi nyingine");
    // Red, as leaving is for good (UI-10).
    expect(sheetButton("Ameondoka").className).toContain("text-destructive");
    fireEvent.click(sheetButton("Ameondoka"));

    expect(
      await onTheCard(
        "Taarifa zake",
        "Asha ameondoka. Siku yake ya mwisho ni 18/11/2026.",
      ),
    ).toBeTruthy();
    const [body] = await sentBodies();
    expect(body).toEqual({
      reason: "Amepata kazi nyingine",
      left_on: "2026-11-18",
    });
    // Gone for good: no button is left.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Simamisha" })).toBeNull(),
    );
    expect(screen.queryByRole("button", { name: "Ameondoka" })).toBeNull();
  });

  it("says an empty reason at once, beside Sababu, and sends nothing", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Simamisha"));
    // Spaces alone are no reason, as the server says too.
    typeInto(reasonBox(), "   ");
    fireEvent.click(sheetButton("Simamisha"));

    expect(errorOf(reasonBox())).toBe("Andika sababu.");
    expect(await sentBodies()).toEqual([]);
  });

  it("says a last day ahead, or before the first day, typed by hand, and sends nothing", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Ameondoka"));
    typeInto(reasonBox(), "Amepata kazi nyingine");
    typeInto(lastDayBox(), "2026-11-19");
    fireEvent.click(sheetButton("Ameondoka"));
    expect(errorOf(lastDayBox())).toBe(
      "Siku ya mwisho ya kazi haiwezi kuwa siku ijayo.",
    );

    typeInto(lastDayBox(), "2026-11-02");
    fireEvent.click(sheetButton("Ameondoka"));
    expect(errorOf(lastDayBox())).toBe(
      "Siku ya mwisho iko kabla ya siku aliyoanza kazi.",
    );
    expect(await sentBodies()).toEqual([]);
  });

  it("shows the server's refusal of the last day beside its box, though it is the whole request's code", async () => {
    // The service checks the day too, and raises it with no field (apps/core/api/errors.py): a phone whose clock is a
    // day ahead of the shop's would send tomorrow.
    theServerHas(ASHA);
    answer("POST", route("leave"), refusal(400, "staff.left_in_future"));
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Ameondoka"));
    typeInto(reasonBox(), "Amepata kazi nyingine");
    fireEvent.click(sheetButton("Ameondoka"));

    await waitFor(() =>
      expect(errorOf(lastDayBox())).toBe(
        "Siku ya mwisho ya kazi haiwezi kuwa siku ijayo.",
      ),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the server's refusal of a last day before the first day beside its box (PPL-6's review)", async () => {
    // The phone's calendar offers nothing before the first day, but the server checks it too, by the first day it
    // holds, which another manager may have moved since the page read it (PPL-10).
    theServerHas(ASHA);
    answer("POST", route("leave"), refusal(400, "staff.left_before_start"));
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Ameondoka"));
    typeInto(reasonBox(), "Amepata kazi nyingine");
    fireEvent.click(sheetButton("Ameondoka"));

    await waitFor(() =>
      expect(errorOf(lastDayBox())).toBe(
        "Siku ya mwisho iko kabla ya siku aliyoanza kazi.",
      ),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the server's refusal of the reason beside Sababu, though it is the whole request's code (PPL-6's review)", async () => {
    // The form takes the spaces off and asks for a reason itself; the service asks again, with no field, for any
    // client that skips the form.
    theServerHas(ASHA);
    answer("POST", route("suspend"), refusal(400, "staff.reason_required"));
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Simamisha"));
    typeInto(reasonBox(), "Hakuja siku tatu");
    fireEvent.click(sheetButton("Simamisha"));

    await waitFor(() => expect(errorOf(reasonBox())).toBe("Andika sababu."));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a refusal of who may inside the sheet, as the demo's of its own people", async () => {
    // On the demo, Asha stays as the seed made her, so every visitor can log in as her (PPL-4).
    theServerHas(ASHA);
    answer("POST", route("suspend"), refusal(400, "demo.people_fixed"));
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Simamisha"));
    typeInto(reasonBox(), "Kujaribu");
    fireEvent.click(sheetButton("Simamisha"));

    expect(
      (await within(theSheet("Simamisha Asha")).findByRole("alert"))
        .textContent,
    ).toContain("Kwenye demo, wafanyakazi wa mwanzo hawabadilishwi");
    // The sheet stays open, with what was typed.
    expect((reasonBox() as HTMLInputElement).value).toBe("Kujaribu");
  });

  it("reads the worker again when someone else changed them first, and says so", async () => {
    // Another manager suspended Asha a moment before; or this phone's first send was saved and its answer lost.
    const server = theServerHas(ASHA);
    answer("POST", route("suspend"), () => {
      server.now({ ...ASHA, status: "suspended" });
      return Response.json(
        { code: "staff.not_active", message: "", fields: {}, params: {} },
        { status: 400 },
      );
    });
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Simamisha"));
    typeInto(reasonBox(), "Hakuja siku tatu");
    fireEvent.click(sheetButton("Simamisha"));

    expect(
      await screen.findByText("Mfanyakazi huyu tayari amesimamishwa."),
    ).toBeTruthy();
    // The sheet closed, and the buttons fit her as she is now.
    await findButton("Rudisha");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByLabelText("Sababu")).toBeNull();
  });

  it("reads the worker again when someone else brought them back first (PPL-6's review)", async () => {
    // Two managers tap Rudisha on Asha at once: the second phone hears she is no longer suspended.
    const suspended = { ...ASHA, status: "suspended" as const };
    const server = theServerHas(suspended);
    answer("POST", route("unsuspend"), () => {
      server.now(ASHA);
      return Response.json(
        { code: "staff.not_suspended", message: "", fields: {}, params: {} },
        { status: 400 },
      );
    });
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Rudisha"));
    typeInto(reasonBox(), "Ameomba radhi");
    fireEvent.click(sheetButton("Mrudishe"));

    expect(
      await screen.findByText("Mfanyakazi huyu hajasimamishwa."),
    ).toBeTruthy();
    await findButton("Simamisha");
    expect(screen.queryByLabelText("Sababu")).toBeNull();
  });

  it("reads the worker again when someone else marked them left first (PPL-6's review)", async () => {
    // Two managers mark Asha left at once, the likeliest race on this page: the second phone hears she already left,
    // and no button is left for her.
    const server = theServerHas(ASHA);
    answer("POST", route("leave"), () => {
      server.now({ ...ASHA, status: "left", left_on: "2026-11-18" });
      return Response.json(
        { code: "staff.left", message: "", fields: {}, params: {} },
        { status: 400 },
      );
    });
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Ameondoka"));
    typeInto(reasonBox(), "Amepata kazi nyingine");
    fireEvent.click(sheetButton("Ameondoka"));

    expect(await screen.findByText("Mtu huyu ameshaacha kazi.")).toBeTruthy();
    await screen.findByText("Ameondoka", { selector: "span" });
    expect(screen.queryByRole("button", { name: "Simamisha" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Ameondoka" })).toBeNull();
  });

  it("offers no button on one's own page, and says why", async () => {
    // Nobody changes their own job or details (PPL-4, PPL-10): Neema, logged in, opens her own page.
    const neema = worker({ id: MANAGER.staff.id, display_name: "Neema" });
    theServerHas(neema);

    render(<WorkerScreen id={neema.id} />);

    expect(
      await screen.findByText(
        "Huwezi kubadilisha hali yako ya kazi, taarifa zako, malipo yako, wala vyeo na ruhusa zako mwenyewe.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Badilisha" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Simamisha" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Ameondoka" })).toBeNull();
  });

  it("switches the sheet's main button off while there is no network, so nothing waits unsent while it looks done", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);

    const simamisha = await findButton("Simamisha");
    // The network gone as the form opens, which reads it as it draws (useOnline). No "offline" event: TanStack's own
    // network watcher would hear it and pause every later test's reads, as nothing here sends "online" back.
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    fireEvent.click(simamisha);

    expect((sheetButton("Simamisha") as HTMLButtonElement).disabled).toBe(true);
    // Ghairi stays free.
    expect((sheetButton("Ghairi") as HTMLButtonElement).disabled).toBe(false);
  });

  it("reads the worker again on Ghairi, as a send whose answer was lost may have changed them (PPL-6's review)", async () => {
    // Simamisha's answer is lost on the way back, though the server suspended Asha; the owner gives up and taps
    // Ghairi. The page must not go on saying she works, with Simamisha.
    const server = theServerHas(ASHA);
    answer("POST", route("suspend"), () => {
      server.now({ ...ASHA, status: "suspended" });
      throw new TypeError("Failed to fetch");
    });
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Simamisha"));
    typeInto(reasonBox(), "Hakuja siku tatu");
    fireEvent.click(sheetButton("Simamisha"));
    await screen.findByRole("alert");
    fireEvent.click(sheetButton("Ghairi"));

    await findButton("Rudisha");
    expect(
      screen.getByText("Amesimamishwa", { selector: "span" }),
    ).toBeTruthy();
  });

  it("closes on Ghairi, sends nothing, and gives the keyboard back to the button", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Ameondoka"));
    typeInto(reasonBox(), "Amepata kazi nyingine");
    fireEvent.click(sheetButton("Ghairi"));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByLabelText("Sababu")).toBeNull();
    await waitFor(() =>
      expect(document.activeElement).toBe(button("Ameondoka")),
    );
    expect(await sentBodies()).toEqual([]);
  });
});

/** Baraka, a seller who worked here from 2 Jan 2025 until 12 Mar 2026. */
const BARAKA = worker({
  full_name: "Baraka Mfano",
  display_name: "Baraka",
  job_title: "Muuzaji wa dawa",
  started_on: "2025-01-02",
  status: "left",
  left_on: "2026-03-12",
});

const firstDayBox = () =>
  screen.getByLabelText("Siku ya kwanza") as HTMLInputElement;

describe("Mwajiri tena", () => {
  it("opens the add's boxes filled from his old job, and today as the first day, with no full name", async () => {
    theServerHas(BARAKA);
    render(<WorkerScreen id={BARAKA.id} />);

    fireEvent.click(await findButton("Mwajiri tena"));

    expect(
      screen.getByRole("heading", { level: 2, name: "Mwajiri tena Baraka" }),
    ).toBeTruthy();
    expect(
      (screen.getByLabelText("Jina la kuitwa") as HTMLInputElement).value,
    ).toBe("Baraka");
    expect((screen.getByLabelText("Kazi") as HTMLInputElement).value).toBe(
      "Muuzaji wa dawa",
    );
    expect(firstDayBox().value).toBe("2026-11-18");
    // The person keeps his own full name: Badilisha fixes it (PPL-10).
    expect(screen.queryByLabelText("Jina kamili")).toBeNull();
  });

  it("hires him again as the same person, and opens his new job's page (the card's first Done when)", async () => {
    theServerHas(BARAKA);
    const back = worker({
      full_name: "Baraka Mfano",
      display_name: "Baraka",
      job_title: "Muuzaji",
      started_on: "2026-11-18",
    });
    answer("POST", STAFF, { status: 201, body: back });
    render(<WorkerScreen id={BARAKA.id} />);

    fireEvent.click(await findButton("Mwajiri tena"));
    typeInto(screen.getByLabelText("Kazi"), "Muuzaji");
    fireEvent.click(button("Hifadhi"));

    await waitFor(() =>
      expect(router.push).toHaveBeenCalledWith(`/workers/view/?id=${back.id}`),
    );
    const [body] = await sentBodies();
    // The old job's id, and the new job's own (ADR-0007): no full name, as he keeps his own.
    expect(body).toEqual({
      id: expect.stringMatching(/^[0-9a-f-]{36}$/),
      hire_again: BARAKA.id,
      display_name: "Baraka",
      job_title: "Muuzaji",
      started_on: "2026-11-18",
    });
  });

  it("says a first day before his last day at once, beside its box, and sends nothing", async () => {
    theServerHas(BARAKA);
    render(<WorkerScreen id={BARAKA.id} />);

    fireEvent.click(await findButton("Mwajiri tena"));
    typeInto(firstDayBox(), "2026-03-11");
    fireEvent.click(button("Hifadhi"));

    expect(errorOf(firstDayBox())).toBe(
      "Siku ya kwanza haiwezi kuwa kabla ya siku yake ya mwisho ya kazi iliyopita.",
    );
    expect(await sentBodies()).toEqual([]);
  });

  it("shows the server's refusal of the first day beside its box, as when a later job ended after it", async () => {
    theServerHas(BARAKA);
    answer(
      "POST",
      STAFF,
      refusal(400, "invalid", {}, { started_on: ["staff.back_before_left"] }),
    );
    render(<WorkerScreen id={BARAKA.id} />);

    fireEvent.click(await findButton("Mwajiri tena"));
    fireEvent.click(button("Hifadhi"));

    await waitFor(() =>
      expect(errorOf(firstDayBox())).toBe(
        "Siku ya kwanza haiwezi kuwa kabla ya siku yake ya mwisho ya kazi iliyopita.",
      ),
    );
  });

  it("says another manager hired him first, and reads the old job again, which then links to the new one", async () => {
    const server = theServerHas(BARAKA);
    const elsewhere = "019a8302-0000-7000-8000-00000000ffff";
    answer("POST", STAFF, () => {
      server.now({ ...BARAKA, hired_again_as: elsewhere });
      return Response.json(refusal(400, "staff.already_member").body, {
        status: 400,
      });
    });
    render(<WorkerScreen id={BARAKA.id} />);

    fireEvent.click(await findButton("Mwajiri tena"));
    fireEvent.click(button("Hifadhi"));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Mtu huyu tayari anafanya kazi hapa.",
    );
    fireEvent.click(button("Ghairi"));
    const link = await screen.findByRole("link", {
      name: "Fungua ukurasa wake wa sasa",
    });
    // The app is built with trailing slashes; Next.js's Link in a test drops them (text-link.test.tsx).
    expect(link.getAttribute("href")).toMatch(
      new RegExp(`^/workers/view/?\\?id=${elsewhere}$`),
    );
  });

  it("shows, once he is back, a link to his new job's page in place of the button (Jack: A)", async () => {
    const now = "019a8302-0000-7000-8000-00000000fffe";
    theServerHas({ ...BARAKA, hired_again_as: now });
    render(<WorkerScreen id={BARAKA.id} />);

    expect(await screen.findByText("Baraka amerudi kazini.")).toBeTruthy();
    const link = screen.getByRole("link", {
      name: "Fungua ukurasa wake wa sasa",
    });
    // The app is built with trailing slashes; Next.js's Link in a test drops them (text-link.test.tsx).
    expect(link.getAttribute("href")).toMatch(
      new RegExp(`^/workers/view/?\\?id=${now}$`),
    );
    expect(screen.queryByRole("button", { name: "Mwajiri tena" })).toBeNull();
  });

  it("closes on Ghairi, sends nothing, and gives the keyboard back to the button", async () => {
    theServerHas(BARAKA);
    render(<WorkerScreen id={BARAKA.id} />);

    fireEvent.click(await findButton("Mwajiri tena"));
    fireEvent.click(button("Ghairi"));

    expect(screen.queryByLabelText("Jina la kuitwa")).toBeNull();
    expect(document.activeElement).toBe(button("Mwajiri tena"));
    expect(await sentBodies()).toEqual([]);
  });
});
