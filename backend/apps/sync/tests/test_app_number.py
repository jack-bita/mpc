"""apps/sync/tests/test_app_number.py — the app a server ships with is never too old for it (SYNC-13; 03 §6.8).

Every pull page carries the lowest app number that may still sync (`MIN_APP_VERSION`, config/settings/base.py), and a
laptop whose own number (`APP_NUMBER`, frontend/src/lib/version.ts) is lower stops pulling, sends what it holds, and
updates. Both are built into one image, so the app the server hands out must always be new enough: a release that
raised the minimum and forgot the app's own number would send every laptop round in updates that never end, and stop
every shop's pulls. Two numbers in two languages, kept in step by this test, which reads the app's from its file.

The lists a laptop keeps a copy of are kept in step with both numbers too. A release that adds a list to the registry
(CAT-6's products, STK-2's stock, DEBT-3's customers) must raise both, as an older app has no drawer for it: the app's,
so the app that ships has the drawer, and the server's minimum, so an older app's pull or bootstrap stops (AppTooOld),
and the older app sends what it holds and updates, never moving its cursor past the new list's lines. Forgetting either
is a test that fails here, not a note someone has to find.
"""

import re
from pathlib import Path

from django.conf import settings

from apps.sync.registry import REGISTRY

# The app's files, beside backend/ in the repo, as CI's backend job checks it out whole.
FRONTEND = Path(settings.BASE_DIR).parent / "frontend" / "src"
APP_VERSION_FILE = FRONTEND / "lib" / "version.ts"
PULL_FILE = FRONTEND / "offline" / "sync" / "pull.ts"

# The lists each app number keeps, in the registry's order. A release that adds one raises APP_NUMBER and
# MIN_APP_VERSION, and writes its number's lists here: 2 for CAT-6, say, with "product" and the rest at their places.
LISTS_BY_APP_NUMBER = {
    1: ["side", "payment_account", "staff", "setting"],
}


def _app_number() -> int:
    # The one line that writes it, exactly so: a change to its form fails here, rather than reading something else.
    found = re.findall(r"^export const APP_NUMBER = (\d+);$", APP_VERSION_FILE.read_text(), flags=re.MULTILINE)
    assert len(found) == 1, f"{APP_VERSION_FILE} must write `export const APP_NUMBER = <n>;` once."
    return int(found[0])


def test_the_app_shipped_is_never_below_the_servers_minimum() -> None:
    assert 1 <= settings.MIN_APP_VERSION <= _app_number()


def _lists_out_of_step(lists: list[str], app_number: int) -> str | None:
    # What is wrong between the lists a device keeps and the app's number, or None when they are in step.
    if app_number not in LISTS_BY_APP_NUMBER:
        return f"app number {app_number} names no lists in LISTS_BY_APP_NUMBER: write them there."
    if lists != LISTS_BY_APP_NUMBER[app_number]:
        return (
            f"the lists {lists} aren't app number {app_number}'s {LISTS_BY_APP_NUMBER[app_number]}: a list added or"
            " moved raises APP_NUMBER and MIN_APP_VERSION, and writes the new number's lists."
        )
    return None


def _apps_drawers() -> list[str]:
    # The lists the app has a drawer for, from the one line that writes them (`const LISTS = [...] as const;`).
    found = re.findall(r"^const LISTS = \[(.*?)\] as const;$", PULL_FILE.read_text(), flags=re.MULTILINE)
    assert len(found) == 1, f"{PULL_FILE} must write `const LISTS = [...] as const;` once, on one line."
    return re.findall(r'"([a-z_]+)"', found[0])


def test_the_registry_keeps_the_lists_of_the_apps_number() -> None:
    # The server's side: the registry, the one list of what a device keeps a copy of (apps/sync/registry.py).
    assert _lists_out_of_step(list(REGISTRY), _app_number()) is None


def test_the_lowest_app_served_keeps_every_list() -> None:
    # The server's minimum: every app it still serves has a drawer for every list. A release that added "product" and
    # raised the app's number alone would leave the minimum at 1: an app-1 tab, its cursor removed by the new version's
    # database upgrade, would fill the database with the old code, which drops the products, and set the cursor past
    # their lines for good (the very hole the bootstrap's min_app_version closes).
    assert _lists_out_of_step(list(REGISTRY), settings.MIN_APP_VERSION) is None


def test_the_app_has_a_drawer_for_each_list_of_its_number() -> None:
    # The app's side: a list in the registry with no drawer in the app stops every pull for good (AppTooOld).
    assert _lists_out_of_step(_apps_drawers(), _app_number()) is None


def test_the_guard_catches_a_list_added_without_a_new_number() -> None:
    # The check above, shown to fail: CAT-6's products added, the number still 1.
    assert _lists_out_of_step([*LISTS_BY_APP_NUMBER[1], "product"], 1) is not None
    assert _lists_out_of_step(LISTS_BY_APP_NUMBER[1], 2) is not None
