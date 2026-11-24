"""apps/people/management/commands/owner.py — `manage.py owner`: the superuser sets up a shop's owner (PPL-13).

Nobody in a shop may make someone Owner or set the Owner's PIN (ADR-0038, PPL-7): whoever holds the Owner role can be
stopped only by the superuser, so a manager who could make a friend Owner could no longer be stopped by the owner. The
superuser is nobody's worker, so no office page serves him, and the admin opens no shop's rows (parking lot item 15).
So he types it on the server, one subcommand for each thing done:

    python manage.py owner add --shop MPC
    python manage.py owner set-pin --shop MPC --nickname Baba
    python manage.py owner take --shop MPC --nickname Baba

- `add` asks the nickname first, as the PIN tiles show it. Someone already working there by that name is given the
  Owner role on every side, after a yes. Anyone new: their full name, phone (may be empty) and PIN, typed twice and
  never shown; then, after a yes, the person and their job (add_worker), the Owner role on every side (assign_role) and
  the PIN (set_pin), all or nothing.
- `set-pin` asks a new PIN twice, and set_pin lifts any lock on every device and ends the logins made with the old PIN
  (AUTH-4). For any current worker of the shop (the card's default): the superuser may help anyone when no manager is
  there, and only he may set an owner's (set_pin: pin.superuser_only).
- `take` asks the reason, and ends every Owner role the person holds (end_role), together, with that one reason (Jack,
  PPL-13: 4A). When no other Owner is working there, it asks once more (the card's default): only the superuser can
  make one again, and the owner's own keys stay only with someone given them one by one.

Thin, like a view (ADR-0043): it asks, shows, and calls the services as they are; every rule is theirs (the card's
Watch out). The superuser acts as `by=None`, as the system does: each service's rules for the superuser hold (a taken
phone, the PIN's strength, role.already_given), and the edit history names nobody, as for the demo seed.
"""

import shlex
from argparse import ArgumentParser
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.core.changes import recording_changes
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.management.asking import Asker, find_shop, refuse_on_demo, refused
from apps.people.models import Role, RoleAssignment, StaffMember, StaffStatus
from apps.people.services import add_worker, assign_role, end_role, set_pin
from apps.shops.models import Shop


