// allauth.ts — the one way the app calls django-allauth's password routes, and reads their answers
// (UI-5, ADR-0038, 03 §5.9).
//
// The owner and managers log in, log out and choose a new password through allauth, at
// /_allauth/browser/v1/ (backend/apps/people/api/password_urls.py). Those routes are outside /api/, so
// they aren't in the API's description, and the typed client (`api`, client.ts) can't call them. And
// they answer in allauth's own shape, not the API's one error shape (CORE-6):
//
//   {"status": 400, "errors": [{"code": "phone_password_mismatch", "param": "password", "message": …}]}
//
// So this file calls them as the client calls an office route (one address, the session cookie, the
// CSRF token on each change, NoConnection when no answer came), and turns allauth's refusal into the same
// ApiRefusal an office route throws. A password form then shows it like any office form does: a box's
// sentence beside the box (apiFieldMessages), anything else in ApiErrorAlert, and TanStack Query treats
// it like any other refusal.
import { csrfHeader, fetchOrNoConnection } from "./client";
import { type ApiError, ApiRefusal } from "./refusal";

/** Where allauth's routes for the browser live (backend/config/urls.py). */
export const ALLAUTH = "/_allauth/browser/v1/";

/** The routes the app may call. password_urls.py mounts these and no others; any other address there
 * answers 404. */
export type AllauthRoute =
  | "auth/session"
  | "auth/login"
  | "auth/password/request"
  | "auth/password/reset"
  | "account/password/change";

/** A code for each status that comes with no code at all. What a bare 401 or 409 means depends on the
 * route, so the form that calls it names it. */
export type BareCodes = Partial<Record<number, string>>;

// allauth's limits answer 429 and nothing else. `throttled` with no wait says "wait a little, then try
// again" (codes.ts), true of every limit allauth has.
const BARE_ON_EVERY_ROUTE: BareCodes = { 429: "throttled" };

export interface AllauthCall {
  method: "GET" | "POST";
  route: AllauthRoute;
  /** What a change sends, as JSON. */
  body?: Record<string, string>;
  /** Headers of the route's own, like the reset link's key (X-Password-Reset-Key). */
  headers?: Record<string, string>;
  /** The statuses that mean it worked: 200, unless the route says otherwise. A reset that worked
   * answers 401, as it logs nobody in (AUTH-3). */
  done?: readonly number[];
  /** A code for each status the route answers with no code (BareCodes). */
  bare?: BareCodes;
}

/** Calls an allauth route. Gives back its answer's JSON when it worked; throws an ApiRefusal when it was
 * refused, and NoConnection when no answer came at all. */
export async function callAllauth({
  method,
  route,
  body,
  headers = {},
  done = [200],
  bare = {},
}: AllauthCall): Promise<unknown> {
  const changes = method === "POST";
  // Django refuses a change with no CSRF token, with a page of its own that names no code. The app gets
  // the token's cookie as it opens (the device's check asks /api/devices/v1/me/, device-check.tsx), but
  // a form sent before that answer came, or after the browser lost its cookies, would have none. Every
  // allauth route hands the cookie out, so the session's is asked first; its own answer doesn't matter.
  if (changes && Object.keys(csrfHeader()).length === 0)
    await fetchOrNoConnection(allauthRequest("GET", "auth/session", {}));

  const response = await fetchOrNoConnection(
    allauthRequest(
      method,
      route,
      {
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        // Read now, after the cookie was asked for: a login gives the browser a new token (client.ts).
        ...(changes ? csrfHeader() : {}),
        ...headers,
      },
      body === undefined ? undefined : JSON.stringify(body),
    ),
  );
  // allauth answers JSON; a proxy's page of HTML has none to read (refusal.ts).
  const answer: unknown = await response.json().catch(() => undefined);
  if (done.includes(response.status)) return answer;
  throw new ApiRefusal(
    response.status,
    asApiError(response.status, answer, bare),
  );
}

function allauthRequest(
  method: AllauthCall["method"],
  route: AllauthRoute,
  headers: Record<string, string>,
  body?: string,
): Request {
  // A full address, from the page's own: the app and allauth share one address (ADR-0038). A Request made
  // outside a page, as a test's in Node, can't take a relative one.
  return new Request(new URL(ALLAUTH + route, location.href), {
    method,
    // The session cookie goes to our own address only, as the client's does (client.ts).
    credentials: "same-origin",
    headers: { Accept: "application/json", ...headers },
    body,
  });
}

/** One of allauth's errors, as much of it as the app reads. */
interface AllauthError {
  code?: unknown;
  param?: unknown;
}

/** allauth's refusal in the API's one shape. An error that names a box goes beside it, and the refusal's
 * code is then `invalid`, as DRF's are; an error for the whole form is the refusal's code. */
function asApiError(
  status: number,
  answer: unknown,
  bare: BareCodes,
): ApiError {
  const fields: Record<string, string[]> = {};
  let code: string | undefined;
  for (const error of errorsOf(answer)) {
    // A check with no code of its own still says the value was wrong.
    const errorCode =
      typeof error.code === "string" && error.code ? error.code : "invalid";
    if (typeof error.param === "string" && error.param)
      (fields[error.param] ??= []).push(errorCode);
    else code ??= errorCode;
  }
  if (code === undefined && Object.keys(fields).length > 0) code = "invalid";
  // No error at all: a bare status, which the route names, or else a proxy's page of HTML while the server
  // restarts, or an answer in some other shape, like Django's own CSRF refusal.
  code ??=
    { ...BARE_ON_EVERY_ROUTE, ...bare }[status] ??
    (status >= 500 ? "server_error" : "bad_request");
  // The message is the code, as in refusal.ts: never shown to a person, who reads its sentence (codes.ts).
  return { code, message: code, fields, params: {} };
}

// allauth's list of errors, or none: a body that isn't allauth's has nothing to read.
function errorsOf(answer: unknown): AllauthError[] {
  if (typeof answer !== "object" || answer === null) return [];
  const { errors } = answer as { errors?: unknown };
  if (!Array.isArray(errors)) return [];
  return errors.filter(
    (error): error is AllauthError =>
      typeof error === "object" && error !== null,
  );
}
