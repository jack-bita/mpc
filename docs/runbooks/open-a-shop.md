# Runbook — open a shop and make its owner

**What:** a new real shop on the production server, and its owner: the person who holds the Owner role on every side, with a PIN for the shop's laptops and a password for his phone. Nobody in a shop may make someone Owner or set the Owner's PIN (ADR-0038, PPL-7), so the superuser does it, typed on the server (PPL-13).
**When:** once for each new shop, before its first go-live (LIVE-1 for MPC, §16 of the build plan). Also when an owner forgets his PIN or password, or the shop changes hands (*Later*, below).
**Files:** `backend/apps/people/management/commands/open_shop.py` (the shop), `backend/apps/people/management/commands/owner.py` (its owner), `backend/apps/people/management/asking.py` (how both ask and refuse). Each file's header explains it.

Two words used below:
- **Management command:** a small program that comes with the backend and runs inside its container: `python manage.py <name>`. It works with the database directly, with no web page.
- **Superuser:** the one account that can open the admin (`/admin/`), made once on each server with `createsuperuser`. Nobody's worker, in no shop.

## Before you start

- The server is running, with its migrations applied, and a restore has been tested (stage 3; §16, *Every go-live*).
- You can log in to the admin as the superuser.
- You have, from the owner, face to face: the shop's name, a short code for it (MPC), each side's letter and name, how each side sells, and the owner's full name, nickname, phone number and the PIN he wants. The owner types his own PIN himself, on your keyboard, if he is there.

**On the server**, each command runs inside the backend's container. The file and service names come with OPS-5 (`compose.prod.yml`); if they differ from these, OPS-5 changes this runbook:

```
docker compose -f compose.prod.yml exec backend python manage.py <command>
```

Never add `-T` to `exec`: the PIN is read with the screen's echo off, which needs a terminal. Every answer is asked one at a time. `open_shop` and `owner add` write nothing until you type `y` at the end. `owner set-pin` and `owner take` ask no final yes: typing the PIN twice, or the reason, is the yes, so check the name each one shows first. Ctrl-C stops a command before its last answer, and writes nothing.

**To rehearse on the laptop**, only on a database you then throw away: a shop is never deleted (rule 7), and the demo seed refuses for good a database that holds a real one, so `make seed` and the local one-tap demo stop working. With made-up names, the local stack running (`make dev`) and the database migrated: `cd backend && uv run --env-file ../.env python manage.py <command>`. Afterwards, wipe the laptop's database and start again: `docker compose -f compose.dev.yml down -v` (it deletes the database volume), `make dev`, `make migrate`, `make seed`. The demo refuses both commands (`DEMO_SEED=yes`): its seed makes its own shop and people.

## The steps, in order

**1. Open the shop.** `open_shop`

It asks the shop's name and code (2 to 10 capital letters), then each side: its letter, its name, its band (`blue` or `striped`) and how it sells (`one`: one screen; `three`: writer, cashier and loader). After each side, `Another side? [y/N]`. Then it shows everything once more.

Check the letters before you answer `y`. **A side's letter never changes:** it starts every number printed on that side's receipts (D2-0457). A name can be fixed later; a letter can't.

It makes the live shop, its sides, each side's stock place and cash drawer, and the shop's six roles, all or nothing. It prints the shop's code and id, and the next command.

**2. Make its owner.** `owner add --shop MPC`

It asks the nickname first, as the PIN tiles will show it (Baba). Then the full name, the phone (Enter for none), and the PIN twice, which nothing shows. Two PINs that differ, or one too easy to guess (`pin.too_easy`, `pin.not_four_digits`), are asked again at once. It shows everything but the PIN, and asks for a yes.

It makes the person and his job, gives him the Owner role on every side, and sets his PIN, all or nothing. His tile shows on each of the shop's laptops after its next sync.

Give him a phone: a password logs in by phone or by email. With neither, the admin still takes the password in step 3, but he can never log in with it. The command warns before the yes.

If the nickname is someone already working at the shop, it gives them the Owner role alone, after a yes; their phone and PIN stay. With no PIN yet, it names `owner set-pin` to run next.

**3. A temporary password for his phone.** In the admin.

*People* → *Users* → the owner → under *Password*, *Set password* (*Reset password* once he has one). Type a temporary password twice and save. Tell it to him face to face (ADR-0038). Nobody in the shop can set the owner's password: only the superuser (`password.superuser_only`).

**4. He logs in on his phone.** At the app's address, *Ingia*: his phone number and the temporary password. The app asks him to choose his own at once (AUTH-6), and the temporary one stops working.

**5. He switches the sides on.** *Mipangilio ya duka* → *Pande*. Every new side starts switched off, so nothing reaches the counters by surprise (ADR-0033). He switches each one on when the shop starts using it.

**6. Then LIVE-1's own steps**, in §16 of the build plan: attendance switched on from the 1st and both fines typed, the laptops paired on *Vifaa*, each worker logged in once on each clock-in laptop.

## Later

| What happened | What to run |
|---|---|
| The owner forgot his PIN, or is locked out by wrong tries | `owner set-pin --shop MPC --nickname Baba`: the PIN twice. It lifts his lock on every device, and logins made with the old PIN end. It works for any current worker, when no manager is there to help. |
| The owner forgot his password | Step 3 again. |
| The shop changes hands | `owner add` for the new owner (steps 2 to 4), then `owner take` for the old one. |
| Someone should no longer be Owner | `owner take --shop MPC --nickname Baba`: the reason. It ends every Owner role he holds, on every side, as soon as the reason is typed; his job and PIN stay. When no other Owner is working at the shop, it asks once more: once taken, only the superuser can make one again. |
| A typo in the shop's name or code | The admin's shop page fixes both. |
| A typo in a side's name, or a side missing | No screen renames or adds a side yet (parking lot item 29): check every side before the yes. |
| A wrong side's letter | It never changes. Nothing is deleted (rule 7), so leave that side switched off; a right one can be added once a screen does it (item 29). |

A nickname with a space goes in quotes: `--nickname 'Mama Juma'`.

The admin has no *Add shop*: a shop made there had no sides, drawers or roles, so nobody could work in it. `open_shop` is the only way.

## When a command refuses

A refusal prints `Refused, nothing written:` and one line for each reason: its code, the field it is about if any, and its words. The command stops, and every step it was taking is undone. Fix the answer and run it again.

| Code | Means |
|---|---|
| `shop.code_taken` | Another shop has this code. |
| `shop.code_invalid` · `side.code_invalid` | A shop's code is 2 to 10 capital letters; a side's letter is one. |
| `side.code_taken` | Two sides were given the same letter. |
| `unique (phone)` | This phone belongs to another person, maybe at another shop: a person at two shops waits for AUTH-7. |
| `phone.invalid` | Not a phone number. |
| `staff.left_here` | This phone is of a worker who left the shop: they are hired again from the workers' page (*Mwajiri tena*), and then made Owner with `owner add`. |
| `role.already_given` | They are Owner on every side already. |
| `staff.temporary_password_open` | Someone without the Owner's keys set this person's temporary password, which is still open: the person logs in and chooses their own first. A new one set in the admin doesn't clear it, as it leaves the first setter's line in the audit trail, which fails safe. |
| `No shop has the code …` · `Nobody working at … has the nickname …` | A typo, or a worker who has left. |
