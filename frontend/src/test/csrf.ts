// csrf.ts — the CSRF token's cookie, as the server leaves it on a working laptop: the device check's
// answer sets it (DeviceMeView), and every change sends it back (src/api/client.ts). The sync's push waits
// for it (sync.ts, SYNC-9), so the sync's tests start with it; vitest.setup.ts takes it away after each
// test, so the next starts as a new device does, with none. Tests only.

/** The cookie as Django sets it: on the whole address. */
export function giveCsrfToken(value = "token-from-django"): void {
  document.cookie = `csrftoken=${value}; path=/`;
}

/** Expires the cookie: the browser forgets it at once. */
export function forgetCsrfToken(): void {
  document.cookie = "csrftoken=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
}
