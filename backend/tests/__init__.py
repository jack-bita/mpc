"""backend/tests — tests that span apps, and the test-only tables some tests read (03 §4).

This package is outside `apps`, so the layer contract (ADR-0035) doesn't apply here: the cross-app tests may
import any app. Today: the tenancy sweep (test_tenancy_sweep.py, CORE-7), with its two filled shops
(conftest.py) and its allowed lists (sweep_lists.py); and the float check and the shared test vectors
(test_no_floats.py, test_vectors.py, CORE-5). The worked examples E1–E10 come later. `probe/` is a test-only app that
config/settings/test.py alone installs: its tables let `core` test its base models before any real table
builds on them, and its routes let the sweep test its own checks.
"""
