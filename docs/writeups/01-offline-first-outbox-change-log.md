# Offline-first with an outbox and a commit-ordered change log

*First draft, 15 November 2026. How MPC's shop laptops keep working with no internet, and why a record made offline reaches the server once: never lost, never counted twice.*

## The problem

MPC is a family agro-vet shop in Usa River, near Arusha in Tanzania. The power goes out often, and the Wi-Fi router goes with it. In a long cut, the mobile network goes down too. The counter, where staff serve customers, can't stop when that happens: a worker still arrives and clocks in, and a customer still buys a sack of feed. So the app saves work on the laptop itself, and sends it to the server when the internet comes back.

That raises three questions:

1. The laptop sends a record, and the connection drops before the answer comes. Did it arrive? If the laptop sends it again, the server must not keep it twice. A clock-in counted twice is a wrong wage; a sale counted twice is wrong money.
2. Records from one laptop must be saved in the order they were made, even when they arrive hours late.
3. The office changes things while the laptop is offline: a new worker, a suspended one, later a new price. The laptop must learn every change, once, and never miss one.

The GIF in the [README](../../README.md) shows the answer from the outside. This page shows how it works inside.

## Two directions, two kinds of data

The key choice ([ADR-0020](../adr/0020-sync-push-documents-pull-changes.md)) is to split the data by who writes it:

