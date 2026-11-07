// confirm-device.test.tsx — Sajili kifaa on the manager's phone: what it sends, one device for a tap
// sent again, each refusal where the manager will fix it, and only the sides they may manage (UI-3).
import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { setLanguage } from "@/i18n/language";
import { DAWA, DAWA_LAPTOP, VYAKULA, whoIsHere } from "@/test/devices";
import { answer, refusal, sent } from "@/test/fake-server";
import { swahiliIn } from "@/test/language";
import { render } from "@/test/render";

import { DevicesScreen } from "./devices-screen";

vi.mock("@/api/client", async (importOriginal) =>
  (await import("@/test/fake-server")).withFakeServer(await importOriginal()),
);

const ME = "/api/auth/me/";
const DEVICES = "/api/v1/people/devices/";
const MANAGE = ["device.manage", "sale.make"];
const UUID7 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

beforeEach(() => {
  // The list under the form, empty: device-list.test.tsx covers it.
  answer("GET", DEVICES, {
    status: 200,
    body: { next: null, previous: null, results: [] },
  });
});

/** The device the server made, as it answers a confirm. */
const MADE = {
  id: DAWA_LAPTOP.id,
  name: "Laptop Dawa",
  code: 1,
  home_side: DAWA.id,
  status: "active",
  last_seen_at: null,
  created_at: "2026-11-07T09:00:00Z",
  updated_at: null,
  version: 1,
};

/** The owner, who holds device.manage on both sides. */
function asOwner() {
  answer("GET", ME, {
    status: 200,
    body: whoIsHere([
      { side: DAWA, permissions: MANAGE },
      { side: VYAKULA, permissions: MANAGE },
    ]),
  });
}

async function openTheForm() {
  render(<DevicesScreen />);
  fireEvent.click(await screen.findByRole("button", { name: "Sajili kifaa" }));
}

function fillIn(code: string, name: string) {
  fireEvent.change(screen.getByLabelText("Namba ya kifaa"), {
    target: { value: code },
  });
  fireEvent.change(screen.getByLabelText("Jina la kifaa"), {
    target: { value: name },
  });
}

const send = () =>
  fireEvent.click(screen.getByRole("button", { name: "Sajili" }));

/** The body of every confirm sent, in order, read from a copy, so it can be read again. */
const confirms = () =>
  Promise.all(
    sent
      .filter((request) => request.method === "POST")
      .map(
        (request) => request.clone().json() as Promise<Record<string, unknown>>,
      ),
  );

