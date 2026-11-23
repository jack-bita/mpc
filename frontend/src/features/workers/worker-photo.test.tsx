// worker-photo.test.tsx — Picha on a worker's page (PPL-9): the face, or that there is none; Piga picha, the phone's own
// camera, and Chagua picha, its gallery; the photo read and shrunk on the phone, shown in a sheet, and sent whole only
// by Hifadhi, with an id of its own; one that can't be read; the refusals; who sees the buttons; the demo, where it
// shows and nothing is sent; offline; Ghairi; and nothing of it kept once the sheet is gone.
//
// The tests' browser (jsdom) opens no camera or gallery, and can read no photo: a test hands the file box a file, as
// the phone would, and the shrinking is a stand-in (shrink-photo.test.ts tests it; e2e/workers.spec.ts, in real
// Chromium, the reading and the drawing).
import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import type { components } from "@/api/schema";
import { MESSAGES } from "@/i18n/language";
import { shrinkFile } from "@/lib/shrink-photo";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import { MANAGER, STAFF, worker } from "@/test/workers";

import { WorkerScreen } from "./worker-page";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);
vi.mock("@/lib/shrink-photo", () => ({ shrinkFile: vi.fn() }));

type Worker = components["schemas"]["Staff"];

const ME = "/api/auth/me/";
const DEMO_OPEN = "/api/devices/v1/demo/open/";

/** Asha, working, with no photo yet. */
const ASHA = worker({ full_name: "Asha Mfano", display_name: "Asha" });
/** The photo she has in some tests. */
const SHOWN = "019a8400-0000-7000-8000-000000000001";
const PHOTO_ROUTE = `${STAFF}${ASHA.id}/photo/`;

/** What the phone's camera or gallery hands over, some megabytes of it, and the small JPEG it becomes. */
const FROM_THE_PHONE = new File(["a phone's own photo"], "IMG_0001.jpg", {
  type: "image/jpeg",
});
const SMALL_BYTES = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3]);
const SMALL = new Blob([SMALL_BYTES], { type: "image/jpeg" });

beforeEach(() => {
  vi.mocked(shrinkFile).mockResolvedValue(SMALL);
  // jsdom has no addresses for a photo in memory: a pretend one, freed as the sheet closes.
  URL.createObjectURL = vi.fn(() => "blob:asha");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  // A test that takes the network away puts it back after (navigator.onLine's spy).
  vi.restoreAllMocks();
  vi.mocked(shrinkFile).mockReset();
  Reflect.deleteProperty(URL, "createObjectURL");
  Reflect.deleteProperty(URL, "revokeObjectURL");
});

/** The manager is logged in, and the server holds `start`; `now` changes what it answers from then on. */
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

/** The server keeps each photo sent, and Asha shows it from then on, as the route does. */
function theServerKeepsPhotos() {
  const server = theServerHas(ASHA);
  answer("PUT", PHOTO_ROUTE, (request) => {
    const changed = {
      ...ASHA,
      photo: new URL(request.url).searchParams.get("photo"),
    };
    server.now(changed);
    return Response.json(changed);
  });
}

/** A server error code's own sentence in Swahili, as the page shows it. */
function sentence(code: string): string {
  let found: unknown = MESSAGES.sw.errors;
  for (const part of code.split("."))
    found = (found as Record<string, unknown>)[part];
  if (typeof found !== "string") throw new Error(`no sentence for ${code}`);
  return found;
}

/** The photos sent: their own ids, as the address carries them, their type and their bytes. */
async function photosSent() {
  return Promise.all(
    sent
      .filter((request) => request.method === "PUT")
      .map(async (request) => ({
        id: new URL(request.url).searchParams.get("photo"),
        type: request.headers.get("Content-Type"),
        bytes: new Uint8Array(await request.arrayBuffer()),
      })),
  );
}

const button = (name: string) =>
  screen.getByRole("button", { name }) as HTMLButtonElement;
