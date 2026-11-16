"""apps/sync/tests/test_carried_rules.py — a rule the app carries itself matches the server's (ATT-2, SYNC-13's note).

A rule's kind and default reach a laptop only with a bootstrap (setting_keys, apps/sync/bootstrap.py). A laptop filled
before the release that added a rule never learns them, though its pulls bring the rule's rows, so the app carries its
own copy of a rule it can't do without: today only attendance's switch (ATT_SWITCH_FILE). If that copy drifted from the
server's registry, an old laptop would read the switch one way and a new one another: a default of "true" in the app
would open Mahudhurio on every old laptop of a shop that never switched it on. So this test reads the app's copy from
its file, as test_app_number.py reads the app's number, and holds it to what the bootstrap sends.
"""

import re
from pathlib import Path

from django.conf import settings

from apps.sync.bootstrap import setting_keys

FRONTEND = Path(settings.BASE_DIR).parent / "frontend" / "src"
ATT_SWITCH_FILE = FRONTEND / "offline" / "attendance-on.ts"


def _carried(name: str) -> dict[str, str]:
    # The object written `export const <name> = { ... }`, one `field: "text",` a line, as Prettier lays it out: its
    # fields as text. A change to that form fails here, rather than reading something else.
    block = re.search(rf"^export const {name} = \{{\n(.*?)\n\}}", ATT_SWITCH_FILE.read_text(), flags=re.M | re.S)
    assert block is not None, f"{ATT_SWITCH_FILE} must write `export const {name} = {{ ... }}`, one field a line."
    return dict(re.findall(r'^\s+(\w+): "([^"]*)",$', block[1], flags=re.M))


def test_the_apps_attendance_switch_is_the_servers() -> None:
    carried = _carried("ATTENDANCE_SWITCH")
    (sent,) = [rule for rule in setting_keys() if rule["key"] == carried.get("key")]
    assert carried == sent
