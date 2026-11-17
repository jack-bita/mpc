// locks.ts — a stand-in for the browser's Web Locks (navigator.locks), which jsdom lacks: a test plays
// another tab holding a lock, and sees this tab wait for it (SYNC-9) or keep away from it (SYNC-13).
// Tests only.
//
// It does what the app needs of the real one, nothing more:
// - request(name, work) gives the lock to one at a time, in the order asked, and hands it on once the work
//   ends, however it ended; the answer is the work's own. The sync's lock (SYNC-9).
// - request(name, { mode: "shared" }, work) is given at once, to as many as ask. Only the counter's busy
//   marks ask for one (src/offline/busy.ts), and nothing ever takes their lock alone, so a shared ask
//   never waits here; the real browser would make it wait behind someone holding the lock alone.
// - query() lists who holds a lock and who waits for one, as the update bar reads it (SYNC-13).
// No ifAvailable, no steal and no signal: the app asks for none.

type Work = (lock: Lock | null) => unknown;

export class FakeLocks {
  // The end of each lock's line: the next to ask waits for it.
  private readonly lines = new Map<string, Promise<void>>();
  // Who holds a lock now, and who waits in a line, for query(). One entry per ask.
  private readonly held: LockInfo[] = [];
  private readonly pending: LockInfo[] = [];

  request(name: string, work: Work): Promise<unknown>;
  request(name: string, options: LockOptions, work: Work): Promise<unknown>;
  request(
    name: string,
    optionsOrWork: LockOptions | Work,
    maybeWork?: Work,
  ): Promise<unknown> {
    const options = typeof optionsOrWork === "function" ? {} : optionsOrWork;
    const work =
      typeof optionsOrWork === "function" ? optionsOrWork : maybeWork!;
    if (options.mode === "shared") return this.holdWhile(name, "shared", work);

    const info: LockInfo = { name, mode: "exclusive" };
    this.pending.push(info);
    const before = this.lines.get(name) ?? Promise.resolve();
    const done = before.then(() => {
      remove(this.pending, info);
      return this.holdWhile(name, "exclusive", work);
    });
    // Handed on however the work ended: a failed sync must not hold the lock.
    const handedOn = done.then(nothing, nothing);
    this.lines.set(name, handedOn);
    return done;
  }

  /** Who holds which lock, and who waits, as the browser's own query() answers. */
  query(): Promise<LockManagerSnapshot> {
    return Promise.resolve({
      held: [...this.held],
      pending: [...this.pending],
    });
  }

  /**
   * Another tab takes the lock and holds it until the test lets it go: `release` ends its work, and
   * `granted` says when it got the lock. `mode` "shared" plays a busy counter screen in that tab.
   */
  holdInAnotherTab(
    name: string,
    mode: LockMode = "exclusive",
  ): {
    granted: Promise<void>;
    release: () => void;
  } {
    let release = nothing;
    let granted = nothing;
    const got = new Promise<void>((resolve) => {
      granted = resolve;
    });
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    void this.request(name, { mode }, () => {
      granted();
      return held;
    });
    return { granted: got, release: () => release() };
  }

  // Holds the lock while the work runs, and lets it go once its answer settles, however it settled.
  private async holdWhile(
    name: string,
    mode: LockMode,
    work: Work,
  ): Promise<unknown> {
    const info: LockInfo = { name, mode };
    this.held.push(info);
    try {
      return await work({ name, mode });
    } finally {
      remove(this.held, info);
    }
  }
}

function nothing(): void {}

// Takes this very entry off its list: two asks of the same lock are two entries that look alike.
function remove(list: LockInfo[], info: LockInfo): void {
  const at = list.indexOf(info);
  if (at !== -1) list.splice(at, 1);
}

/** Puts a stand-in on navigator.locks for this test; removeFakeLocks() takes it away again. */
export function installFakeLocks(): FakeLocks {
  const locks = new FakeLocks();
  Object.defineProperty(navigator, "locks", {
    value: locks,
    configurable: true,
  });
  return locks;
}

/** Takes the stand-in away: the browser of the other tests, with no Web Locks. */
export function removeFakeLocks(): void {
  Reflect.deleteProperty(navigator, "locks");
}
