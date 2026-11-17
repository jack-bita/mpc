// api-error-alert.test.tsx — an API error shows its Swahili message (the UI-2 card's Done line), the
// whole way: a refusal from the server, through the typed client, into the alert.
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { createApiClient } from "@/api/client";
import { answerOf } from "@/api/refusal";
import { setLanguage } from "@/i18n/language";
import { render } from "@/test/render";

import { ApiErrorAlert } from "./api-error-alert";

const SIDE_ID = "01970000-0000-7000-8000-000000000001";

/** Renames a side on a fake server that refuses with `body`, and gives back what was thrown. */
async function refusedRename(status: number, body: object): Promise<unknown> {
  const client = createApiClient({
    baseUrl: "http://shop.test",
    fetch: () => Promise.resolve(Response.json(body, { status })),
  });
  return answerOf(
    client.PATCH("/api/v1/shops/sides/{id}/", {
      params: { path: { id: SIDE_ID } },
      body: { name: "Dawa", version: 1 },
    }),
  ).catch((error: unknown) => error);
}

const CONFLICT = {
  code: "version_conflict",
  message: "This row changed since it was read.",
  fields: {},
  params: {},
};

describe("ApiErrorAlert", () => {
  it("shows an API error's Swahili message", async () => {
    render(<ApiErrorAlert error={await refusedRename(409, CONFLICT)} />);

    // role="alert": a screen reader says it at once.
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Imeshindikana");
    expect(alert.textContent).toContain(
      "Mtu mwingine amebadilisha hiki wakati huo huo. Fungua upya, kisha ujaribu tena.",
    );
    // The server's English `message` is for developers and logs, never for the screen.
    expect(alert.textContent).not.toContain(CONFLICT.message);
  });

  it("shows it in English after the switch", async () => {
    setLanguage("en");
    render(<ApiErrorAlert error={await refusedRename(409, CONFLICT)} />);

    expect(screen.getByRole("alert").textContent).toContain(
      "Someone else changed this at the same time.",
    );
  });

  it("shows a server that sent a page of HTML as a server problem", async () => {
    const client = createApiClient({
      baseUrl: "http://shop.test",
      fetch: () =>
        Promise.resolve(
          new Response("<html>502 Bad Gateway</html>", { status: 502 }),
        ),
    });
    const error = await answerOf(client.GET("/api/v1/shops/sides/")).catch(
      (caught: unknown) => caught,
    );
    render(<ApiErrorAlert error={error} />);

    expect(screen.getByRole("alert").textContent).toContain(
      "Seva ina hitilafu. Jaribu tena baadaye.",
    );
  });

  it("shows nothing while there is no error", () => {
    render(<ApiErrorAlert error={null} />);

    expect(screen.queryByRole("alert")).toBeNull();
  });
});
