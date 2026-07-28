import os

import pytest

from src.config.config_loader import ConfigLoader
from src.connectors.local_connector import LocalSQLConnector
from src.connectors.remote_connector import RemoteSQLConnector


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run integration tests",
)


def test_database_connectors_can_be_constructed():
    config = ConfigLoader().load()

    local = LocalSQLConnector(config.synchronizer.local_database)
    remote = RemoteSQLConnector(config.synchronizer.remote_database)

    assert local.source_name == "local"
    assert remote.source_name == "remote"