describe("Sajili kifaa", () => {
  it("sends the code as typed, the name and the side, with an id made on the phone", async () => {
    asOwner();
    answer("POST", DEVICES, { status: 201, body: MADE });
    await openTheForm();

    fillIn("k7qm-4rxt", "Laptop Dawa");
    fireEvent.click(screen.getByText("Dawa"));
    send();

    expect(
      await screen.findByText(
        "Kifaa Laptop Dawa kimesajiliwa. Kitaonyesha jina la duka baada ya sekunde chache.",
      ),
    ).toBeDefined();
    const [body] = await confirms();
    expect(body).toEqual({
      id: expect.stringMatching(UUID7),
      pairing_code: "k7qm-4rxt",
      name: "Laptop Dawa",
      home_side: DAWA.id,
    });
    // The form closes, and the button is back for the next laptop.
    expect(screen.queryByLabelText("Namba ya kifaa")).toBeNull();
    expect(screen.getByRole("button", { name: "Sajili kifaa" })).toBeDefined();
  });

  it("puts the keyboard in the code box, and back on Sajili kifaa when the form closes", async () => {
    // Laptops are keyboard first: the place mustn't fall to the page's start.
    asOwner();
    answer("POST", DEVICES, { status: 201, body: MADE });
    await openTheForm();
    expect(document.activeElement).toBe(
      screen.getByLabelText("Namba ya kifaa"),
    );

    fireEvent.click(screen.getByRole("button", { name: "Ghairi" }));
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Sajili kifaa" }),
    );

    // And after a device is made.
    fireEvent.click(screen.getByRole("button", { name: "Sajili kifaa" }));
    fillIn("K7QM4RXT", "Laptop Dawa");
    fireEvent.click(screen.getByText("Dawa"));
    send();
    await screen.findByText(/Kifaa Laptop Dawa kimesajiliwa/);
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Sajili kifaa" }),
    );
  });

  it("sends the same id again after a lost answer, so the shop gets one device", async () => {
    asOwner();
    answer("POST", DEVICES, () => {
      throw new TypeError("Failed to fetch");
    });
    await openTheForm();
    fillIn("K7QM4RXT", "Laptop Dawa");
    fireEvent.click(screen.getByText("Dawa"));

    send();
    expect(
      await screen.findByText(
        "Imeshindwa kufika kwenye seva. Angalia mtandao, kisha ujaribu tena.",
      ),
    ).toBeDefined();
    // The network is back; the first send had reached the server after all, which answers the
    // repeat with the device it made (CreateOnceMixin).
    answer("POST", DEVICES, { status: 200, body: MADE });
    send();

    expect(
      await screen.findByText(/Kifaa Laptop Dawa kimesajiliwa/),
    ).toBeDefined();
    const [first, second] = await confirms();
    expect(second?.id).toBe(first?.id);
  });

  it("asks the list again when the manager gives up after a lost answer", async () => {
    // The send may have reached the server and made the device, though no answer came back.
    asOwner();
    answer("POST", DEVICES, () => {
      throw new TypeError("Failed to fetch");
    });
    await openTheForm();
    fillIn("K7QM4RXT", "Laptop Dawa");
    fireEvent.click(screen.getByText("Dawa"));
    send();
    await screen.findByText(
      "Imeshindwa kufika kwenye seva. Angalia mtandao, kisha ujaribu tena.",
    );
    const listReads = () =>
      sent.filter(
        (request) => request.method === "GET" && request.url.endsWith(DEVICES),
      ).length;
    const before = listReads();

    fireEvent.click(screen.getByRole("button", { name: "Ghairi" }));

    await vi.waitFor(() => expect(listReads()).toBe(before + 1));
  });

  it("gives the next form a new id", async () => {
    asOwner();
    answer("POST", DEVICES, { status: 201, body: MADE });
    await openTheForm();
    fillIn("K7QM4RXT", "Laptop Dawa");
    fireEvent.click(screen.getByText("Dawa"));
    send();
    await screen.findByText(/Kifaa Laptop Dawa kimesajiliwa/);

    fireEvent.click(screen.getByRole("button", { name: "Sajili kifaa" }));
    fillIn("ABCD2345", "Laptop Vyakula");
    fireEvent.click(screen.getByText("Vyakula"));
    send();
    await vi.waitFor(async () => expect(await confirms()).toHaveLength(2));

    const [first, second] = await confirms();
    expect(second?.id).not.toBe(first?.id);
  });

  it("says a wrong code above the code box", async () => {
    asOwner();
    answer("POST", DEVICES, refusal(400, "pairing.code_unknown"));
    await openTheForm();
    fillIn("K7QM4RXZ", "Laptop Dawa");
    fireEvent.click(screen.getByText("Dawa"));

    send();

    expect(
      await screen.findByText("Hakuna kifaa kinachosubiri kwa namba hii."),
    ).toBeDefined();
    expect(
      screen.getByLabelText("Namba ya kifaa").getAttribute("aria-invalid"),
    ).toBe("true");
    // Said once, beside the box, not again on an alert.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says a name the shop already uses above the name box", async () => {
    asOwner();
    answer("POST", DEVICES, refusal(400, "device.name_taken"));
    await openTheForm();
    fillIn("K7QM4RXT", "Laptop Dawa");
    fireEvent.click(screen.getByText("Dawa"));

    send();

    expect(
      await screen.findByText("Kifaa kingine tayari kina jina hili."),
    ).toBeDefined();
    expect(
      screen.getByLabelText("Jina la kifaa").getAttribute("aria-invalid"),
    ).toBe("true");
  });

  it("says a box left empty above that box", async () => {
    asOwner();
    answer("POST", DEVICES, refusal(400, "invalid", {}, { name: ["blank"] }));
    await openTheForm();
    fillIn("K7QM4RXT", "");
    fireEvent.click(screen.getByText("Dawa"));

    send();

    expect(
      await screen.findByText("Sehemu hii haiwezi kuwa tupu."),
    ).toBeDefined();
    expect(
      screen.getByLabelText("Jina la kifaa").getAttribute("aria-invalid"),
    ).toBe("true");
  });

  it("asks for a side before sending anything", async () => {
    asOwner();
    await openTheForm();
    fillIn("K7QM4RXT", "Laptop Dawa");

    send();

    expect(await screen.findByText("Chagua upande.")).toBeDefined();
    expect(sent.filter((request) => request.method === "POST")).toEqual([]);
  });

  it("offers only the sides the person may manage, and picks a lone one", async () => {
    // A Dawa manager who may sell on Vyakula too.
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([
        { side: DAWA, permissions: MANAGE },
        { side: VYAKULA, permissions: ["sale.make"] },
      ]),
    });
    await openTheForm();

    expect(screen.queryByRole("radio", { name: "Vyakula" })).toBeNull();
    expect(
      screen.getByRole("radio", { name: "Dawa" }).getAttribute("aria-checked"),
    ).toBe("true");
  });

  it("shows no Sajili kifaa to someone who may manage no device", async () => {
    answer("GET", ME, {
      status: 200,
      body: whoIsHere([{ side: DAWA, permissions: ["sale.make"] }]),
    });
    render(<DevicesScreen />);

    expect(await screen.findByRole("heading", { name: "Vifaa" })).toBeDefined();
    // Once `me` has answered, and the list with it.
    await vi.waitFor(() => expect(sent.length).toBe(2));
    expect(screen.queryByRole("button", { name: "Sajili kifaa" })).toBeNull();
  });

  it("says to log in first when nobody is", async () => {
    answer("GET", ME, refusal(403, "not_authenticated"));

    render(<DevicesScreen />);

    expect(await screen.findByText("Ingia kwanza.")).toBeDefined();
  });

  it("speaks English after the switch, with no Swahili left", async () => {
    setLanguage("en");
    asOwner();
    const { container } = render(<DevicesScreen />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Register a device" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Register" }));

    expect(await screen.findByText("Pick a side.")).toBeDefined();
    expect(swahiliIn(container)).toEqual([]);
  });
});
