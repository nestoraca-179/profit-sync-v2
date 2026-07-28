import pytest

from src.config.config_loader import DatabaseSettings
from src.utils.validators import validate_identifier

def test_database_settings_build_connection_string():
    settings = DatabaseSettings(
        server="localhost",
        database="SistemaFacturacion",
        username="user",
        password="password",
    )

    connection_string = settings.connection_string

    assert "SERVER=localhost" in connection_string
    assert "DATABASE=SistemaFacturacion" in connection_string

def test_validate_identifier_rejects_unsafe_input():
    with pytest.raises(ValueError):
        validate_identifier("dbo.Users;")