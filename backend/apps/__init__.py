"""apps — the 13 domain apps of the modular monolith (ADR-0015, 03 §5.1).

Each app owns its own tables and rules; its `__init__.py` says what in one line.
The apps sit in layers, and an app imports only from the layers below it:

    0 core · 1 shops · 2 people, control · 3 catalog, contacts · 4 inventory, money ·
    5 sales, services, staffpay · 6 sync, reports

A model may still point at a higher layer by name ("sales.Sale"): that is not an import.
import-linter turns these layers into a CI check in REPO-6.

Each app's label is the last part of its name (`apps.people` → `people`), which is how models are
named elsewhere: `AUTH_USER_MODEL = "people.User"` (PPL-1), `"sales.Sale"`.
"""
