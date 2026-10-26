"""apps/core/languages.py — the languages the screens speak: one list for every app.

A person picks one for their own screens (people's User), and a shop has a default one (shops' Shop).
The list lives in core, the lowest layer, so both apps can use it: shops sits below people and may not
import from it (ADR-0035). Swahili first (03 §7.4).
"""

from django.db import models


# The values ("sw", "en") are what the database stores; each model's check constraint copies them into
# its migration. A new language goes here, and then each table that uses it needs a new migration.
class Language(models.TextChoices):
    SWAHILI = "sw", "Kiswahili"
    ENGLISH = "en", "English"
