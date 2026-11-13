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
import {
  type ApiClient,
  CSRF_COOKIE,
  CSRF_HEADER,
  createApiClient as createClientWithToken,
  noConnectionWhenNoAnswer,
} from "./make-client";

export type { ApiClient, CsrfSource } from "./make-client";
export { CSRF_COOKIE, CSRF_HEADER } from "./make-client";

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
/** The CSRF header for a change, from its cookie: `{"X-CSRFToken": …}`, or nothing before the server
 * has given a token. The client adds it to every change itself; a route outside the API's description,
 * like allauth's password routes (UI-5), puts it on by hand. */
export function csrfHeader(): Record<string, string> {
  const token = readCookie(CSRF_COOKIE);
  return token ? { [CSRF_HEADER]: token } : {};
}

/** Whether the server has given this browser a CSRF token yet: without one, every change is refused. The
 * sync's push asks first, so it doesn't send a change bound to fail (SYNC-9). */
export function hasCsrfToken(): boolean {
  return Object.keys(csrfHeader()).length > 0;
}

/** A client with the CSRF token on every change, read from this page's cookies (csrfHeader). Screens use
 * `api` below; tests make their own, with a full address and a fake fetch, as Node can't call a relative
 * address. The service worker, which has no cookies of a page, makes its own with make-client.ts. */
export function createApiClient(
  options: Parameters<typeof createClientWithToken>[0] = {},
): ApiClient {
  return createClientWithToken(options, csrfHeader);
}

/** fetch for a route the typed client can't call, like allauth's password routes (UI-5): it throws
 * NoConnection when no answer came, as the client does, so a login form offline says "check the
 * internet", not "something went wrong". */
export const fetchOrNoConnection = noConnectionWhenNoAnswer(undefined);

export const api = createApiClient();
