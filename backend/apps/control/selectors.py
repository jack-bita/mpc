"""apps/control/selectors.py — the reads of the control tables the services and the office routes share (ADR-0015).

flag_names says whether a flag names a person: the services ask it before a flag is closed (02 §13), and a flag's page
asks it for the person looking. One question in one place, so the page and the service can't answer it differently.

`control` is layer 0 and may not import `people` (ADR-0043), so a staff member's table is reached by its type code
(apps/core/links.py), at run time, as a flag's subject is.
"""

from typing import Any

from apps.control.models import Flag, FlagPerson
from apps.core.links import table_of
from apps.core.tenancy import Actor


def flag_names(flag: Flag, person: Actor) -> bool:
    """Whether `flag` names `person`, under any of their jobs at the shop: someone who left and was hired again has two
    (PPL-11), and a flag that names the old one is still about them (02 §13)."""
    # By the person, not the job: whoever the acting job belongs to, as deciding one's own day is asked (ATT-6). One
    # query: the jobs the flag names, whose person is the acting job's person. Both tables read through the shop's
    # guard, so a job at another shop never counts.
    jobs: Any = table_of("staff")
    their_person = jobs._default_manager.filter(pk=person.staff_id).values("user")
    return FlagPerson.objects.filter(flag=flag, staff__user__in=their_person).exists()
