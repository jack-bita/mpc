// refusal.ts — a server's refusal as an error that TanStack Query can catch (UI-2, 03 §5.10).
//
// openapi-fetch hands a refusal back as a value, `{ error, response }`, and throws only when the network
// drops. TanStack Query sees a failure only when something is thrown. So office screens call the server
// through answerOf(), which gives back the answer, or throws an ApiRefusal that keeps the status and the
// one error shape (apps/core/api/errors.py). When no answer came at all, the client throws NoConnection.
import type { components } from "./schema";

/** The one error shape, as the server's description gives it: `{code, message, fields, params}`. */
export type ApiError = components["schemas"]["ApiError"];

export class ApiRefusal extends Error {
  readonly status: number;
  readonly body: ApiError;

  constructor(status: number, body: ApiError) {
    // The code as the error's message, for the console and error reports: never shown to a person.
    super(body.code);
    this.name = "ApiRefusal";
    this.status = status;
    this.body = body;
  }
}

/** No answer came at all: the network dropped, or the server can't be reached. The client throws it
 * (client.ts) in place of fetch's own TypeError, which a bug in a screen throws too: so a bug isn't shown
 * as "check the internet", nor asked again. fetch's error stays inside, as `cause`. */
export class NoConnection extends Error {
  constructor(cause: unknown) {
    super("No answer from the server.", { cause });
    this.name = "NoConnection";
  }
}

// What every openapi-fetch call gives back. Its own type is a union, one side with `data` and one with
// `error`; this wider shape takes both, so answerOf() works for every route.
type Answer<D> = { data?: D; error?: unknown; response: Response };

/** The answer of a call, or an ApiRefusal when the server refused it. A route that answers 204, with
 * nothing, gives undefined. */
export async function answerOf<D>(call: Promise<Answer<D>>): Promise<D> {
  const { data, error, response } = await call;
  if (response.ok) return data as D;
  throw new ApiRefusal(response.status, asApiError(error));
}

// openapi-fetch hands back whatever the body held. From Django under /api/ that is the one shape, a crash
// and a request Django finds suspicious included (apps/core/api/errors.py); only DEBUG's own page on a
// laptop isn't. But a refusal can come from the proxy in front of Django, Caddy on the real server and
// Render's on the demo, which answers 502 or 503 with a page of HTML while the server restarts, during a
// deploy or as the demo wakes up. Such a body has no code to translate, so it reads as `server_error`,
// which the screen shows as "the server has a problem".
function asApiError(body: unknown): ApiError {
  if (isApiError(body)) return body;
  return {
    code: "server_error",
    message: "No answer from the API.",
    fields: {},
    params: {},
  };
}

function isApiError(body: unknown): body is ApiError {
  if (typeof body !== "object" || body === null) return false;
  const { code, fields, params } = body as Record<string, unknown>;
  return (
    typeof code === "string" &&
    typeof fields === "object" &&
    fields !== null &&
    typeof params === "object" &&
    params !== null
  );
}
