"""backend/tests/e2e_shop.py — the made-up shop the browser tests log in to (UI-6).

It owns the rows frontend/e2e/ needs on an empty database: a shop with one side, a manager who logs in with a
password, and a seller who logs in with a PIN. scripts/run_e2e.sh runs it inside the test container, after the
migrations and before the tests, as `manage.py shell --command "<this file's text>"`.

Made through the services, as the shop's own setup makes them (set_up_shop, add_staff, assign_role, set_pin), never
by writing rows: a shop made here can't hold anything a real one couldn't, and a service that changes its rules
changes this shop with it.

Here, not in the image: it is test data. The image's build sees backend/apps and backend/config, never this folder
(Dockerfile.dockerignore), so the file is handed to the container's shell as text. As `--command`, not on stdin:
`shell` reads stdin only if it is ready the moment it looks, and would otherwise open its prompt.

It refuses to run anywhere else: only where the container marks itself as the tests' (E2E_SHOP=yes, set in
compose.e2e.yml alone) and the database holds no shop yet. The manager's password is public here, so a shop made with
it on the demo or the real server would be one anyone could log in to (test_e2e_shop.py proves both refusals).

DATA-1's demo seed (`manage.py seed_demo`) replaces this file: its card says the end-to-end tests use that seed too.

Fake data only (rule 10). The PIN and the password are written again in frontend/e2e/pair-and-pin-login.spec.ts:
change both together. If they ever differ, the test's login fails at once, so the mismatch can't hide.
"""

import os

from apps.core.permissions import RoleTemplate
from apps.core.tenancy import shop_context
from apps.people.models import Role, User
from apps.people.services import add_staff, assign_role, set_pin, set_up_shop
from apps.shops.models import Shop, Side
from apps.shops.services import NewSide

# The manager's login (an email, so the test types it as it is) and the seller's PIN. Not secrets: they open only a
# throwaway database on a test machine. 2580: four digits the PIN rules allow (apps/people/pins.py).
MANAGER_EMAIL = "meneja@example.com"
MANAGER_PASSWORD = "e2e-only-not-a-secret"
SELLER_PIN = "2580"


def refuse_unless_an_empty_test_database() -> None:
    # Both checks, before anything is written. The mark: compose.e2e.yml alone sets E2E_SHOP, so the demo (render.yaml)
    # and the real server never pass it, whoever pastes this file into their shell. No shop yet: Shop has no tenancy
    # guard (it is the shop itself, rule 1), so this looks across every shop. The tests' database is new on every
    # run, and any shop at all means a database somebody uses. SystemExit: `shell` prints the reason and stops, with
    # no traceback, and the run script stops with it.
    if os.environ.get("E2E_SHOP") != "yes":
        raise SystemExit(
            "Refused: E2E_SHOP=yes is not set. This file makes the browser tests' shop, in their own container only."
        )
    if Shop.objects.exists():
        raise SystemExit("Refused: the database already holds a shop. This file runs only on the tests' empty one.")


def make_the_shop() -> None:
    refuse_unless_an_empty_test_database()
    # The shop, its side with its stock place and cash drawer, and its own copy of the six roles (set_up_shop).
    shop = set_up_shop(name="Duka la Majaribio", code="JARIBIO", sides=[NewSide("D", "Dawa")])
    # create_user first: a person's account has no shop (rule 1). Then their job, inside the shop, because the
    # services' checks read through the tenancy guard (ADR-0037), as conftest.py's staff fixtures do.
    manager = User.objects.create_user(full_name="Meneja Mfano", email=MANAGER_EMAIL, password=MANAGER_PASSWORD)
    # No password: Asha logs in only with her PIN, at the shop's laptop, as a seller does (create_user then stores a
    # password nothing can match).
    seller = User.objects.create_user(full_name="Asha Mfano")
    with shop_context(shop):
        dawa = Side.objects.get(code="D")
        # by=None everywhere: the system sets the shop up, not one of its people, so no giver is named (02 §1).
        meneja = add_staff(shop=shop, user=manager, display_name="Meneja", by=None)
        asha = add_staff(shop=shop, user=seller, display_name="Asha", by=None)
        # The manager on every side, as a shop's manager is: device.manage among the role's keys lets them confirm
        # a laptop's code on its home side (confirm_pairing). Asha sells on Dawa only.
        assign_role(meneja, Role.objects.get(template=RoleTemplate.MANAGER), side=None, by=None)
        assign_role(asha, Role.objects.get(template=RoleTemplate.SELLER), side=dawa, by=None)
        set_pin(asha, SELLER_PIN, by=None)
    # One line in the run's output, so a failed test's log shows the shop was made. Names only: no PIN, no password.
    print(f"e2e shop ready: {shop.name}, with {meneja.display_name} and {asha.display_name}")


# Called here, not under `if __name__ == "__main__"`: `shell --command` runs this text with the shell's own names,
# where __name__ is not "__main__".
make_the_shop()
