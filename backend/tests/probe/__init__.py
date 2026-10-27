"""tests/probe — a test-only app: small tables built on core's base models, for core's own tests.

`core` can't prove its base models on a real table: none exists yet, and `core` may not import the apps
that will have them (ADR-0035). So these tables stand in. Only config/settings/test.py installs this
app, so the development and production databases never get its tables.
"""
