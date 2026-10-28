"""tests/probe — a test-only app: small tables built on core's base models, for core's own tests, and routes
over them, for the tenancy sweep's own tests.

`core` can't prove its base models on a real table: none exists yet, and `core` may not import the apps
that will have them (ADR-0035). So these tables stand in. The sweep proves its checks on routes built to
break them, which no real app may hold: they live here too (api.py, urls.py). Only config/settings/test.py
installs this app, so the development and production databases never get its tables.
"""