- **Facts made at the counter** (a clock-in today; sales and payments later) are made on one laptop and never edited. They go **up**: the laptop *pushes* them.
- **Reference data** (staff, settings and the shop's *sides*, its sections, each with its own stock, cash drawer and staff, such as Dawa for drugs and Vyakula for foods; products and prices later) is edited only in the office, online. It comes **down**: the laptop *pulls* the changes.

Each kind of data has one writer, so two copies never need merging. I don't need last-write-wins, or CRDTs (data structures that merge edits made in two places). They solve a problem this shop doesn't have, and in a money system "last write wins" means a record quietly lost.

```
 the laptop                                  the server
 ┌───────────────┐   push: records       ┌──────────────────┐
 │ outbox        │ ────────────────────▶ │ answer log       │
 │ (to send)     │ ◀──────────────────── │ + the save       │
 │               │   one answer each     │                  │
 │ copies of the │ ◀──────────────────── │ change log       │
 │ office's data │   pull: changes       │ (numbered)       │
 └───────────────┘   after number N      └──────────────────┘
```

The two logs on the server, the answer log and the change log, are explained below.

## Up: the outbox

The laptop keeps its data in IndexedDB, the browser's own database, through Dexie ([ADR-0019](../adr/0019-offline-data-lives-in-indexeddb-through-dexie.md)). A clock-in is saved in **one** transaction: a group of writes where either all of them happen or none does ([`outbox.ts`](../../frontend/src/offline/outbox.ts)):

1. the record itself (in the code, a *document*), with a new id made on the laptop: a UUIDv7, a long random id that also sorts by time, so two laptops never make the same one;
2. its row in the **outbox**, the list of records still to send;
3. the laptop's next number for it, its `device_seq`: 1, 2, 3…

Once that transaction commits, the record exists, even if the tab closes a moment later. The screen says *Kumbukumbu 1 inasubiri kutumwa*: one record waiting to be sent.

A sync loop sends what waits. It runs when the app starts, when the network comes back, 2 seconds after a save, every 30 seconds while online, and when someone taps *Tuma sasa* (send now). Only one tab sends at a time: the tabs take turns through a Web Lock, a lock the browser itself keeps. In Chrome and Edge, Background Sync lets the service worker (the app's background script, which the browser can wake on its own) send even after the app is closed.

## The push, and why sending twice is safe

The laptop sends up to 100 waiting records, in `device_seq` order. The server ([`push.py`](../../backend/apps/sync/push.py)) saves each one in its own database transaction, and answers each one:

| Answer | Meaning | The laptop… |
|---|---|---|
| `accepted` | saved now | moves it from the outbox to its archive |
| `duplicate` | saved before; here is the first answer again | reads it as that first answer |
| `invalid` | broken, or a type that can't be made offline | sets it aside, so a manager sees it |
| `retry` | the server's own trouble | stops, keeps the rest in order, tries again later |

The safety comes from the **answer log**: one line per record id, written in the same transaction as the record. The id is made once, when the laptop saves the record, so every resend carries the same id. A record sent a second time finds its line, and gets `duplicate` with its first answer. So when in doubt, the laptop just sends again. The connection can drop before the request, during the save, or after the save but before the answer: the worst case is one extra `duplicate`.

A `retry` stops the batch there, so the records after it never jump ahead. After a failed push, the laptop waits 30 seconds, then twice as long each time, up to 5 minutes.

One rule matters most: **a fact made offline is never refused for breaking a business rule.** Say the manager suspends Juma, and a laptop that hasn't synced yet lets him clock in. That clock-in still happened. The server accepts it and raises a **flag** for the manager to look at. Refusing it would only hide it.

## Down: the change log, and the late-commit trap

The laptop learns about the office's changes with a cursor, the number of the last change it has: "give me every change after number 41."

Every service that changes something a laptop keeps also writes a line in the shop's **change log**, in the same transaction: the shop, a number, the table and the record's id. The pull returns the lines after the cursor, each with its record as it is now ([`pull.py`](../../backend/apps/sync/pull.py)).

The trap is *when* a save takes its number. Take it at the start, and a slow save can commit after a faster one:

```
numbered at the start (wrong)            numbered at the end (what MPC does)
Juma's save starts, takes 42             Juma's save starts
Asha's save starts, takes 43             Asha's save starts
Asha's save commits (43)                 Asha's save ends: takes 42, commits
  a laptop pulls; its cursor is now 43   Juma's save ends: takes 43, commits
Juma's save commits (42): never pulled     a laptop pulls 42, then 43
```

On the left, the laptop has moved past 43 by the time 42 appears. It never asks for 42 again, so that laptop misses Juma's change for good. A PostgreSQL sequence, or an auto-increment id, has exactly this problem: it hands out a number at once and never waits for the commit.

So each save takes its numbers as its last step, from one numbering row per shop, which stays locked until the commit ([`changes.py`](../../backend/apps/core/changes.py), [`sequences.py`](../../backend/apps/core/sequences.py)). The shop's next save waits for that last moment, then takes the numbers after. The numbers appear in commit order, so a cursor can never skip one.

The cost: one shop's saves queue up for the last moment of each transaction. For a shop with a few laptops, the wait is small. Each shop has its own numbering row, so shops never wait for each other.

Two smaller choices keep the pull simple:

- The log holds no data, only which record changed. The pull reads the record as it is now. A record changed twice comes down twice, each time as it is now, which does no harm.
- A new laptop starts with a **bootstrap**: a copy of everything, plus the number it is valid up to. That number is read first, so a change that commits while the copy is read comes again in the next pull.

## Not counting twice on the laptop

When selling comes, a sale made offline must lower the stock on the laptop's screen at once, before the server knows about it. The laptop keeps that as a **pending effect**. When the server accepts the sale, its answer carries `posted_seq`, the change-log number its save got. Once the laptop's cursor reaches that number, the server's stock already includes the sale, and the laptop drops its pending effect. So the screen never subtracts the sale twice, or forgets it. This part is built and tested today: the sale will be the first record to use it.

## How I know it works

Tests prove each rule:

- `test_change_numbers_follow_commit_order` and `test_late_numbers_wait_for_the_shops_last_commit` run two real PostgreSQL transactions side by side, and check the numbers they get; `test_shops_do_not_block_each_other` checks that two shops never wait for each other ([`test_change_order.py`](../../backend/apps/core/tests/test_change_order.py)).
- `test_bootstrap_cursor_consistent` renames a side at the very moment a new laptop asks for its copy, and checks that the copy and its number agree ([`test_bootstrap.py`](../../backend/apps/sync/tests/test_bootstrap.py)).
- `test_same_batch_twice_posts_once`, `test_posts_in_device_seq_order` and `test_server_error_answers_retry` cover the push ([`test_push.py`](../../backend/apps/sync/tests/test_push.py)).
- `test_suspended_worker_clock_in_flagged` is Juma's case above: suspended, he clocks in on a laptop that hasn't heard, and the server accepts it and flags it ([`test_clock_in.py`](../../backend/apps/sync/tests/test_clock_in.py)).
- On the laptop, Vitest checks that a save is all or nothing ([`outbox.save.test.ts`](../../frontend/src/offline/outbox.save.test.ts)), that the push stops at a `retry` and keeps the rest in order ([`push.loop.test.ts`](../../frontend/src/offline/sync/push.loop.test.ts)), and that a pull drops the pending effects its cursor has reached ([`pull.apply.test.ts`](../../frontend/src/offline/sync/pull.apply.test.ts)).
- On every pull request, an end-to-end test drives a real browser ([`clock-in-offline.spec.ts`](../../frontend/e2e/clock-in-offline.spec.ts)): internet off, clock in, reload, still there, internet on. The server answers `accepted` exactly once, and the same push sent again answers `duplicate`.

## Trade-offs, and what's next

- **Flags need people.** Accepting offline facts means a manager reviews the flags they raise. That is part of the office's job, by design.
- **A restored server is behind its laptops.** If the server is restored from last night's backup, it has lost the newest records, but the laptops still hold them: each keeps its sent records in an archive. Sending them again is safe, thanks to the answer log. The change log's numbers go back too, so a laptop's cursor can sit ahead of them, and its pulls would skip every new change up to it. How each laptop starts again (probably a fresh bootstrap, once its outbox is sent), the resend, and clearing the archive after 30 days are a later task (OPS-11).
- **Background Sync is Chrome and Edge only, and it gives up.** The shop's devices are supported on Chrome or Edge only. Even there, with the app closed, the browser tries about three times over some 20 minutes, then waits until the app is opened or another record is saved. In Firefox and Safari, records leave only while the app is open.
- **The change log only grows.** Nothing can delete its lines (it is append-only), so how to compact it is a decision for later.

Next, this runs on a real server; after that, the same two pipes carry sales, payments and debts.
