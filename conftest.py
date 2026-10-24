"""Root conftest — loads .env.test before any application code is imported."""

from pathlib import Path

from dotenv import load_dotenv

# Load test environment BEFORE any league_app imports happen.
# This file is picked up by pytest first because it sits at the repo root.
_env_test = Path(__file__).parent / ".env.test"
load_dotenv(_env_test, override=True)

# Also clear the lru_cache of get_settings so it picks up the test values
# (in case config was already imported by a plugin or earlier conftest).
from league_app.config import get_settings  # noqa: E402

get_settings.cache_clear()
