"""apps/sync/tests/test_app_number.py — the app a server ships with is never too old for it (SYNC-13; 03 §6.8).

Every pull page carries the lowest app number that may still sync (`MIN_APP_VERSION`, config/settings/base.py), and a
laptop whose own number (`APP_NUMBER`, frontend/src/lib/version.ts) is lower stops pulling, sends what it holds, and
updates. Both are built into one image, so the app the server hands out must always be new enough: a release that
raised the minimum and forgot the app's own number would send every laptop round in updates that never end, and stop
every shop's pulls. Two numbers in two languages, kept in step by this test, which reads the app's from its file.
"""

import re
from pathlib import Path

from django.conf import settings

# The app's file, beside backend/ in the repo, as CI's backend job checks it out whole.
APP_VERSION_FILE = Path(settings.BASE_DIR).parent / "frontend" / "src" / "lib" / "version.ts"


def _app_number() -> int:
    # The one line that writes it, exactly so: a change to its form fails here, rather than reading something else.
    found = re.findall(r"^export const APP_NUMBER = (\d+);$", APP_VERSION_FILE.read_text(), flags=re.MULTILINE)
    assert len(found) == 1, f"{APP_VERSION_FILE} must write `export const APP_NUMBER = <n>;` once."
    return int(found[0])


def test_the_app_shipped_is_never_below_the_servers_minimum() -> None:
    assert 1 <= settings.MIN_APP_VERSION <= _app_number()
