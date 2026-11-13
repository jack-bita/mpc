// make-client.ts — how the typed client is made, wherever it runs: on a page (client.ts, which reads the
// CSRF token from document.cookie) or in the service worker, which has no `document` and reads the same
// cookie its own way (sw.ts, SYNC-16).
//
// Kept apart from client.ts so the worker's code, which TypeScript checks with the worker's types
// (tsconfig.sw.json), never meets the page's `document`. Everything a client does is here: the token on
// every change, and a lost network told apart from a bug (NoConnection).
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

/** Where a client finds the CSRF header for a change. A page reads it from document.cookie (csrfHeader);
 * the service worker has no `document`, so it reads the same cookie its own way (SYNC-16). */
export type CsrfSource = () =>
  Record<string, string> | Promise<Record<string, string>>;

function withCsrfToken(source: CsrfSource): Middleware {
  return {
    async onRequest({ request }) {
      if (CHANGES.has(request.method))
        for (const [name, value] of Object.entries(await source()))
          request.headers.set(name, value);
      return request;
    },
  };
}

/** A client with the CSRF token on every change, read from `csrf`. */
export function createApiClient(options: ClientOptions, csrf: CsrfSource) {
  const client = createClient<paths>({
    // Same origin: the app and the API come from one address, Caddy's on the real server and Django's own
    // on the demo (03 §12, §13), so a call to /api/... goes to the server that sent the page.
    // "same-origin" sends the session cookie there and nowhere else. It is fetch's own default, written
    // out so nobody changes it to "include" without a reason.
    baseUrl: "",
    credentials: "same-origin",
    ...options,
    fetch: noConnectionWhenNoAnswer(options.fetch),
  });
  client.use(withCsrfToken(csrf));
  return client;
}

/** A client as createApiClient makes it: the page's `api`, or the service worker's own (SYNC-16). */
export type ApiClient = ReturnType<typeof createApiClient>;

// fetch throws a TypeError when no answer comes at all, and so does a bug in a screen ("x is not a
// function"): told apart here, where only fetch can have thrown, so the screen says "check the internet"
// only when that is true, and the store asks again only then (query-client.ts).
//
// The whole answer is read here too, not only its start: fetch hands back the answer once its first
// bytes arrive, and openapi-fetch reads the rest later, outside this check. A long list on 3G whose
// signal drops halfway would then throw a plain TypeError, and read as a bug. The answer is read on a
// copy (clone()), so openapi-fetch still reads it as usual; our answers are small JSON, kept whole anyway.
//
// A read the store cancelled, as its screen closed, throws too: that stays a cancel, as TanStack Query
// expects. A call that ran out of time (AbortSignal.timeout(), as the sync's calls have, SYNC-9) is no
// cancel: nobody stopped it, no answer came in time, so it is NoConnection, as a dropped network is. And
// a single call given its own fetch (api.GET(path, { fetch })) skips this check, as openapi-fetch takes
// that one over the client's.
export function noConnectionWhenNoAnswer(
  given: ClientOptions["fetch"],
): (request: Request) => Promise<Response> {
  return async (request) => {
    try {
      // globalThis.fetch looked up on each call, not kept, so a test's stand-in is the one used.
      const response = await (given ?? globalThis.fetch)(request);
      await response.clone().arrayBuffer();
      return response;
    } catch (cause) {
      if (request.signal.aborted && !ranOutOfTime(request.signal)) throw cause;
      throw new NoConnection(cause);
    }
  };
}

// AbortSignal.timeout() stops a call with a "TimeoutError"; a cancel stops it with an "AbortError". Read
// by name, as the error may come from another part of the browser than this page's DOMException.
function ranOutOfTime(signal: AbortSignal): boolean {
  const reason: unknown = signal.reason;
  return (
    typeof reason === "object" &&
    reason !== null &&
    (reason as { name?: unknown }).name === "TimeoutError"
  );
}
