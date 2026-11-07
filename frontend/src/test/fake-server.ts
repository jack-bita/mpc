// fake-server.ts — a server in miniature for tests of screens that call the API: each test says how a
// route answers, and the app's own client calls it (UI-3). Tests only.
//
// Screens call the server through `api` (src/api/client.ts), whose address is relative ("/api/..."), as
// the app and the API share one address. Node can't call a relative address, so a test file swaps `api`
// for a client with a full address whose fetch is this server, at the top of the file:
//
//   vi.mock("@/api/client", async (importOriginal) =>
//     (await import("@/test/fake-server")).withFakeServer(await importOriginal()));
//
// The real client still does the work, with its CSRF header and its network check (createApiClient):
// only the far end is fake. vitest.setup.ts empties the server after each test.
import type * as ClientModule from "@/api/client";

type Handler = (request: Request) => Response | Promise<Response>;

// Each route's answer, by method and path ("GET /api/devices/v1/me/"). The query string is left out:
// a test that cares reads it from the request it is handed.
const routes = new Map<string, Handler>();

/** Every request the app sent, in order, each a copy whose body a test can still read. */
export const sent: Request[] = [];

/** Says how a route answers: with a handler, or with a body and a status, the same each time. */
export function answer(
  method: string,
  path: string,
  how: Handler | { status: number; body?: unknown },
): void {
  routes.set(
    `${method} ${path}`,
    typeof how === "function"
      ? how
      : () =>
          how.body === undefined
            ? new Response(null, { status: how.status })
            : Response.json(how.body, { status: how.status }),
  );
}

/** A refusal in the API's one shape (apps/core/api/errors.py), for answer(). */
export function refusal(
  status: number,
  code: string,
  params: Record<string, unknown> = {},
  fields: Record<string, string[]> = {},
): { status: number; body: unknown } {
  return { status, body: { code, message: code, fields, params } };
}

/** Forgets every route and every request: vitest.setup.ts calls it after each test. */
export function resetFakeServer(): void {
  routes.clear();
  sent.length = 0;
}

async function fakeFetch(request: Request): Promise<Response> {
  sent.push(request.clone());
  const handler = routes.get(
    `${request.method} ${new URL(request.url).pathname}`,
  );
  // A route the test didn't set answers as Django does for an address it doesn't serve, so a test that
  // forgot one sees a refusal, never a hang.
  return handler
    ? handler(request)
    : Response.json(
        { code: "not_found", message: "not_found", fields: {}, params: {} },
        { status: 404 },
      );
}

/** The client module with `api` swapped for one that calls this server (see the top of this file). */
export function withFakeServer(real: typeof ClientModule): typeof ClientModule {
  return {
    ...real,
    api: real.createApiClient({
      baseUrl: "http://shop.test",
      fetch: fakeFetch,
    }),
  };
}
