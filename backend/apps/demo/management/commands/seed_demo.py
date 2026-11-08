"""apps/demo/management/commands/seed_demo.py — `manage.py seed_demo`: makes the demo shop, or keeps today's (DATA-1).

Thin, like a view (ADR-0015): the seed itself, its refusals and the reason it wipes the database are in
apps/demo/services.py. This file only reads `--fresh`, turns a refusal into the command's error, and prints one line
at the start and one at the end (ops rule: a job logs its start and end). Neither line holds a name, an email, a PIN or
the password (privacy rule): only what was done, and how many people the shop has.

    DEMO_SEED=yes python manage.py seed_demo            the demo's start: keeps a demo shop made today
    DEMO_SEED=yes python manage.py seed_demo --fresh    makes it again anyway (`make seed` on a laptop)
"""

from argparse import ArgumentParser
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.demo.services import PEOPLE, Seeded, seed_demo


class Command(BaseCommand):
    help = (
        "Wipe a database that holds only demo data and make the demo shop again (needs DEMO_SEED=yes). "
        "Keeps a demo shop made today, unless --fresh."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--fresh", action="store_true", help="make the demo shop again even if it was made today")

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write("demo seed: start")
        try:
            done = seed_demo(fresh=options["fresh"])
        except ValidationError as refused:
            # CommandError: Django prints the reason on its own, with no traceback, and the command exits with 1, so
            # a start script that runs it (`set -e`) stops there instead of serving a database it shouldn't.
            raise CommandError(" ".join(refused.messages)) from None
        if done is Seeded.KEPT:
            self.stdout.write("demo seed: kept today's demo shop")
        else:
            self.stdout.write(f"demo seed: made the demo shop, with {len(PEOPLE)} people")
