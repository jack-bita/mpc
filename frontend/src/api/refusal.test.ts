// refusal.test.ts — answerOf() gives back the answer, or throws the server's refusal in the one error
// shape, even when the body came from something in front of Django (UI-2); and aboutTheWholeRequest() says which
// failure a form shows above its buttons, not beside a box (ATT-9, moved here in ATT-6's review).
import { describe, expect, it } from "vitest";

import { createApiClient } from "./client";
import {
  aboutTheChange,
  aboutTheWholeRequest,
  ApiRefusal,
  answerOf,
} from "./refusal";

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

describe("aboutTheWholeRequest", () => {
  /** A refusal in the one error shape, with its code and the codes beside its boxes. */
  function refused(code: string, fields: Record<string, string[]> = {}) {
    return new ApiRefusal(400, { code, message: code, fields, params: {} });
  }

  it("leaves to the boxes a refusal of the boxes alone", () => {
    // Every problem is beside a box: the form shows them there, and nothing above its buttons.
    expect(
      aboutTheWholeRequest(
        refused("invalid", { reason: ["day.reason_missing"] }),
      ),
    ).toBeNull();
  });

  it("keeps a refusal about the whole request, even with boxes beside it", () => {
    // A demo's refusal of today, with first_day beside it: the form says both at once (ATT-9's review).
    const both = refused("closure.overlaps", {
      first_day: ["demo.closures_from_tomorrow"],
    });
    expect(aboutTheWholeRequest(both)).toBe(both);
    const whole = refused("day.own");
    expect(aboutTheWholeRequest(whole)).toBe(whole);
  });

  it("keeps an invalid with no box to show it beside, and any other failure", () => {
    const nowhere = refused("invalid");
    expect(aboutTheWholeRequest(nowhere)).toBe(nowhere);
    const offline = new TypeError("Failed to fetch");
    expect(aboutTheWholeRequest(offline)).toBe(offline);
    expect(aboutTheWholeRequest(null)).toBeNull();
  });
});

describe("aboutTheChange", () => {
  const refusedFor = (code: string, fields: Record<string, string[]>) =>
    new ApiRefusal(400, { code, message: code, fields, params: {} });

  it("says a field the form has no box for in that field's own code, above the buttons", () => {
    const taken = aboutTheChange(refusedFor("invalid", { id: ["id.taken"] }), [
      "text",
    ]);
    expect(taken).toBeInstanceOf(ApiRefusal);
    expect((taken as ApiRefusal).body).toMatchObject({
      code: "id.taken",
      fields: {},
    });
  });

  it("leaves the form's own boxes' refusals beside them", () => {
    const beside = refusedFor("invalid", { text: ["flag.note_required"] });
    expect(aboutTheChange(beside, ["text"])).toBeNull();
  });

  it("shows any other failure as it is, one that names nothing included", () => {
    const whole = refusedFor("flag.closed", {});
    expect(aboutTheChange(whole, ["text"])).toBe(whole);
    const nowhere = refusedFor("invalid", {});
    expect(aboutTheChange(nowhere, ["text"])).toBe(nowhere);
    expect(aboutTheChange(null)).toBeNull();
  });
});