const card = () => screen.getByRole("region", { name: "Picha" });
/** A line on the card, once the sheet is gone: while it is open, the page behind it is shut off. */
const onTheCard = (line: string) =>
  waitFor(() => within(card()).getByText(line));
const face = (name: string) =>
  screen.getByRole("img", { name }) as HTMLImageElement;
/** A button inside the open sheet: Hifadhi, its main one, or Ghairi. */
const sheetButton = (name: string) =>
  within(screen.getByRole("dialog")).getByRole("button", {
    name,
  }) as HTMLButtonElement;

/** The hidden file box behind a button: the phone's camera (`capture`), or its gallery. */
function fileBox(way: "Piga picha" | "Chagua picha"): HTMLInputElement {
  const box = document.querySelector<HTMLInputElement>(
    way === "Piga picha"
      ? 'input[type="file"][capture]'
      : 'input[type="file"]:not([capture])',
  );
  if (box === null) throw new Error(`no file box behind ${way}`);
  return box;
}

/** The manager taps a button and the phone hands a photo over. */
function pick(way: "Piga picha" | "Chagua picha", file: File = FROM_THE_PHONE) {
  const tapped = button(way);
  tapped.focus();
  fireEvent.click(tapped);
  fireEvent.change(fileBox(way), { target: { files: [file] } });
}

/** The page open on Asha, with a photo picked and shrunk, shown in the sheet. */
async function ashaPicked(way: "Piga picha" | "Chagua picha" = "Piga picha") {
  await screen.findByRole("button", { name: way });
  pick(way);
  await screen.findByRole("img", {
    name: "Picha mpya ya Asha, bado haijahifadhiwa",
  });
}

