import os

import pytest

from src.config.config_loader import ConfigLoader


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run integration tests",
)


def test_config_loader_reads_yaml_files():
    config = ConfigLoader().load()

    assert config.synchronizer.name == "SQLSyncService"
    assert len(config.tables) >= 1
