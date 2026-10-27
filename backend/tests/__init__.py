"""backend/tests — tests that span apps, and the test-only tables some tests read (03 §4).

This package is outside `apps`, so the layer contract (ADR-0035) doesn't apply here: the cross-app tests
to come (the tenancy sweep in CORE-7, the worked examples E1–E10) may import any app. `probe/` is a
test-only app that config/settings/test.py alone installs: its tables let `core` test its base models
before any real table builds on them.
"""
