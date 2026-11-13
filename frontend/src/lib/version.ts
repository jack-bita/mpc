// version.ts — the app's version, the git commit it was built from (SPIKE-1, 03 §6.5), and its number,
// which the server's minimum is compared with (SYNC-13, 03 §6.8).
//
// The image build passes the commit to `pnpm build` as NEXT_PUBLIC_APP_VERSION (backend/Dockerfile,
// APP_VERSION). Next.js writes the value of every NEXT_PUBLIC_ variable into the code at build time, so
// a device keeps showing the version it runs, offline too. The server shows the same commit at
// /api/health/, so a device's version can be compared with the server's after an update.

/** The first 7 characters of a commit, as GitHub shows it: enough to tell versions apart. Builds that
 * get no version (a laptop, CI's frontend job) are "dev". */
export function shortVersion(version: string | undefined): string {
  return version ? version.slice(0, 7) : "dev";
}

// Written out in full, process.env.NEXT_PUBLIC_APP_VERSION: Next.js replaces only that exact spelling.
export const APP_VERSION = shortVersion(process.env.NEXT_PUBLIC_APP_VERSION);

/**
 * The app's number: whether it is new enough to sync. Every pull page names the lowest number the server
 * still serves (`min_app_version`); an app below it sends what it holds, then updates (SYNC-13).
 *
 * A commit can't say whether it is older or newer than another, so this whole number does, raised by
 * hand in a release that must retire older apps: one that adds a list to the registry, which an older app
 * has no drawer for, or one whose apps stop writing a record shape the server is to drop. Raise it together
 * with the server's MIN_APP_VERSION (config/settings/base.py); a backend test reads this line, and fails if
 * the server's minimum is ever above it (apps/sync/tests/test_app_number.py). Keep its form: one line,
 * `export const APP_NUMBER = <n>;`.
 *
 * The shape itself leaves the server's list only in a later release. An app below the minimum sends its
 * outbox first, in the shapes it wrote: in the same release the server would refuse those records, Asha's
 * waiting clock-in among them, and set them aside for a manager. */
export const APP_NUMBER = 1;
