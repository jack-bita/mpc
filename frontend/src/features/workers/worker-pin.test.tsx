// worker-pin.test.tsx — Weka PIN on a worker's page (PPL-12): the Kuingia card that says whether the worker has a PIN,
// the two hidden boxes the worker types their own PIN into, two that differ said at once, the server's strength codes
// beside the box and who-may codes above the buttons, the line after, who sees the button, the demo, offline, Ghairi,
// one form at a time on the page, nothing of the PIN kept in the store, and the line under Ongeza kazi once the worker
// has a PIN.
import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeQueryClient } from "@/api/query-client";
import type { components } from "@/api/schema";
import { MESSAGES } from "@/i18n/language";
import { DAWA } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { render } from "@/test/render";
import {
  MANAGER,
  role,
  ROLES_ROUTE,
  rolesPage,
  SHOP_ROLES,
  STAFF,
  worker,
} from "@/test/workers";

import { WorkerScreen } from "./worker-page";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

type Worker = components["schemas"]["Staff"];

const ME = "/api/auth/me/";
const DEMO_OPEN = "/api/devices/v1/demo/open/";

afterEach(() => {
  // A test that takes the network away puts it back after (navigator.onLine's spy).
  vi.restoreAllMocks();
});

/** Asha, a seller on Dawa, working, with no PIN yet: no tile on the shop's laptops. */
const ASHA = worker({
  full_name: "Asha Mfano",
  display_name: "Asha",
  started_on: "2026-11-03",
  roles: [role("seller", DAWA.id)],
});

/** Where Weka PIN sends Asha's. */
const PIN_ROUTE = `${STAFF}${ASHA.id}/pin/`;

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

/** A server error code's own sentence in Swahili, as the page shows it. */
function sentence(code: string): string {
  let found: unknown = MESSAGES.sw.errors;
  for (const part of code.split("."))
    found = (found as Record<string, unknown>)[part];
  if (typeof found !== "string") throw new Error(`no sentence for ${code}`);
  return found;
}

/** What the app sent to set a PIN, as the server would read it. */
async function pinsSent(): Promise<unknown[]> {
  return Promise.all(
    sent
      .filter((request) => request.url.endsWith("/pin/"))
      .map((request) => request.json()),
  );
}

/** The error beside a box: the one its aria-describedby names (field.tsx). */
function errorOf(box: HTMLElement): string {
  const ids = box.getAttribute("aria-describedby")?.split(" ") ?? [];
  const error = ids.find((id) => id.endsWith("-error"));
  return error ? (document.getElementById(error)?.textContent ?? "") : "";
}

const button = (name: string) =>
  screen.getByRole("button", { name }) as HTMLButtonElement;
const findButton = (name: string) => screen.findByRole("button", { name });
const newPin = () => screen.getByLabelText("PIN mpya") as HTMLInputElement;
const again = () => screen.getByLabelText("Andika tena") as HTMLInputElement;

/** Asha types her PIN in both boxes, as she would on the owner's phone. */
function ashaTypes(first: string, second: string = first) {
  fireEvent.change(newPin(), { target: { value: first } });
  fireEvent.change(again(), { target: { value: second } });
}

describe("the Kuingia card", () => {
  it("says whether the worker has a PIN, so the owner sees who has no tile yet", async () => {
    theServerHas(ASHA);
    const { unmount } = render(<WorkerScreen id={ASHA.id} />);

    await screen.findByRole("heading", { name: "Kuingia" });
    expect(screen.getByText("Haijawekwa")).toBeTruthy();
    unmount();

    const withPin = { ...ASHA, has_pin: true };
    theServerHas(withPin);
    render(<WorkerScreen id={withPin.id} />);
    expect(await screen.findByText("Imewekwa")).toBeTruthy();
  });

  it("offers Weka PIN to a worker working or suspended, never to one who left nor on one's own page", async () => {
    theServerHas({ ...ASHA, status: "suspended" });
    const { unmount } = render(<WorkerScreen id={ASHA.id} />);
    await findButton("Weka PIN");
    unmount();

    const left = worker({
      display_name: "Hamisi",
      status: "left",
      left_on: "2026-11-10",
    });
    theServerHas(left);
    const second = render(<WorkerScreen id={left.id} />);
    await findButton("Mwajiri tena");
    expect(screen.queryByRole("button", { name: "Weka PIN" })).toBeNull();
    second.unmount();

    // Nobody sets their own here (pin.own): the status buttons' line already says why.
    const own = { ...ASHA, id: MANAGER.staff.id, display_name: "Neema" };
    theServerHas(own);
    render(<WorkerScreen id={own.id} />);
    await screen.findByText(sentence("staff.own"));
    expect(screen.queryByRole("button", { name: "Weka PIN" })).toBeNull();
  });
});

