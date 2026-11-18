// worker-actions.test.tsx — Simamisha, Rudisha and Ameondoka on a worker's own page (PPL-6): which show for which
// status, each with its reason, the last day's limits, where each refusal shows, and a worker someone else changed
// first read again.
import { fireEvent, screen, waitFor } from "@testing-library/react";
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
const lastDayBox = () =>
  screen.getByLabelText("Siku ya mwisho") as HTMLInputElement;

describe("the buttons on a worker's page", () => {
  it("offers Simamisha and Ameondoka to a working worker", async () => {
    theServerHas(ASHA);

    render(<WorkerScreen id={ASHA.id} />);

    await findButton("Simamisha");
    expect(button("Ameondoka")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Rudisha" })).toBeNull();
  });

  it("offers Rudisha and Ameondoka to a suspended one, and none to one who left", async () => {
    const suspended = { ...ASHA, status: "suspended" as const };
    theServerHas(suspended);

    const { unmount } = render(<WorkerScreen id={ASHA.id} />);

    await findButton("Rudisha");
    expect(button("Ameondoka")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Simamisha" })).toBeNull();
    unmount();

    // Leaving is for good: a worker hired again comes back through Ongeza.
    const hamisi = worker({
      display_name: "Hamisi",
      status: "left",
      left_on: "2026-11-10",
    });
    theServerHas(hamisi);
    render(<WorkerScreen id={hamisi.id} />);

    await screen.findByText("Ameondoka", { selector: "span" });
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
    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe(
      "Simamisha Asha",
    );
    // The keyboard starts in Sababu, where the button was.
    expect(document.activeElement).toBe(reasonBox());
    typeInto(reasonBox(), "  Hakuja siku tatu bila ruhusa ");
    fireEvent.click(button("Hifadhi"));

    expect(await screen.findByText("Asha amesimamishwa.")).toBeTruthy();
    const [body] = await sentBodies();
    // The spaces around the reason off, as the server keeps it.
    expect(body).toEqual({ reason: "Hakuja siku tatu bila ruhusa" });
    await findButton("Rudisha");
    expect(
      screen.getByText("Amesimamishwa", { selector: "span" }),
    ).toBeTruthy();
    // The keyboard on the line that says what happened, as Simamisha is gone.
    expect(document.activeElement?.textContent).toBe("Asha amesimamishwa.");
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
    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe(
      "Mrudishe Asha kazini",
    );
    typeInto(reasonBox(), "Ameomba radhi");
    fireEvent.click(button("Hifadhi"));

    expect(await screen.findByText("Asha amerudishwa kazini.")).toBeTruthy();
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
    expect(lastDayBox().value).toBe("2026-11-18");
    expect(lastDayBox().max).toBe("2026-11-18");
    expect(lastDayBox().min).toBe("2026-11-03");
    typeInto(reasonBox(), "Amepata kazi nyingine");
    fireEvent.click(button("Hifadhi"));

    expect(
      await screen.findByText(
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
    fireEvent.click(button("Hifadhi"));

    expect(errorOf(reasonBox())).toBe("Andika sababu.");
    expect(await sentBodies()).toEqual([]);
  });

  it("says a last day ahead, or before the first day, typed by hand, and sends nothing", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Ameondoka"));
    typeInto(reasonBox(), "Amepata kazi nyingine");
    typeInto(lastDayBox(), "2026-11-19");
    fireEvent.click(button("Hifadhi"));
    expect(errorOf(lastDayBox())).toBe(
      "Siku ya mwisho ya kazi haiwezi kuwa siku ijayo.",
    );

    typeInto(lastDayBox(), "2026-11-02");
    fireEvent.click(button("Hifadhi"));
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
    fireEvent.click(button("Hifadhi"));

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
    fireEvent.click(button("Hifadhi"));

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
    fireEvent.click(button("Hifadhi"));

    await waitFor(() => expect(errorOf(reasonBox())).toBe("Andika sababu."));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a refusal of who may above the buttons, as the demo's of its own people", async () => {
    // On the demo, Asha stays as the seed made her, so every visitor can log in as her (PPL-4).
    theServerHas(ASHA);
    answer("POST", route("suspend"), refusal(400, "demo.people_fixed"));
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Simamisha"));
    typeInto(reasonBox(), "Kujaribu");
    fireEvent.click(button("Hifadhi"));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Kwenye demo, wafanyakazi wa mwanzo hawabadilishwi",
    );
    // The form stays open, with what was typed.
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
    fireEvent.click(button("Hifadhi"));

    expect(
      await screen.findByText("Mfanyakazi huyu tayari amesimamishwa."),
    ).toBeTruthy();
    // The buttons fit her as she is now.
    await findButton("Rudisha");
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
    fireEvent.click(button("Hifadhi"));

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
    fireEvent.click(button("Hifadhi"));

    expect(await screen.findByText("Mtu huyu ameshaacha kazi.")).toBeTruthy();
    await screen.findByText("Ameondoka", { selector: "span" });
    expect(screen.queryByRole("button", { name: "Simamisha" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Ameondoka" })).toBeNull();
  });

  it("offers no button on one's own page, and says why", async () => {
    // Nobody changes their own job (PPL-4): Neema, logged in, opens her own page.
    const neema = worker({ id: MANAGER.staff.id, display_name: "Neema" });
    theServerHas(neema);

    render(<WorkerScreen id={neema.id} />);

    expect(
      await screen.findByText(
        "Huwezi kubadilisha hali yako ya kazi wala taarifa zako mwenyewe.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Simamisha" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Ameondoka" })).toBeNull();
  });

  it("switches Hifadhi off while there is no network, so nothing waits unsent while it looks done", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);

    const simamisha = await findButton("Simamisha");
    // The network gone as the form opens, which reads it as it draws (useOnline). No "offline" event: TanStack's own
    // network watcher would hear it and pause every later test's reads, as nothing here sends "online" back.
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    fireEvent.click(simamisha);

    expect((button("Hifadhi") as HTMLButtonElement).disabled).toBe(true);
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
    fireEvent.click(button("Hifadhi"));
    await screen.findByRole("alert");
    fireEvent.click(button("Ghairi"));

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
    fireEvent.click(button("Ghairi"));

    expect(screen.queryByLabelText("Sababu")).toBeNull();
    expect(document.activeElement).toBe(button("Ameondoka"));
    expect(await sentBodies()).toEqual([]);
  });
});
