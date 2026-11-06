// client.ts — the one way office screens talk to the server (03 §7.1, ADR-0025).
//
// openapi-fetch reads the routes' types from schema.d.ts, which `pnpm gen:api` writes from the server's
// own description (shared/openapi.json). So `api.GET("/api/v1/people/devices/")` knows every address,
// what each takes and what each answers, and a wrong address or a missing field fails the build. A
// refusal comes back as `error`, typed as the one error shape (ApiError, apps/core/api/errors.py), never
// thrown; when no answer comes at all, it throws NoConnection (refusal.ts).
//
// Only office screens use it. Counter screens read Dexie and never call the server, so they work the same
// offline (rule 5, ADR-0019); a lint rule refuses this folder in app/(counter)/ (eslint.config.mjs).
import createClient, {
  type ClientOptions,
  type Middleware,
} from "openapi-fetch";

import { NoConnection } from "./refusal";
import type { paths } from "./schema";

// Django's names for the CSRF token: the cookie it sets, and the header it checks on every change
// (its defaults, CSRF_COOKIE_NAME and CSRF_HEADER_NAME, which config/settings/ leaves as they are).
export const CSRF_COOKIE = "csrftoken";
export const CSRF_HEADER = "X-CSRFToken";

// The methods that change something: Django checks the token only on these. Our API takes no PUT and no
// DELETE (03 §5.10), but they are listed so a route that ever takes one is covered too.
const CHANGES = new Set(["POST", "PATCH", "PUT", "DELETE"]);

// The cookie's value as it is, never decoded: Django's tokens are letters and digits, which need no
// decoding, and decodeURIComponent() throws on a broken escape ("%E0%A4%A"), which another page on the
// same domain could plant, so every change would throw. Sent as it is, a broken token is the server's
// to refuse, with a clear 403.
function readCookie(name: string): string | undefined {
  for (const pair of document.cookie.split(";")) {
    const [key, ...value] = pair.trim().split("=");
    if (key === name) return value.join("=");
  }
  return undefined;
}

// The session cookie proves who is asking, and the browser sends it with every call, even one that
// another website starts. The token proves the call comes from our own page: another website can't read
// our cookies, so it can't copy the token into the header (03 §5.9).
//
// It is read on every change, never kept: a login gives the browser a new token (Django rotates it), so
// a token kept from before would be refused on the first change after a PIN login (UI-4).
//
// With no cookie yet, the change goes without the header and the server refuses it. The app asks
// /api/devices/v1/me/ first, which sets the cookie (DeviceMeView).
const csrfToken: Middleware = {
  onRequest({ request }) {
    if (CHANGES.has(request.method)) {
      const token = readCookie(CSRF_COOKIE);
      if (token) request.headers.set(CSRF_HEADER, token);
    }
    return request;
  },
};

/** A client with the CSRF token on every change. Screens use `api` below; tests make their own, with a
 * full address and a fake fetch, as Node can't call a relative address. */
export function createApiClient(options: ClientOptions = {}) {
  const client = createClient<paths>({
    // Same origin: Caddy serves the app and the API from one address (03 §12), so a call to /api/...
    // goes to the server that sent the page. "same-origin" sends the session cookie there and nowhere
    // else. It is fetch's own default, written out so nobody changes it to "include" without a reason.
    baseUrl: "",
    credentials: "same-origin",
    ...options,
    fetch: noConnectionWhenNoAnswer(options.fetch),
  });
  client.use(csrfToken);
  return client;
}

// fetch throws a TypeError when no answer comes at all, and so does a bug in a screen ("x is not a
// function"): told apart here, where only fetch can have thrown, so the screen says "check the internet"
// only when that is true, and the store asks again only then (query-client.ts). A read the store
// cancelled, as its screen closed, throws too: that stays a cancel, as TanStack Query expects.
function noConnectionWhenNoAnswer(
  given: ClientOptions["fetch"],
): (request: Request) => Promise<Response> {
  return async (request) => {
    try {
      // globalThis.fetch looked up on each call, not kept, so a test's stand-in is the one used.
      return await (given ?? globalThis.fetch)(request);
    } catch (cause) {
      if (request.signal.aborted) throw cause;
      throw new NoConnection(cause);
    }
  };
}

export const api = createApiClient();