describe("Weka PIN", () => {
  it("sets Asha's PIN as she types it twice, says what follows, and shows she has one (Done when #1)", async () => {
    const server = theServerHas(ASHA);
    answer("POST", PIN_ROUTE, () => {
      const changed = { ...ASHA, has_pin: true };
      server.now(changed);
      return Response.json(changed);
    });
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Weka PIN"));
    // Both hidden, with the phone's number pad: the owner stands beside her, and a PIN is four digits. Each a box for a
    // new secret, so the phone never offers the owner's own saved password to her (PPL-12's review).
    for (const box of [newPin(), again()]) {
      expect(box.type).toBe("password");
      expect(box.inputMode).toBe("numeric");
      expect(box.autocomplete).toBe("new-password");
    }
    ashaTypes("4829");
    fireEvent.click(button("Hifadhi"));

    // The whole line: a laptop with no network keeps its lock and the old PIN until it syncs (src/offline/pin.ts), so
    // "now" is promised only where there is a network (PPL-12's review).
    const done = await screen.findByText(
      "PIN ya Asha imewekwa. Kila kompyuta ya duka itamwonyesha ikishasawazisha. Kwenye kompyuta yenye mtandao, kifungo chake kimeondoka na PIN yake ya zamani haifanyi kazi tena; isiyo na mtandao itajua ikishasawazisha.",
    );
    // The keyboard goes to the line, as the button that opened the form may be gone.
    expect(done.closest("[tabindex='-1']")).toBe(document.activeElement);
    expect(await pinsSent()).toEqual([{ pin: "4829" }]);
    expect(screen.getByText("Imewekwa")).toBeTruthy();
    // The boxes are gone with the form: nothing of the PIN stays on the page.
    expect(screen.queryByLabelText("PIN mpya")).toBeNull();
  });

  it("says at once when the two differ, beside Andika tena, and sends nothing", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Weka PIN"));
    ashaTypes("4829", "4828");
    fireEvent.click(button("Hifadhi"));

    expect(errorOf(again())).toBe("PIN hizi hazifanani.");
    expect(await pinsSent()).toEqual([]);
  });

  it("asks for a PIN in the first box before anything is sent", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Weka PIN"));
    fireEvent.click(button("Hifadhi"));

    expect(errorOf(newPin())).toBe(sentence("blank"));
    expect(await pinsSent()).toEqual([]);
  });

  it.each(["pin.not_four_digits", "pin.too_easy"])(
    "shows the server's %s beside PIN mpya",
    async (code) => {
      theServerHas(ASHA);
      answer("POST", PIN_ROUTE, refusal(400, code));
      render(<WorkerScreen id={ASHA.id} />);

      fireEvent.click(await findButton("Weka PIN"));
      ashaTypes("1234");
      fireEvent.click(button("Hifadhi"));

      await waitFor(() => expect(errorOf(newPin())).toBe(sentence(code)));
      expect(screen.queryByRole("alert")).toBeNull();
    },
  );

  it.each([
    "pin.own",
    "pin.superuser_only",
    "pin.more_keys",
    "staff.left",
    "demo.logins_fixed",
  ])("shows who-may's %s above the buttons", async (code) => {
    theServerHas(ASHA);
    answer("POST", PIN_ROUTE, refusal(400, code));
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Weka PIN"));
    ashaTypes("4829");
    fireEvent.click(button("Hifadhi"));

    expect((await screen.findByRole("alert")).textContent).toContain(
      sentence(code),
    );
  });

  it("keeps nothing of the PIN in the store of server answers once it is sent", async () => {
    // The store is shared by everyone on the phone (UI-4): a PIN kept there would outlive the form (UI-5).
    const store = makeQueryClient();
    theServerHas(ASHA);
    answer("POST", PIN_ROUTE, refusal(400, "pin.too_easy"));
    render(
      <QueryClientProvider client={store}>
        <WorkerScreen id={ASHA.id} />
      </QueryClientProvider>,
    );

    fireEvent.click(await findButton("Weka PIN"));
    ashaTypes("1111");
    fireEvent.click(button("Hifadhi"));
    await waitFor(() => expect(errorOf(newPin())).not.toBe(""));
    fireEvent.click(button("Ghairi"));

    await waitFor(() =>
      expect(
        JSON.stringify(
          store
            .getMutationCache()
            .getAll()
            .map((change) => change.state.variables),
        ),
      ).not.toContain("1111"),
    );
  });

  it("keeps nothing of the PIN in the store once it is set, either (PPL-12's review)", async () => {
    // The path most PINs take: the form closes on the server's yes, and the change is let go of at once (gcTime: 0).
    const store = makeQueryClient();
    theServerHas(ASHA);
    answer("POST", PIN_ROUTE, () => Response.json({ ...ASHA, has_pin: true }));
    render(
      <QueryClientProvider client={store}>
        <WorkerScreen id={ASHA.id} />
      </QueryClientProvider>,
    );

    fireEvent.click(await findButton("Weka PIN"));
    ashaTypes("4829");
    fireEvent.click(button("Hifadhi"));
    await screen.findByText(/^PIN ya Asha imewekwa\./);

    await waitFor(() => expect(store.getMutationCache().getAll()).toEqual([]));
  });

  it("switches Hifadhi off while there is no network", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);

    const weka = await findButton("Weka PIN");
    // No "offline" event: TanStack's own network watcher would pause every later test's reads (worker-actions.test).
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    fireEvent.click(weka);

    expect(button("Hifadhi").disabled).toBe(true);
  });

  it("gives the keyboard back to Weka PIN on Ghairi, and keeps one form open on the page at a time", async () => {
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Weka PIN"));
    // While it is open, the other cards' buttons hide: one Hifadhi and one Ghairi on the page (PPL-8's review).
    for (const name of ["Simamisha", "Ongeza kazi", "Weka PIN"])
      expect(screen.queryByRole("button", { name })).toBeNull();
    fireEvent.click(button("Ghairi"));

    await waitFor(() =>
      expect(document.activeElement).toBe(button("Weka PIN")),
    );
    expect(button("Simamisha")).toBeTruthy();
    expect(button("Ongeza kazi")).toBeTruthy();
  });
});