class Command(BaseCommand):
    help = (
        "The superuser's way to set up a shop's owner, as nobody in the shop may (PPL-7). "
        "`add`: make someone the Owner on every side, with their PIN. "
        "`set-pin`: give a worker a new PIN. `take`: take the Owner role away, with a reason. Refused on the demo."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        # One subcommand for each thing done to the owner, as `git commit` and `git push`. Required: the bare `owner`
        # does nothing.
        actions = parser.add_subparsers(dest="action", required=True, metavar="add|set-pin|take")
        # Named for what they read, not `set_pin`, which would hide the service of that name in this method.
        adding = actions.add_parser("add", help="make someone the shop's Owner on every side, with their PIN")
        setting_pin = actions.add_parser("set-pin", help="give a current worker of the shop a new PIN")
        taking = actions.add_parser("take", help="take the Owner role away from someone, with a reason")
        for action in (adding, setting_pin, taking):
            # The shop by its code, as open_shop printed it. No --pin, ever (the card's default): the PIN is typed,
            # unseen.
            action.add_argument("--shop", required=True, help="the shop's code, as MPC")
        for action in (setting_pin, taking):
            action.add_argument("--nickname", required=True, help="the worker's nickname, as the PIN tiles show it")

    def handle(self, *args: Any, **options: Any) -> None:
        # The demo first, before even the shop is read (the card's default).
        refuse_on_demo()
        shop = find_shop(options["shop"])
        ask = Asker(self.stdout)
        # The shop opened for everything below, never every shop (system_context(), rule 1): each service's reads go
        # through the tenancy guard, which then shows this shop's rows alone.
        with shop_context(shop):
            if options["action"] == "add":
                self._add(ask, shop)
                return
            staff = _working_here(options["nickname"])
            if staff is None:
                raise CommandError(f"Nobody working at {shop.code} has the nickname {options['nickname']}.")
            if options["action"] == "set-pin":
                self._set_pin(ask, shop, staff)
            else:
                self._take(ask, shop, staff)

    def _add(self, ask: Asker, shop: Shop) -> None:
        nickname = ask.text("Nickname, as the PIN tiles show it")
        here = _working_here(nickname)
        # The shop's own Owner role, one per shop (role.template_taken), copied in when the shop was opened.
        owner = Role.objects.get(template=RoleTemplate.OWNER)
        if here is not None:
            self._make_owner(ask, shop, here, owner)
        else:
            self._add_owner(ask, shop, nickname, owner)

    def _make_owner(self, ask: Asker, shop: Shop, staff: StaffMember, owner: Role) -> None:
        # Someone already working here: the role alone (the card). Their PIN and phone stay as they are.
        ask.say(f"{staff.user.full_name} already works at {shop.code} as {staff.display_name} ({staff.status}).")
        ask.say("They get: the Owner role on every side.")
        if not ask.yes("Make them the Owner?"):
            ask.say("Nothing written.")
            return
        try:
            # One service, in its own block: nothing to join.
            assign_role(staff, owner, side=None, by=None)
        except ValidationError as error:
            raise refused(error) from None
        ask.say(f"{staff.display_name} is now {shop.code}'s Owner on every side.")
        if not staff.pin_hash:
            # No tile on the shop's laptops without a PIN: set-pin gives one.
            # Quoted as the shell needs it, so the line can be copied as it is: a nickname with a space (Mama Juma),
            # common in Swahili, would otherwise be split in two, and argparse would refuse the second word.
            nickname = shlex.quote(staff.display_name)
            ask.say(f"No PIN yet: python manage.py owner set-pin --shop {shop.code} --nickname {nickname}")

    def _add_owner(self, ask: Asker, shop: Shop, nickname: str, owner: Role) -> None:
        full_name = ask.text("Full name")
        # Optional, as on the office's form (PPL-10). Checked and stored in one form (+255…) by add_worker.
        phone = ask.text("Phone, or Enter for none", optional=True)
        pin = ask.pin()
        # Everything once more before the yes (Jack, PPL-13: 1A). Never the PIN.
        ask.say(f"New at {shop.code}: {full_name}, nickname {nickname}, phone {phone or 'none'}.")
        ask.say("They get: the Owner role on every side, and the PIN just typed.")
        if not phone:
            # Jack, PPL-13: 3A. Allowed, as the PIN works without one. But a password logs in by phone or email, and the
            # admin's form, the runbook's next step, takes a temporary password all the same and asks for neither:
            # he could never log in with it. The office's own route refuses that (password.no_login_name); the admin
            # doesn't (PPL-13's review). So the warning comes here, before the yes.
            ask.say("No phone: they can't log in with a password until a phone or an email is added in the admin.")
        if not ask.yes("Make them the Owner?"):
            ask.say("Nothing written.")
            return
        try:
            # One block for the three services, which each join it (backend rule: code that calls more than one saving
            # service opens the block itself): a PIN refused at the end takes back the person, the job and the role too.
            # The lines for the shop's laptops are numbered once, at the block's end (SYNC-1).
            with recording_changes(shop):
                staff = add_worker(shop=shop, full_name=full_name, display_name=nickname, phone=phone or None, by=None)
                assign_role(staff, owner, side=None, by=None)
                set_pin(staff, pin, by=None)
        except ValidationError as error:
            raise refused(error) from None
        ask.say(f"{nickname} is now {shop.code}'s Owner on every side, with a PIN.")
        # The tile comes with the staff line set_pin wrote (pin_changed_at), at each laptop's next sync (SYNC-15).
        ask.say("Their tile shows on the shop's laptops after each one's next sync.")
        ask.say("Next, for their phone: a temporary password in the admin (docs/runbooks/open-a-shop.md).")

    def _set_pin(self, ask: Asker, shop: Shop, staff: StaffMember) -> None:
        # Who, before the PIN is typed: a nickname mistyped as another worker's shows here. The PIN typed twice is the
        # yes: no other question.
        ask.say(f"A new PIN for {staff.user.full_name}, {staff.display_name} at {shop.code} ({staff.status}).")
        pin = ask.pin()
        try:
            # One service: it locks the person, refuses one who left (staff.left), and lifts every lock (AUTH-4).
            set_pin(staff, pin, by=None)
        except ValidationError as error:
            raise refused(error) from None
        ask.say(f"{staff.display_name} has a new PIN. Any lock from wrong tries is lifted, on every device.")
        # pin_changed_at moved: each laptop drops its offline check of the old PIN at its next sync, and a login made
        # with the old PIN ends at its next visit (AUTH-4).
        ask.say("Logins made with the old PIN have ended; the shop's laptops take the new one at their next sync.")

    def _take(self, ask: Asker, shop: Shop, staff: StaffMember) -> None:
        # Every Owner row the person holds, on every side and on one: all of them end, so nothing of the Owner's is left
        # (Jack, PPL-13: 4A). Read with the shop open: the guard shows this shop's rows alone.
        rows = list(
            RoleAssignment.objects.select_related("side")
            .filter(staff=staff, role__template=RoleTemplate.OWNER, ended_at=None)
            .order_by("created_at")
        )
        if not rows:
            raise CommandError(f"{staff.display_name} holds no Owner role at {shop.code}.")
        sides = ", ".join("every side" if row.side is None else f"{row.side.name}" for row in rows)
        ask.say(f"{staff.user.full_name}, {staff.display_name} at {shop.code}, is Owner on: {sides}.")
        # Rule 7: an end is always kept with who, when and why. Blank is asked again; end_role refuses it too.
        reason = ask.text("Why is it taken away")
        if not _another_owner_working(staff) and not self._last_owner_agreed(ask, shop):
            ask.say("Nothing written.")
            return
        try:
            # One block for every row (backend rule: more than one saving call opens the block itself): the rows end
            # together, or none does, and the person's staff line is numbered once, at the end.
            with recording_changes(shop):
                for row in rows:
                    end_role(row, reason=reason, by=None)
        except ValidationError as error:
            raise refused(error) from None
        ask.say(f"{staff.display_name} no longer holds the Owner role at {shop.code}; their job and PIN stay.")
        ask.say("Their laptops drop the Owner's keys at their next sync.")

    def _last_owner_agreed(self, ask: Asker, shop: Shop) -> bool:
        # Asked once more (the card's default). With no other Owner working, nobody there may give the role again: only
        # the superuser can (role.superuser_only). And the owner's own keys (the day's final approval, the pay, the
        # shop's rules, who works there, the meal money; spec §6) stay only with someone given them one by one, as a
        # manager may be (apps/core/permissions.py): so the words claim no more than that. "No other": true whether the
        # person taken is working or suspended (PPL-13's review).
        ask.say(f"No other Owner is working at {shop.code}.")
        ask.say("Once taken, only the superuser can make one again,")
        ask.say("and the owner's own keys stay only with someone given them one by one.")
        return ask.yes("Take it all the same?")


def _working_here(nickname: str) -> StaffMember | None:
    # A current worker of the open shop by that nickname, in any letter case, as the nickname's own rule reads it: one
    # at most among those who haven't left (people_staffmember_nickname_unique). One who left is history: `add` asks
    # for a new person, and `set-pin` and `take` find nobody, as set_pin and end_role would refuse them (staff.left).
    return (
        StaffMember.objects.select_related("user")
        .filter(display_name__iexact=nickname.strip())
        .exclude(status=StaffStatus.LEFT)
        .first()
    )


def _another_owner_working(staff: StaffMember) -> bool:
    # Someone else at the shop who is working (not suspended, not gone) and holds an open Owner role. A suspended Owner
    # doesn't count: suspended, they hold nothing until brought back (apps/people/permissions.py; Jack, PPL-13: 4A).
    # Only the question to ask hangs on this, never a rule: the superuser alone types these commands, so nothing else
    # changes the shop's Owners meanwhile, and the rows are read again, and locked, by end_role.
    return (
        RoleAssignment.objects.filter(
            role__template=RoleTemplate.OWNER, ended_at=None, staff__status=StaffStatus.ACTIVE
        )
        .exclude(staff=staff)
        .exists()
    )
