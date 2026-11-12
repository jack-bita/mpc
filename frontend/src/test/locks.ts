// locks.ts — a stand-in for the browser's Web Locks (navigator.locks), which jsdom lacks: a test plays
// another tab holding a shop's sync lock, and sees this tab's sync wait for it (SYNC-9). Tests only.
//
// It does what the sync needs of the real one, nothing more: request(name, work) gives the lock to one at
// a time, in the order asked, and hands it on once the work ends, however it ended; the answer is the
// work's own. No modes, no options and no steal: the sync asks for none.

type Work = (lock: Lock | null) => unknown;

export class FakeLocks {
  // The end of each lock's line: the next to ask waits for it.
  private readonly lines = new Map<string, Promise<void>>();

  request(name: string, work: Work): Promise<unknown> {
    const before = this.lines.get(name) ?? Promise.resolve();
    const done = before.then(() => work({ name, mode: "exclusive" }));
    // Handed on however the work ended: a failed sync must not hold the lock.
    const handedOn = done.then(nothing, nothing);
    this.lines.set(name, handedOn);
    return done;
  }

  /**
   * Another tab takes the lock and holds it until the test lets it go: `release` ends its work, and
   * `granted` says when it got the lock.
   */
  holdInAnotherTab(name: string): {
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
    void this.request(name, () => {
      granted();
      return held;
    });
    return { granted: got, release: () => release() };
  }
}

function nothing(): void {}

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