describe("on the demo", () => {
  it("keeps Weka PIN off, with the line saying why (Done when #5)", async () => {
    theServerHas(ASHA);
    answer("GET", DEMO_OPEN, { status: 200, body: { open: true } });
    render(<WorkerScreen id={ASHA.id} />);

    await waitFor(() => expect(button("Weka PIN").disabled).toBe(true));
    expect(screen.getByText(sentence("demo.logins_fixed"))).toBeTruthy();
  });

  it("leaves Weka PIN on where the server says it is no demo", async () => {
    theServerHas(ASHA);
    answer("GET", DEMO_OPEN, { status: 200, body: { open: false } });
    render(<WorkerScreen id={ASHA.id} />);

    await waitFor(() =>
      expect(sent.some((request) => request.url.endsWith(DEMO_OPEN))).toBe(
        true,
      ),
    );
    expect(button("Weka PIN").disabled).toBe(false);
    expect(screen.queryByText(sentence("demo.logins_fixed"))).toBeNull();
  });
});

describe("Ongeza kazi, once the worker has a PIN", () => {
  it("says to set a fresh PIN after a big role or key, as whoever set the old one knows it", async () => {
    answer("GET", ROLES_ROUTE, { status: 200, body: rolesPage(SHOP_ROLES) });
    theServerHas({ ...ASHA, has_pin: true });
    const { unmount } = render(<WorkerScreen id={ASHA.id} />);

    fireEvent.click(await findButton("Ongeza kazi"));
    expect(
      screen.getByText(
        "Asha ana PIN tayari. Kama mtu mwingine ndiye aliyeiweka na unampa cheo au ruhusa kubwa, baada ya hapa mwekee PIN mpya wewe mwenyewe.",
      ),
    ).toBeTruthy();
    unmount();

    // No PIN, nothing to say.
    theServerHas(ASHA);
    render(<WorkerScreen id={ASHA.id} />);
    fireEvent.click(await findButton("Ongeza kazi"));
    expect(screen.queryByText(/ana PIN tayari/)).toBeNull();
  });
});
