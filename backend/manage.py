#!/usr/bin/env python
"""manage.py — the command line for the backend: `uv run python manage.py <command>`.

It owns nothing but the choice of settings when none is given.
Never run `migrate` before PPL-1 is merged: the custom User must be the first migration (ADR-0012).
"""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Run commands through uv (`uv run python manage.py …`) "
            "so they use the backend's own environment."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
