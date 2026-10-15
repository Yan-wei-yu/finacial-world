from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def now() -> datetime:
    """Thursday 2026-10-15 21:00 in Taipei (09:00 in New York)."""
    return datetime(2026, 10, 15, 13, 0, tzinfo=timezone.utc)


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def config_dir() -> Path:
    return ROOT / "config"


@pytest.fixture
def config(config_dir):
    from pipeline.config import load_config

    return load_config(config_dir)
