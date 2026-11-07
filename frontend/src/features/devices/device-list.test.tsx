// device-list.test.tsx — the shop's devices on the manager's phone: what each card says, who sees its
// buttons, and rename, block and unblock, each refusal where the manager will see it (UI-3).
import { act, fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { setLanguage } from "@/i18n/language";
import { DAWA, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { swahiliIn } from "@/test/language";
import { render } from "@/test/render";

import type { Device } from "./confirm-device";
import { DeviceList } from "./device-list";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const DEVICES = "/api/v1/people/devices/";
const MANAGE = ["device.manage", "sale.make"];

const LAPTOP: Device = {
  id: "019a5e00-0000-7000-8000-000000000001",
  name: "Laptop Dawa",
  code: 1,
  home_side: DAWA.id,
  status: "active",
  // Seen 3 minutes before the test runs.
  last_seen_at: new Date(Date.now() - 3 * 60 * 1000).toISOString(),
  created_at: "2026-11-07T09:00:00Z",
  updated_at: null,
  version: 1,
};

const PHONE: Device = {
  id: "019a5e00-0000-7000-8000-000000000002",
  name: "Simu Vyakula",
  code: 2,
  home_side: VYAKULA.id,
  status: "blocked",
  last_seen_at: null,
  created_at: "2026-11-07T09:30:00Z",
  updated_at: "2026-11-07T10:00:00Z",
  version: 2,
};

const OWNER = whoIsHere([
  { side: DAWA, permissions: MANAGE },
  { side: VYAKULA, permissions: MANAGE },
]);

/** The list, as the server sends it: newest first, one page. */
function listAnswers(...devices: Device[]) {
  answer("GET", DEVICES, {
    status: 200,
    body: { next: null, previous: null, results: devices },
  });
}

/** One device's card, found by its name. */
async function card(name: string) {
  const item = (await screen.findByText(name)).closest("li");
  if (!item) throw new Error(`No card for ${name}`);
  return within(item);
}

/** The body of the last change sent, read from a copy. */
async function lastChange(): Promise<unknown> {
  const change = sent.filter((request) => request.method !== "GET").at(-1);
  return change?.clone().json();
}

describe("the device list", () => {
  it("shows each device's name, number, side, whether it works and when it was last seen, by number", async () => {
    listAnswers(PHONE, LAPTOP);

    render(<DeviceList me={OWNER} />);

    const laptop = await card("Laptop Dawa");
    expect(laptop.getByText("Na. 1 · Dawa")).toBeDefined();
    expect(laptop.getByText("Kinafanya kazi")).toBeDefined();
    expect(laptop.getByText("Kilionekana dakika 3 zilizopita")).toBeDefined();
    const phone = await card("Simu Vyakula");
    expect(phone.getByText("Na. 2 · Vyakula")).toBeDefined();
    expect(phone.getByText("Kimezuiwa")).toBeDefined();
    expect(phone.getByText("Hakijaonekana bado")).toBeDefined();
    // A list for every screen reader, Safari's included (device-list.tsx says why it is written out).
    expect(screen.getByRole("list").getAttribute("role")).toBe("list");
    // The first laptop first, though the server sent the newest first.
    const names = screen
      .getAllByRole("listitem")
      .map((item) => within(item).getByRole("heading").textContent);
    expect(names).toEqual(["Laptop Dawa", "Simu Vyakula"]);
  });

  it("follows the pages to the last", async () => {
    answer("GET", DEVICES, (request) => {
      const cursor = new URL(request.url).searchParams.get("cursor");
      return Response.json(
        cursor === "page2"
          ? { next: null, previous: null, results: [LAPTOP] }
          : {
              next: `http://shop.test${DEVICES}?cursor=page2`,
              previous: null,
              results: [PHONE],
            },
      );
    });

    render(<DeviceList me={OWNER} />);

    expect(await screen.findByText("Laptop Dawa")).toBeDefined();
    expect(screen.getByText("Simu Vyakula")).toBeDefined();
  });

  it("keeps the devices on screen when a refresh fails, with the reason above them", async () => {
    listAnswers(LAPTOP);
    render(<DeviceList me={OWNER} />);
    await card("Laptop Dawa");

    // The session ended meanwhile; the window comes back to the front, and the list asks again.
    answer("GET", DEVICES, refusal(403, "not_authenticated"));
    act(() => {
      window.dispatchEvent(new Event("visibilitychange"));
    });

    expect(await screen.findByText("Ingia kwanza.")).toBeDefined();
    expect(screen.getByText("Laptop Dawa")).toBeDefined();
  });

  it("says when no device is registered yet", async () => {
    listAnswers();

    render(<DeviceList me={OWNER} />);

    expect(
      await screen.findByText("Bado hakuna kifaa kilichosajiliwa."),
    ).toBeDefined();
  });

  it("shows a seller the list, and no buttons", async () => {
    // A name and when it was last seen are no secret (Jack, 2 Nov 2026).
    listAnswers(LAPTOP);

    render(
      <DeviceList
        me={whoIsHere([{ side: DAWA, permissions: ["sale.make"] }])}
      />,
    );

    const laptop = await card("Laptop Dawa");
    expect(laptop.queryAllByRole("button")).toEqual([]);
  });

  it("shows the buttons only on the devices of the sides a manager manages", async () => {
    listAnswers(LAPTOP, PHONE);

    render(
      <DeviceList
        me={whoIsHere([
          { side: DAWA, permissions: MANAGE },
          { side: VYAKULA, permissions: ["sale.make"] },
        ])}
      />,
    );

    expect(
      (await card("Laptop Dawa")).getByRole("button", { name: "Zuia" }),
    ).toBeDefined();
    expect((await card("Simu Vyakula")).queryAllByRole("button")).toEqual([]);
  });

  it("renames a device, sending the version it read", async () => {
    listAnswers(LAPTOP);
    answer("PATCH", `${DEVICES}${LAPTOP.id}/`, (request) =>
      request
        .clone()
        .json()
        .then((body: { name: string }) =>
          Response.json({ ...LAPTOP, name: body.name, version: 2 }),
        ),
    );
    render(<DeviceList me={OWNER} />);

    const laptop = await card("Laptop Dawa");
    fireEvent.click(laptop.getByRole("button", { name: "Badilisha jina" }));
    listAnswers({ ...LAPTOP, name: "Laptop ya Dawa", version: 2 });
    fireEvent.change(laptop.getByLabelText("Jina jipya"), {
      target: { value: "Laptop ya Dawa" },
    });
    fireEvent.click(laptop.getByRole("button", { name: "Hifadhi" }));

    expect(await screen.findByText("Laptop ya Dawa")).toBeDefined();
    expect(await lastChange()).toEqual({ name: "Laptop ya Dawa", version: 1 });
  });

  it("puts the keyboard in each form's box, and back on its button when it closes", async () => {
    // Laptops are keyboard first: the place mustn't fall to the page's start.
    listAnswers(LAPTOP);
    answer("POST", `${DEVICES}${LAPTOP.id}/block/`, {
      status: 200,
      body: { ...LAPTOP, status: "blocked", version: 2 },
    });
    render(<DeviceList me={OWNER} />);
    const laptop = await card("Laptop Dawa");

    fireEvent.click(laptop.getByRole("button", { name: "Badilisha jina" }));
    expect(document.activeElement).toBe(laptop.getByLabelText("Jina jipya"));
    fireEvent.click(laptop.getByRole("button", { name: "Ghairi" }));
    expect(document.activeElement).toBe(
      laptop.getByRole("button", { name: "Badilisha jina" }),
    );

    fireEvent.click(laptop.getByRole("button", { name: "Zuia" }));
    expect(document.activeElement).toBe(
      laptop.getByLabelText("Kwa nini unakizuia?"),
    );
    listAnswers({ ...LAPTOP, status: "blocked", version: 2 });
    fireEvent.change(laptop.getByLabelText("Kwa nini unakizuia?"), {
      target: { value: "Kimeibiwa" },
    });
    fireEvent.click(laptop.getByRole("button", { name: "Zuia kifaa" }));
    // Blocked, the same place now holds Fungua.
    const unblock = await laptop.findByRole("button", { name: "Fungua" });
    await vi.waitFor(() => expect(document.activeElement).toBe(unblock));
  });

  it("says when someone else renamed it meanwhile, and asks the list again", async () => {
    listAnswers(LAPTOP);
    answer(
      "PATCH",
      `${DEVICES}${LAPTOP.id}/`,
      refusal(409, "version_conflict"),
    );
    render(<DeviceList me={OWNER} />);

    const laptop = await card("Laptop Dawa");
    fireEvent.click(laptop.getByRole("button", { name: "Badilisha jina" }));
    fireEvent.click(laptop.getByRole("button", { name: "Hifadhi" }));

    expect(
      await screen.findByText(
        "Mtu mwingine amebadilisha hiki wakati huo huo. Fungua upya, kisha ujaribu tena.",
      ),
    ).toBeDefined();
    // Asked again, so the next try sends the new version.
    await vi.waitFor(() =>
      expect(sent.filter((request) => request.method === "GET").length).toBe(2),
    );
  });

  it("says a name the shop already uses above the box", async () => {
    listAnswers(LAPTOP);
    answer(
      "PATCH",
      `${DEVICES}${LAPTOP.id}/`,
      refusal(400, "device.name_taken"),
    );
    render(<DeviceList me={OWNER} />);

    const laptop = await card("Laptop Dawa");
    fireEvent.click(laptop.getByRole("button", { name: "Badilisha jina" }));
    fireEvent.click(laptop.getByRole("button", { name: "Hifadhi" }));

    expect(
      await laptop.findByText("Kifaa kingine tayari kina jina hili."),
    ).toBeDefined();
    expect(
      laptop.getByLabelText("Jina jipya").getAttribute("aria-invalid"),
    ).toBe("true");
  });

  it("blocks a device with a reason, and shows it blocked", async () => {
    listAnswers(LAPTOP);
    answer("POST", `${DEVICES}${LAPTOP.id}/block/`, {
      status: 200,
      body: { ...LAPTOP, status: "blocked", version: 2 },
    });
    render(<DeviceList me={OWNER} />);

    const laptop = await card("Laptop Dawa");
    fireEvent.click(laptop.getByRole("button", { name: "Zuia" }));
    listAnswers({ ...LAPTOP, status: "blocked", version: 2 });
    fireEvent.change(laptop.getByLabelText("Kwa nini unakizuia?"), {
      target: { value: "Kimeibiwa" },
    });
    fireEvent.click(laptop.getByRole("button", { name: "Zuia kifaa" }));

    expect(await laptop.findByText("Kimezuiwa")).toBeDefined();
    expect(laptop.getByRole("button", { name: "Fungua" })).toBeDefined();
    expect(await lastChange()).toEqual({ reason: "Kimeibiwa" });
  });

  it("says a block with no reason above the box", async () => {
    // The server refuses a blank reason with its own code (DeviceReasonSerializer).
    listAnswers(LAPTOP);
    answer(
      "POST",
      `${DEVICES}${LAPTOP.id}/block/`,
      refusal(400, "device.reason_required"),
    );
    render(<DeviceList me={OWNER} />);

    const laptop = await card("Laptop Dawa");
    fireEvent.click(laptop.getByRole("button", { name: "Zuia" }));
    fireEvent.click(laptop.getByRole("button", { name: "Zuia kifaa" }));

    expect(await laptop.findByText("Andika sababu.")).toBeDefined();
    expect(
      laptop.getByLabelText("Kwa nini unakizuia?").getAttribute("aria-invalid"),
    ).toBe("true");
  });

  it("unblocks a device with a reason", async () => {
    listAnswers(PHONE);
    answer("POST", `${DEVICES}${PHONE.id}/unblock/`, {
      status: 200,
      body: { ...PHONE, status: "active", version: 3 },
    });
    render(<DeviceList me={OWNER} />);

    const phone = await card("Simu Vyakula");
    fireEvent.click(phone.getByRole("button", { name: "Fungua" }));
    listAnswers({ ...PHONE, status: "active", version: 3 });
    fireEvent.change(phone.getByLabelText("Kwa nini unakifungua?"), {
      target: { value: "Kimepatikana" },
    });
    fireEvent.click(phone.getByRole("button", { name: "Fungua kifaa" }));

    expect(await phone.findByText("Kinafanya kazi")).toBeDefined();
    expect(await lastChange()).toEqual({ reason: "Kimepatikana" });
  });

  it("speaks English after the switch, with no Swahili left", async () => {
    setLanguage("en");
    listAnswers(LAPTOP, PHONE);
    const { container } = render(<DeviceList me={OWNER} />);

    const laptop = await card("Laptop Dawa");
    expect(laptop.getByText("Seen 3 minutes ago")).toBeDefined();
    fireEvent.click(laptop.getByRole("button", { name: "Block" }));

    expect(laptop.getByLabelText("Why are you blocking it?")).toBeDefined();
    expect(swahiliIn(container)).toEqual([]);
  });
});
