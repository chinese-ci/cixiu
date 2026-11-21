from __future__ import annotations

from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).resolve().parent


@pytest.fixture
def golden_root() -> Path:
    return TESTS_ROOT / "golden"
