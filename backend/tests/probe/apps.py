"""tests/probe/apps.py — registers the test-only probe app with Django."""

from django.apps import AppConfig


class ProbeConfig(AppConfig):
    name = "tests.probe"
    # The short name tables and migrations use: `probe.Note`, table `probe_note`.
    label = "probe"
