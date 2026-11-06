// client.test.ts — the office screens' client: every change carries the CSRF token, read fresh from its
// cookie, and a refusal comes back in the one error shape (UI-2, 03 §5.9, §5.10).
import { afterEach, describe, expect, it, vi } from "vitest";

import { CSRF_HEADER, createApiClient } from "./client";
import { NoConnection } from "./refusal";

const SIDE_ID = "01970000-0000-7000-8000-000000000001";

// A fake server: it keeps every request the client sends and answers each one with `answer`.
function fakeServer(answer: () => Response = () => Response.json({})) {
  const sent: Request[] = [];
  const fetch = vi.fn(async (request: Request) => {
    sent.push(request);
    return answer();
  });
  // Node needs a full address; in the browser the client calls /api/... on the page's own address.
  return {
    sent,
    client: createApiClient({ baseUrl: "http://shop.test", fetch }),
  };
}

// The request a test's one call sent: exactly one, so a client that sent two, or none, fails here.
function theOneRequest(sent: Request[]): Request {
  const [request, ...others] = sent;
  expect(others).toEqual([]);
  if (!request) throw new Error("The client sent nothing.");
  return request;
}

function setCookie(value: string) {
  document.cookie = `csrftoken=${value}; path=/`;
}

afterEach(() => {
  // Expire the cookie, so the next test starts with none, as a new device does.
  document.cookie = "csrftoken=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("the CSRF token", () => {
  it("goes with a change, copied from its cookie", async () => {
    setCookie("token-from-django");
    const { sent, client } = fakeServer();

    await client.PATCH("/api/v1/shops/sides/{id}/", {
      params: { path: { id: SIDE_ID } },
      body: { name: "Dawa", version: 1 },
    });

    expect(theOneRequest(sent).method).toBe("PATCH");
    expect(theOneRequest(sent).headers.get(CSRF_HEADER)).toBe(
      "token-from-django",
    );
  });

  it("is read again for each change, so the new one after a login is sent", async () => {
    setCookie("before-login");
    const { sent, client } = fakeServer();
    await client.POST("/api/auth/logout/");
    // A PIN login makes Django send a new token (UI-4).
    setCookie("after-login");
    await client.POST("/api/auth/logout/");

    expect(sent.map((request) => request.headers.get(CSRF_HEADER))).toEqual([
      "before-login",
      "after-login",
    ]);
  });

  it("stays off a read, which changes nothing", async () => {
    setCookie("token-from-django");
    const { sent, client } = fakeServer();

    await client.GET("/api/v1/shops/sides/");

    expect(theOneRequest(sent).headers.has(CSRF_HEADER)).toBe(false);
  });

  it("is sent as it is, so a broken cookie can't stop every change", async () => {
    // Django's tokens are letters and digits, but a cookie can hold anything another page put there,
    // like this broken escape. Decoding it would throw on every change; the server judges it instead.
    setCookie("%E0%A4%A");
    const { sent, client } = fakeServer();

    await client.POST("/api/auth/logout/");

    expect(theOneRequest(sent).headers.get(CSRF_HEADER)).toBe("%E0%A4%A");
  });

  it("is left out, not sent empty, before the server has given one", async () => {
    const { sent, client } = fakeServer();

    await client.POST("/api/auth/logout/");

    expect(theOneRequest(sent).headers.has(CSRF_HEADER)).toBe(false);
  });
});

describe("the answers", () => {
  it("call the server's own address, with the route's path", async () => {
    const { sent, client } = fakeServer();

    await client.GET("/api/v1/shops/sides/{id}/", {
      params: { path: { id: SIDE_ID } },
    });

    expect(theOneRequest(sent).url).toBe(
      `http://shop.test/api/v1/shops/sides/${SIDE_ID}/`,
    );
  });

  it("give a refusal back as the one error shape", async () => {
    const refusal = {
      code: "version_conflict",
      message: "This row changed since it was read.",
      fields: {},
      params: {},
    };
    const { client } = fakeServer(() =>
      Response.json(refusal, { status: 409 }),
    );

    const { data, error, response } = await client.PATCH(
      "/api/v1/shops/sides/{id}/",
      { params: { path: { id: SIDE_ID } }, body: { name: "Dawa", version: 1 } },
    );

    // Typed from each route's `default` answer (apps/core/api/schema.py): `error.code` compiles only
    // because the server's description says how every route refuses.
    expect(error?.code).toBe("version_conflict");
    expect(data).toBeUndefined();
    expect(response.status).toBe(409);
  });

  it("throw NoConnection when no answer came at all", async () => {
    // What fetch throws when the network drops, or the server can't be reached.
    const dropped = new TypeError("Failed to fetch");
    const client = createApiClient({
      baseUrl: "http://shop.test",
      fetch: () => Promise.reject(dropped),
    });

    const error: unknown = await client
      .GET("/api/v1/shops/sides/")
      .catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(NoConnection);
    // The browser's own error stays inside, for the console.
    expect((error as NoConnection).cause).toBe(dropped);
  });

  it("leave a cancelled read as a cancel, not a lost connection", async () => {
    // TanStack Query cancels a read a closed screen no longer needs; fetch then throws an AbortError.
    const stop = new AbortController();
    stop.abort();
    const client = createApiClient({
      baseUrl: "http://shop.test",
      fetch: (request: Request) =>
        Promise.reject(
          request.signal.aborted
            ? request.signal.reason
            : new Error("not cancelled"),
        ),
    });

    const error: unknown = await client
      .GET("/api/v1/shops/sides/", { signal: stop.signal })
      .catch((caught: unknown) => caught);

    expect(error).not.toBeInstanceOf(NoConnection);
    expect((error as Error).name).toBe("AbortError");
  });
});
