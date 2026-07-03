"""Tests for the ``_FILE`` file-based secret settings source (#587).

The exporter must be able to load the Meraki API key (or any setting) from a
file path supplied via a ``<ENV_VAR>_FILE`` environment variable, as is the
norm for Kubernetes / Docker / Vault secret mounts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from meraki_dashboard_exporter.core.config_sources import FileSecretsSettingsSource


class _Nested(BaseModel):
    # Mirrors MerakiSettings: a plain BaseModel (extra ignored), so the raw
    # ..._FILE env var that env_settings splits into `api_key_file` is dropped.
    api_key: SecretStr = Field(default=SecretStr("unset"))


class _DemoSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MERAKI_EXPORTER_",
        env_nested_delimiter="__",
        case_sensitive=False,
    )
    meraki: _Nested = Field(default_factory=_Nested)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            FileSecretsSettingsSource(settings_cls),
            file_secret_settings,
        )


def test_file_secret_loads_nested_key(monkeypatch, tmp_path):
    """Nested API key loads from a mounted secret file."""
    secret_file = tmp_path / "api_key"
    secret_file.write_text("s3cret-from-file-value-1234567890")
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY_FILE", str(secret_file))
    monkeypatch.delenv("MERAKI_EXPORTER_MERAKI__API_KEY", raising=False)

    settings = _DemoSettings()
    assert settings.meraki.api_key.get_secret_value() == "s3cret-from-file-value-1234567890"


def test_file_secret_strips_trailing_newline(monkeypatch, tmp_path):
    """Trailing newline in the secret file is stripped."""
    secret_file = tmp_path / "api_key"
    secret_file.write_text("keywithnewline\n")
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY_FILE", str(secret_file))

    settings = _DemoSettings()
    assert settings.meraki.api_key.get_secret_value() == "keywithnewline"


def test_direct_env_takes_precedence_over_file(monkeypatch, tmp_path):
    """A directly-set env var overrides the file value."""
    secret_file = tmp_path / "api_key"
    secret_file.write_text("from-file")
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY_FILE", str(secret_file))
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", "from-env")

    settings = _DemoSettings()
    # env_settings source runs after the file source and overrides it.
    assert settings.meraki.api_key.get_secret_value() == "from-env"


def test_missing_file_is_ignored(monkeypatch, tmp_path):
    """A missing secret file is ignored (warns, does not fail)."""
    monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY_FILE", str(tmp_path / "does-not-exist"))
    settings = _DemoSettings()
    assert settings.meraki.api_key.get_secret_value() == "unset"


def test_no_file_env_is_noop(monkeypatch):
    """With no _FILE env var the source is a no-op."""
    monkeypatch.delenv("MERAKI_EXPORTER_MERAKI__API_KEY_FILE", raising=False)
    settings = _DemoSettings()
    assert settings.meraki.api_key.get_secret_value() == "unset"
