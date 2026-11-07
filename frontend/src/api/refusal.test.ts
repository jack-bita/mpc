// refusal.test.ts — answerOf() gives back the answer, or throws the server's refusal in the one error
// shape, even when the body came from something in front of Django (UI-2).
import { describe, expect, it } from "vitest";

import { createApiClient } from "./client";
import { ApiRefusal, answerOf } from "./refusal";

const LOCKED = {
  code: "pin.locked",
  message: "Too many wrong PINs.",
  fields: {},
  params: { wait: 300 },
};

// What an openapi-fetch call gives back, built by hand: the body as openapi-fetch read it, and the response.
function answer(status: number, body: { data?: unknown; error?: unknown }) {
  return Promise.resolve({ ...body, response: new Response(null, { status }) });
}

async function refusalOf(call: Promise<unknown>): Promise<ApiRefusal> {
  const error: unknown = await call.catch((caught: unknown) => caught);
  if (!(error instanceof ApiRefusal)) throw new Error("No refusal was thrown.");
  return error;
}

describe("answerOf", () => {
  it("gives back the answer", async () => {
    await expect(
      answerOf(answer(200, { data: { name: "Dawa" } })),
    ).resolves.toEqual({
      name: "Dawa",
    });
  });

  it("gives back nothing for a route that answers 204", async () => {
    await expect(answerOf(answer(204, {}))).resolves.toBeUndefined();
  });

  it("throws a refusal with its status and the one error shape", async () => {
    const refusal = await refusalOf(answerOf(answer(400, { error: LOCKED })));

    expect(refusal.status).toBe(400);
    expect(refusal.body).toEqual(LOCKED);
    // The code, for the console and error reports.
    expect(refusal.message).toBe("pin.locked");
  });

  it("reads a page of HTML from in front of Django as a server error", async () => {
    // The proxy's answer while the server restarts: openapi-fetch hands back the text it couldn't read
    // as JSON.
    const html = "<html><body>502 Bad Gateway</body></html>";
    const refusal = await refusalOf(answerOf(answer(502, { error: html })));

    expect(refusal.status).toBe(502);
    expect(refusal.body.code).toBe("server_error");
    expect(refusal.body).toMatchObject({ fields: {}, params: {} });
  });

  it("takes the real client's answers, typed by their route", async () => {
    const side = { id: "01970000-0000-7000-8000-000000000001", name: "Dawa" };
    const client = createApiClient({
      baseUrl: "http://shop.test",
      fetch: () => Promise.resolve(Response.json(side)),
    });

    const read = await answerOf(
      client.GET("/api/v1/shops/sides/{id}/", {
        params: { path: { id: side.id } },
      }),
    );

    // `read.name` compiles only because answerOf() kept the route's own answer type, Side.
    expect(read.name).toBe("Dawa");
  });

  it("reads a body that isn't the whole shape as a server error", async () => {
    for (const error of [
      undefined,
      null,
      { detail: "Not found." },
      { code: "x" },
      // Each of the four keys counts: with one missing, or of the wrong kind, a screen reading it could
      // break, so it is no refusal of ours.
      { code: "pin.wrong", fields: {}, params: {} },
      { code: "pin.wrong", message: 5, fields: {}, params: {} },
      { code: "pin.wrong", message: "", fields: [], params: {} },
      { code: "pin.wrong", message: "", fields: {}, params: [] },
    ]) {
      const refusal = await refusalOf(answerOf(answer(404, { error })));
      expect(refusal.body.code, JSON.stringify(error)).toBe("server_error");
    }
  });
});
