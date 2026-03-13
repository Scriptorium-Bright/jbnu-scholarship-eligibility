import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import reset_settings_cache
from app.db.session import reset_engine_cache


@pytest.fixture(autouse=True)
def clear_cached_state():
    reset_settings_cache()
    reset_engine_cache()
    yield
    reset_settings_cache()
    reset_engine_cache()
