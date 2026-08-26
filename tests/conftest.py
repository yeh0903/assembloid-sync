import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


@pytest.fixture(autouse=True)
def _isolate_local_config(monkeypatch):
    """Tests must see defaults.json only - never a developer's config.local.json."""
    from assembloid_sync import config
    monkeypatch.setattr(config, "local_config", lambda: {})
    for suffix in ("DATA_ROOT", "IMAGEJ", "DATASET"):
        monkeypatch.delenv(config.ENV_PREFIX + suffix, raising=False)
