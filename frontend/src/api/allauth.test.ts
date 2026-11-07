// allauth.test.ts — the app calls allauth's password routes as it calls an office route, and reads
// allauth's own answers into the API's one refusal (UI-5, ADR-0038).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  allauthRefusal,
  answer,
  fakeFetch,
  refusal,
  sent,
} from "@/test/fake-server";

import { ALLAUTH, callAllauth } from "./allauth";
import { CSRF_HEADER } from "./client";
import { ApiRefusal, NoConnection } from "./refusal";

const LOGIN = `${ALLAUTH}auth/login`;
const SESSION = `${ALLAUTH}auth/session`;
const RESET = `${ALLAUTH}auth/password/reset`;

function setCookie(value: string) {
  document.cookie = `csrftoken=${value}; path=/`;
}

beforeEach(() => {
  // allauth's routes go through the browser's own fetch, which the fake server stands in for.
  vi.stubGlobal("fetch", fakeFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
  // Expire the cookie, so the next test starts with none, as a new phone does.
  document.cookie = "csrftoken=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

/** The refusal a call threw: fails the test if it threw none, or something else. */
async function refusalOf(call: Promise<unknown>): Promise<ApiRefusal> {
  const error: unknown = await call.then(
    () => undefined,
    (caught: unknown) => caught,
  );
  if (!(error instanceof ApiRefusal))
    throw new Error(`Expected an ApiRefusal, got ${String(error)}`);
  return error;
}

describe("a call to allauth", () => {
  it("sends JSON with the CSRF token, and gives back the answer", async () => {
    setCookie("token-from-django");
    answer("POST", LOGIN, { status: 200, body: { status: 200, data: {} } });

    const body = await callAllauth({
      method: "POST",
      route: "auth/login",
      body: { phone: "+255712345678", password: "siri-ya-meneja" },
    });

    expect(body).toEqual({ status: 200, data: {} });
    const [request] = sent;
    expect(request?.headers.get(CSRF_HEADER)).toBe("token-from-django");
    expect(request?.headers.get("Content-Type")).toBe("application/json");
    expect(await request?.json()).toEqual({
      phone: "+255712345678",
      password: "siri-ya-meneja",
    });
  });

  it("asks for the CSRF cookie first when the browser has none", async () => {
    // Django refuses a change with no token, with a page of its own that names no code. Every allauth
    // route hands the cookie out, so the session's is asked first.
    answer("GET", SESSION, () => {
      setCookie("fresh-token");
      return Response.json({ status: 401 }, { status: 401 });
    });
    answer("POST", LOGIN, { status: 200, body: { status: 200 } });

    await callAllauth({ method: "POST", route: "auth/login", body: {} });

    expect(sent.map((request) => request.method)).toEqual(["GET", "POST"]);
    expect(sent[1]?.headers.get(CSRF_HEADER)).toBe("fresh-token");
  });

  it("sends no CSRF token with a read, and the headers it is given", async () => {
    setCookie("token-from-django");
    answer("GET", RESET, { status: 200, body: { status: 200 } });

    await callAllauth({
      method: "GET",
      route: "auth/password/reset",
      headers: { "X-Password-Reset-Key": "abc-123" },
    });

    const [request] = sent;
    expect(request?.headers.get(CSRF_HEADER)).toBeNull();
    expect(request?.headers.get("X-Password-Reset-Key")).toBe("abc-123");
  });

  it("takes the statuses a route answers when it worked", async () => {
    // A reset that worked logs nobody in, so allauth answers 401 (AUTH-3).
    setCookie("token");
    answer("POST", RESET, { status: 401, body: { status: 401 } });

    await expect(
      callAllauth({
        method: "POST",
        route: "auth/password/reset",
        body: {},
        done: [200, 401],
      }),
    ).resolves.toEqual({ status: 401 });
  });

  it("throws NoConnection when no answer came", async () => {
    setCookie("token");
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );

    await expect(
      callAllauth({ method: "POST", route: "auth/login", body: {} }),
    ).rejects.toBeInstanceOf(NoConnection);
  });
});

describe("allauth's refusal, read as the API's one shape", () => {
  beforeEach(() => setCookie("token"));

  it("puts an error that names a box beside it, as `invalid`", async () => {
    // As DRF's do: the form shows each sentence beside its box (apiFieldMessages).
    answer(
      "POST",
      LOGIN,
      allauthRefusal(400, [
        { code: "phone_password_mismatch", param: "password" },
      ]),
    );

    const error = await refusalOf(
      callAllauth({ method: "POST", route: "auth/login", body: {} }),
    );

    expect(error.status).toBe(400);
    expect(error.body).toMatchObject({
      code: "invalid",
      fields: { password: ["phone_password_mismatch"] },
      params: {},
    });
  });

  it("keeps every code a box was given, in order", async () => {
    answer(
      "POST",
      RESET,
      allauthRefusal(400, [
        { code: "password_too_short", param: "password" },
        { code: "password_entirely_numeric", param: "password" },
      ]),
    );

    const error = await refusalOf(
      callAllauth({ method: "POST", route: "auth/password/reset", body: {} }),
    );

    expect(error.body.fields).toEqual({
      password: ["password_too_short", "password_entirely_numeric"],
    });
  });

  it("makes an error for the whole form the refusal's code", async () => {
    answer(
      "POST",
      LOGIN,
      allauthRefusal(400, [{ code: "too_many_login_attempts" }]),
    );

    const error = await refusalOf(
      callAllauth({ method: "POST", route: "auth/login", body: {} }),
    );

    expect(error.body).toMatchObject({
      code: "too_many_login_attempts",
      fields: {},
    });
  });

  it("names a status that came with no code, as the form says", async () => {
    // allauth answers 409 with nothing else when the browser already holds a session (AUTH-4).
    answer("POST", LOGIN, allauthRefusal(409));

    const error = await refusalOf(
      callAllauth({
        method: "POST",
        route: "auth/login",
        body: {},
        bare: { 409: "login.already_in" },
      }),
    );

    expect(error.status).toBe(409);
    expect(error.body.code).toBe("login.already_in");
  });

  it("names a limit `throttled`, with no wait to count", async () => {
    // allauth's limits say no more than 429: the sentence then says to wait a little (codes.ts).
    answer("POST", LOGIN, allauthRefusal(429));

    const error = await refusalOf(
      callAllauth({ method: "POST", route: "auth/login", body: {} }),
    );

    expect(error.body).toMatchObject({ code: "throttled", params: {} });
  });

  it("reads a proxy's page of HTML as the server's problem", async () => {
    // Caddy's or Render's 502 while the server restarts (refusal.ts).
    answer(
      "POST",
      LOGIN,
      () => new Response("<html>Bad gateway</html>", { status: 502 }),
    );

    const error = await refusalOf(
      callAllauth({ method: "POST", route: "auth/login", body: {} }),
    );

    expect(error.body.code).toBe("server_error");
  });

  it("reads an answer in some other shape as a refusal with no code of its own", async () => {
    // Django's own 403 when the CSRF token is wrong, or our API's shape from a route that isn't
    // allauth's: neither has allauth's list of errors.
    answer("POST", LOGIN, refusal(403, "permission_denied"));

    const error = await refusalOf(
      callAllauth({ method: "POST", route: "auth/login", body: {} }),
    );

    expect(error.status).toBe(403);
    expect(error.body.code).toBe("bad_request");
  });
});
