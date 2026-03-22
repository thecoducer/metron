"""Pytest session configuration.

Prevents tests from writing to real ML cache files
(``data/classification_cache.json`` and ``data/sector_labels.json``).

The write functions are no-oped so tests can still read existing data
(sector labels etc.) but never modify production files.

Session scope ensures this is in place before any test runs, including
``unittest.TestCase`` subclasses which don't receive function fixtures.
"""

from collections.abc import Generator
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True, scope="session")
def _no_ml_cache_writes() -> Generator[None, None, None]:
    """No-op the ML cache write functions for the entire test session."""
    p1 = patch("app.api.company_classifier._write_cache_file")
    p2 = patch("app.api.company_classifier._write_sector_labels_file")
    p1.start()
    p2.start()
    yield
    p1.stop()
    p2.stop()