describe("the Picha card", () => {
  it("says there is no photo yet, at the top of the page", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);

    await screen.findByRole("heading", { name: "Picha" });
    expect(within(card()).getByText("Hakuna picha")).toBeTruthy();
    expect(within(card()).queryByRole("img")).toBeNull();
    expect(screen.getAllByRole("heading", { level: 2 })[0]?.textContent).toBe(
      "Picha",
    );
  });

  it("shows the worker's face, opened from the photos' own route", async () => {
    theServerHas({ ...ASHA, photo: SHOWN });
    render(<WorkerScreen id={ASHA.id} />);

    await screen.findByRole("img", { name: "Picha ya Asha" });
    expect(new URL(face("Picha ya Asha").src).pathname).toBe(
      `/api/v1/control/attachments/${SHOWN}/file/`,
    );
    expect(screen.queryByText("Hakuna picha")).toBeNull();
  });

  it("says so when the photo doesn't open, and shows the next one all the same", async () => {
    const server = theServerHas({ ...ASHA, photo: SHOWN });
    answer("PUT", PHOTO_ROUTE, (request) => {
      const changed = {
        ...ASHA,
        photo: new URL(request.url).searchParams.get("photo"),
      };
      server.now(changed);
      return Response.json(changed);
    });
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.error(await screen.findByRole("img", { name: "Picha ya Asha" }));

    expect(
      within(card()).getByText("Picha haikufunguka. Jaribu tena baadaye."),
    ).toBeTruthy();
    expect(within(card()).queryByRole("img")).toBeNull();

    await ashaPicked();
    fireEvent.click(sheetButton("Hifadhi"));
    expect(
      await screen.findByRole("img", { name: "Picha ya Asha" }),
    ).toBeTruthy();
  });

  it("offers both buttons to a worker working or suspended, never to one who left nor on one's own page", async () => {
    theServerHas({ ...ASHA, status: "suspended" });
    const first = render(<WorkerScreen id={ASHA.id} />);
    await screen.findByRole("button", { name: "Piga picha" });
    expect(button("Chagua picha")).toBeTruthy();
    first.unmount();

    // Her photo stays to be seen: she keeps what she was then.
    const left = worker({
      display_name: "Halima",
      status: "left",
      left_on: "2026-11-10",
      photo: SHOWN,
    });
    theServerHas(left);
    const second = render(<WorkerScreen id={left.id} />);
    await screen.findByRole("img", { name: "Picha ya Halima" });
    expect(screen.queryByRole("button", { name: "Piga picha" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Chagua picha" })).toBeNull();
    second.unmount();

    // Nobody sets their own (staff.own): Taarifa zake's line already says why.
    const own = { ...ASHA, id: MANAGER.staff.id, display_name: "Neema" };
    theServerHas(own);
    render(<WorkerScreen id={own.id} />);
    await screen.findByText(sentence("staff.own"));
    expect(screen.queryByRole("button", { name: "Piga picha" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Chagua picha" })).toBeNull();
  });
});

describe("Piga picha and Chagua picha", () => {
  it("ask the phone for its back camera, and for its gallery", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);
    await screen.findByRole("button", { name: "Piga picha" });

    // "environment": the camera on the back, as the manager photographs someone else.
    expect(fileBox("Piga picha").getAttribute("capture")).toBe("environment");
    for (const way of ["Piga picha", "Chagua picha"] as const) {
      expect(fileBox(way).accept).toBe("image/*");
      const opened = vi.spyOn(fileBox(way), "click");
      fireEvent.click(button(way));
      expect(opened).toHaveBeenCalledOnce();
    }
  });

  it.each(["Piga picha", "Chagua picha"] as const)(
    "%s: shows the photo in a sheet, and Hifadhi sends it shrunk, once (Done when #1, #2, #4)",
    async (way) => {
      theServerKeepsPhotos();
      render(<WorkerScreen id={ASHA.id} />);

      await ashaPicked(way);
      // The phone's own file was shrunk before anything else: what shows, and what goes, is the small copy.
      expect(shrinkFile).toHaveBeenCalledWith(FROM_THE_PHONE);
      const sheet = screen.getByRole("dialog", { name: "Picha ya Asha" });
      expect((within(sheet).getByRole("img") as HTMLImageElement).src).toBe(
        "blob:asha",
      );
      // Nothing sent until Hifadhi.
      expect(await photosSent()).toEqual([]);
      fireEvent.click(sheetButton("Hifadhi"));

      const done = await onTheCard("Picha ya Asha imehifadhiwa.");
      expect(screen.queryByRole("dialog")).toBeNull();
      const [photo, ...more] = await photosSent();
      expect(more).toEqual([]);
      expect(photo?.type).toBe("image/jpeg");
      expect(photo?.bytes).toEqual(SMALL_BYTES);
      // An id made on the phone, of version 7 (ADR-0007).
      expect(photo?.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-/);
      // The page shows it at once, with no second read, and the keyboard is on the line.
      expect(new URL(face("Picha ya Asha").src).pathname).toBe(
        `/api/v1/control/attachments/${photo?.id}/file/`,
      );
      await waitFor(() =>
        expect(done.closest("[tabindex='-1']")).toBe(document.activeElement),
      );
    },
  );

  it("sends the same id again after an answer that was lost, so it is one photo", async () => {
    theServerHas(ASHA);
    answer("PUT", PHOTO_ROUTE, () =>
      Promise.reject(new TypeError("no network")),
    );
    render(<WorkerScreen id={ASHA.id} />);

    await ashaPicked();
    fireEvent.click(sheetButton("Hifadhi"));
    await screen.findByRole("alert");
    answer("PUT", PHOTO_ROUTE, (request) =>
      Response.json({
        ...ASHA,
        photo: new URL(request.url).searchParams.get("photo"),
      }),
    );
    fireEvent.click(sheetButton("Hifadhi"));
    await onTheCard("Picha ya Asha imehifadhiwa.");

    const ids = (await photosSent()).map((photo) => photo.id);
    expect(ids.length).toBeGreaterThan(1);
    expect(new Set(ids).size).toBe(1);
  });

  it("gives a photo picked again an id of its own", async () => {
    theServerKeepsPhotos();
    render(<WorkerScreen id={ASHA.id} />);

    await ashaPicked("Chagua picha");
    fireEvent.click(sheetButton("Hifadhi"));
    await onTheCard("Picha ya Asha imehifadhiwa.");
    await ashaPicked("Chagua picha");
    // The last line is about the last photo: gone as a new one is picked.
    expect(screen.queryByText("Picha ya Asha imehifadhiwa.")).toBeNull();
    fireEvent.click(sheetButton("Hifadhi"));
    await onTheCard("Picha ya Asha imehifadhiwa.");

    const ids = (await photosSent()).map((photo) => photo.id);
    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
  });

  it("empties the box at each pick, so the same photo can be picked again after Ghairi", async () => {
    // A browser says nothing when the file chosen is the one already in the box. The tests' browser shows every file box
    // as empty, so what is watched is the emptying itself.
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);
    await screen.findByRole("button", { name: "Chagua picha" });
    const emptied = vi.spyOn(fileBox("Chagua picha"), "value", "set");
    pick("Chagua picha");

    expect(emptied).toHaveBeenCalledWith("");
    await screen.findByRole("dialog");
  });

  it("opens nothing when the camera or the gallery is closed with no photo", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);
    await screen.findByRole("button", { name: "Piga picha" });

    fireEvent.change(fileBox("Piga picha"), { target: { files: [] } });

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(shrinkFile).not.toHaveBeenCalled();
  });

  it("says to wait while the photo is read, with nothing to save yet", async () => {
    let ready: (photo: Blob) => void = () => {};
    vi.mocked(shrinkFile).mockReturnValue(
      new Promise((resolve) => {
        ready = resolve;
      }),
    );
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);
    await screen.findByRole("button", { name: "Piga picha" });
    pick("Piga picha");

    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByText("Subiri kidogo…")).toBeTruthy();
    expect(sheetButton("Hifadhi").disabled).toBe(true);
    ready(SMALL);
    await within(sheet).findByRole("img");
    expect(within(sheet).queryByText("Subiri kidogo…")).toBeNull();
    expect(sheetButton("Hifadhi").disabled).toBe(false);
  });

  it("says when a photo can't be read here, and sends nothing", async () => {
    // An iPhone's HEIC, on a browser that doesn't know it; or no picture at all.
    vi.mocked(shrinkFile).mockRejectedValue(new DOMException("no", "E"));
    vi.spyOn(console, "error").mockImplementation(() => {});
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);
    await screen.findByRole("button", { name: "Chagua picha" });
    pick("Chagua picha");

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Picha hii haisomeki hapa. Chagua nyingine, au piga mpya.",
    );
    expect(sheetButton("Hifadhi").disabled).toBe(true);
    expect(await photosSent()).toEqual([]);
  });

  it.each([
    "staff.own",
    "staff.superuser_only",
    "staff.more_keys",
    "demo.people_fixed",
    "demo.photos_fixed",
    "attachment.too_big",
    "attachment.not_an_image",
  ])(
    "shows the server's %s above the buttons, the photo still there",
    async (code) => {
      theServerHas(ASHA);
      answer("PUT", PHOTO_ROUTE, refusal(400, code));
      render(<WorkerScreen id={ASHA.id} />);

      await ashaPicked();
      fireEvent.click(sheetButton("Hifadhi"));

      expect((await screen.findByRole("alert")).textContent).toContain(
        sentence(code),
      );
      expect(within(screen.getByRole("dialog")).getByRole("img")).toBeTruthy();
    },
  );

  it("shows a refusal of the photo's id, which no box is about", async () => {
    theServerHas(ASHA);
    answer(
      "PUT",
      PHOTO_ROUTE,
      refusal(400, "invalid", {}, { id: ["id.taken"] }),
    );
    render(<WorkerScreen id={ASHA.id} />);

    await ashaPicked();
    fireEvent.click(sheetButton("Hifadhi"));

    expect((await screen.findByRole("alert")).textContent).toContain(
      sentence("id.taken"),
    );
  });

  it("closes and says so when the worker left meanwhile, and reads them again", async () => {
    const server = theServerHas(ASHA);
    answer("PUT", PHOTO_ROUTE, () => {
      server.now({ ...ASHA, status: "left", left_on: "2026-11-20" });
      return Response.json(refusal(400, "staff.left").body, { status: 400 });
    });
    render(<WorkerScreen id={ASHA.id} />);

    await ashaPicked();
    fireEvent.click(sheetButton("Hifadhi"));

    await onTheCard(sentence("staff.left"));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Piga picha" })).toBeNull(),
    );
  });

  it("on the demo, shows the photo and saves nothing, with one line saying why (Done when #6)", async () => {
    theServerHas(ASHA);
    answer("GET", DEMO_OPEN, { status: 200, body: { open: true } });
    render(<WorkerScreen id={ASHA.id} />);

    // Once the page knows it is the demo: Weka PIN goes off (PPL-12). Picha's two stay on, to be tried (Jack).
    await waitFor(() => expect(button("Weka PIN").disabled).toBe(true));
    expect(button("Piga picha").disabled).toBe(false);
    expect(button("Chagua picha").disabled).toBe(false);
    await ashaPicked();

    const sheet = screen.getByRole("dialog");
    expect(within(sheet).getByText(sentence("demo.photos_fixed"))).toBeTruthy();
    expect(sheetButton("Hifadhi").disabled).toBe(true);
    // Enter is the main button's too: it sends nothing either.
    fireEvent.submit(sheet.querySelector("form") as HTMLFormElement);
    expect(await photosSent()).toEqual([]);
  });

  it("switches Hifadhi off while there is no network", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);
    await screen.findByRole("button", { name: "Piga picha" });
    // No "offline" event: TanStack's own network watcher would pause every later test's reads (worker-actions.test).
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await ashaPicked();

    expect(sheetButton("Hifadhi").disabled).toBe(true);
  });

  it.each(["Piga picha", "Chagua picha"] as const)(
    "Ghairi forgets the photo, and gives the keyboard back to %s",
    async (way) => {
      theServerHas(ASHA);
      render(<WorkerScreen id={ASHA.id} />);

      await ashaPicked(way);
      // While it is open, only its two buttons can be reached.
      expect(
        screen.getAllByRole("button").map((each) => each.textContent),
      ).toEqual(["Ghairi", "Hifadhi"]);
      expect(URL.revokeObjectURL).not.toHaveBeenCalled();
      fireEvent.click(sheetButton("Ghairi"));

      await waitFor(() => expect(document.activeElement).toBe(button(way)));
      // Its place in the browser's memory is freed, and nothing was sent.
      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:asha");
      expect(await photosSent()).toEqual([]);
      expect(within(card()).getByText("Hakuna picha")).toBeTruthy();
    },
  );

  it("never shows a photo whose sheet was closed while it was read", async () => {
    let ready: (photo: Blob) => void = () => {};
    vi.mocked(shrinkFile).mockReturnValue(
      new Promise((resolve) => {
        ready = resolve;
      }),
    );
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);
    await screen.findByRole("button", { name: "Piga picha" });
    pick("Piga picha");
    await screen.findByRole("dialog");
    fireEvent.click(sheetButton("Ghairi"));
    ready(SMALL);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    // Given no place in the browser's memory, which nothing would ever free.
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });

  it("keeps nothing of the photo in the store of server answers once it is saved", async () => {
    // The store is shared by everyone on the phone (UI-4): a face kept there would outlive the sheet.
    const store = makeQueryClient();
    theServerKeepsPhotos();
    render(
      <QueryClientProvider client={store}>
        <WorkerScreen id={ASHA.id} />
      </QueryClientProvider>,
    );

    await ashaPicked();
    fireEvent.click(sheetButton("Hifadhi"));
    await onTheCard("Picha ya Asha imehifadhiwa.");

    await waitFor(() => expect(store.getMutationCache().getAll()).toEqual([]));
  });
});
