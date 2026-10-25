// version.ts — the app's version: the git commit it was built from (SPIKE-1, 03 §6.5).
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
