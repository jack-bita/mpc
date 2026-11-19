"""apps/people/management/commands/owner.py — `manage.py owner add`: the superuser makes a shop's owner (PPL-13).

Nobody in a shop may make someone Owner or set the Owner's PIN (ADR-0038, PPL-7): whoever holds the Owner role can be
stopped only by the superuser, so a manager who could make a friend Owner could no longer be stopped by the owner. The
superuser is nobody's worker, so no office page serves him, and the admin opens no shop's rows (parking lot item 15).
So he types it on the server:

    python manage.py owner add --shop MPC

It asks the nickname first, as the PIN tiles show it. Someone already working there by that name is given the Owner
role on every side, after a yes. Anyone new: their full name, phone (may be empty) and PIN, typed twice and never
shown; then, after a yes, the person and their job (add_worker), the Owner role on every side (assign_role) and the PIN
(set_pin), all or nothing.

Thin, like a view (ADR-0043): it asks, shows, and calls the services as they are; every rule is theirs (the card's
Watch out). The superuser acts as `by=None`, as the system does: each service's rules for the superuser hold (a taken
phone, the PIN's strength, role.already_given), and the edit history names nobody, as for the demo seed.
"""

from argparse import ArgumentParser
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from apps.core.changes import recording_changes
from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.management.asking import Asker, find_shop, refuse_on_demo, refused
from apps.people.models import Role, StaffMember, StaffStatus
from apps.people.services import add_worker, assign_role, set_pin
from apps.shops.models import Shop


class Command(BaseCommand):
    help = (
        "The superuser's way to set up a shop's owner, as nobody in the shop may (PPL-7). "
        "`add`: make someone the Owner on every side, with their PIN. Refused on the demo."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        # One subcommand for each thing done to the owner, as `git commit` and `git push`: `owner add`. Required: the
        # bare `owner` does nothing.
        actions = parser.add_subparsers(dest="action", required=True, metavar="add")
        add = actions.add_parser("add", help="make someone the shop's Owner on every side, with their PIN")
        # The shop by its code, as open_shop printed it. No --pin, ever (the card's default): the PIN is typed, unseen.
        add.add_argument("--shop", required=True, help="the shop's code, as MPC")

    def handle(self, *args: Any, **options: Any) -> None:
        # The demo first, before even the shop is read (the card's default).
        refuse_on_demo()
        shop = find_shop(options["shop"])
        ask = Asker(self.stdout)
        # The shop opened for everything below, never every shop (system_context(), rule 1): each service's reads go
        # through the tenancy guard, which then shows this shop's rows alone.
        with shop_context(shop):
            self._add(ask, shop)

    def _add(self, ask: Asker, shop: Shop) -> None:
        nickname = ask.text("Nickname, as the PIN tiles show it")
        # A current worker by that nickname, in any letter case, as the nickname's own rule reads it: one at most among
        # those who haven't left (people_staffmember_nickname_unique). One who left is history: a new person is asked.
        here = (
            StaffMember.objects.select_related("user")
            .filter(display_name__iexact=nickname)
            .exclude(status=StaffStatus.LEFT)
            .first()
        )
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

    def _add_owner(self, ask: Asker, shop: Shop, nickname: str, owner: Role) -> None:
        full_name = ask.text("Full name")
        # Optional, as on the office's form (PPL-10). Checked and stored in one form (+255…) by add_worker.
        phone = ask.text("Phone, or Enter for none", optional=True)
        pin = ask.pin()
        # Everything once more before the yes (Jack, PPL-13: 1A). Never the PIN.
        ask.say(f"New at {shop.code}: {full_name}, nickname {nickname}, phone {phone or 'none'}.")
        ask.say("They get: the Owner role on every side, and the PIN just typed.")
        if not phone:
            # Jack, PPL-13: 3A. Allowed, as the PIN works without one; but a password logs in by phone or email, so the
            # admin's temporary password, the runbook's next step, would be refused (password.no_login_name).
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
