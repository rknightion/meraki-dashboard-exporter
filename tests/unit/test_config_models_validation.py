"""Unit tests for config_models validators and helpers.

Covers v1-readiness config issues:
- #514 CSV form of collector enable/disable settings
- #515 recognized-env-var reconciliation helper
- #587 file-based (``_FILE``) API-key settings source
- #590 api_base_url + org_id validation
- #598 case-insensitive log levels
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from meraki_dashboard_exporter.core.config import Settings
from meraki_dashboard_exporter.core.config_models import (
    APISettings,
    CollectorSettings,
    LoggingSettings,
    MerakiSettings,
    ServerSettings,
    WebhookSettings,
    find_unrecognized_env_vars,
)

_KEY = "a" * 40


class TestCollectorCsv:
    """#514 - CSV / JSON form of enabled_collectors / disable_collectors."""

    def test_csv_string_enabled(self):
        """A bare comma-separated string parses into a set."""
        s = CollectorSettings(enabled_collectors="device,organization,clients")
        assert s.enabled_collectors == {"device", "organization", "clients"}

    def test_csv_string_with_whitespace(self):
        """Surrounding whitespace on items is stripped."""
        s = CollectorSettings(enabled_collectors=" device , organization ")
        assert s.enabled_collectors == {"device", "organization"}

    def test_json_list_still_parses(self):
        """The JSON-array form keeps working after the change."""
        s = CollectorSettings(enabled_collectors='["device","organization"]')
        assert s.enabled_collectors == {"device", "organization"}

    def test_native_set_still_works(self):
        """A native set value passes through unchanged."""
        s = CollectorSettings(enabled_collectors={"device"})
        assert s.enabled_collectors == {"device"}

    def test_disable_csv(self):
        """disable_collectors also accepts the CSV form."""
        s = CollectorSettings(disable_collectors="clients,alerts")
        assert s.disable_collectors == {"clients", "alerts"}

    def test_empty_string_is_empty_set(self):
        """An empty string yields an empty set, not a crash."""
        s = CollectorSettings(disable_collectors="")
        assert s.disable_collectors == set()


class TestLogLevel:
    """#598 - case-insensitive log levels normalised to upper-case."""

    @pytest.mark.parametrize("value", ["info", "INFO", "Info", "  debug ", "WaRnInG"])
    def test_accepts_case_insensitive(self, value):
        """Mixed / lower-case levels are accepted and upper-cased."""
        s = LoggingSettings(level=value)
        assert s.level == value.strip().upper()

    def test_rejects_unknown_level(self):
        """An unknown level name is rejected."""
        with pytest.raises(ValidationError):
            LoggingSettings(level="verbose")


class TestMerakiUrlValidation:
    """#590 - api_base_url + org_id validation."""

    def test_default_url_ok(self):
        """The default global base URL validates."""
        m = MerakiSettings(api_key=_KEY)
        assert m.api_base_url == "https://api.meraki.com/api/v1"

    @pytest.mark.parametrize(
        "url",
        [
            "https://api.meraki.ca/api/v1",
            "https://api.meraki.cn/api/v1",
            "https://api.gov-meraki.com/api/v1",
        ],
    )
    def test_known_regions_ok(self, url):
        """Recognised regional base URLs validate without warning."""
        m = MerakiSettings(api_key=_KEY, api_base_url=url)
        assert m.api_base_url == url

    def test_unknown_but_wellformed_region_warns_not_fails(self):
        """A well-formed custom/proxy base URL is accepted (warn only)."""
        url = "https://meraki-proxy.internal.example.com/api/v1"
        m = MerakiSettings(api_key=_KEY, api_base_url=url)
        assert m.api_base_url == url

    @pytest.mark.parametrize(
        "url",
        [
            "not-a-url",
            "ftp://api.meraki.com/api/v1",
            "://missing-scheme",
            "https://",
            "",
        ],
    )
    def test_malformed_url_rejected(self, url):
        """Malformed base URLs are rejected at construction."""
        with pytest.raises(ValidationError):
            MerakiSettings(api_key=_KEY, api_base_url=url)

    def test_org_id_numeric_ok(self):
        """A numeric org_id validates."""
        m = MerakiSettings(api_key=_KEY, org_id="123456")
        assert m.org_id == "123456"

    def test_org_id_whitespace_stripped(self):
        """Surrounding whitespace on org_id is stripped."""
        m = MerakiSettings(api_key=_KEY, org_id=" 123456 ")
        assert m.org_id == "123456"

    def test_org_id_empty_rejected(self):
        """A whitespace-only org_id is rejected."""
        with pytest.raises(ValidationError):
            MerakiSettings(api_key=_KEY, org_id="   ")

    def test_org_id_non_numeric_accepted_with_warning(self):
        """A non-numeric org_id warns but does not fail (defensive)."""
        m = MerakiSettings(api_key=_KEY, org_id="my-org")
        assert m.org_id == "my-org"

    def test_org_id_omitted_is_none(self):
        """org_id is optional; omitting it yields None (#585 single-org auto-select)."""
        m = MerakiSettings(api_key=_KEY)
        assert m.org_id is None

    def test_org_id_explicit_none_accepted(self):
        """An explicit None org_id is accepted at the config layer (#585)."""
        m = MerakiSettings(api_key=_KEY, org_id=None)
        assert m.org_id is None


class TestApiProxyAndCert:
    """#586 - requests_proxy / certificate_path passthrough to the SDK."""

    def test_defaults_none(self):
        """Both fields default to None (SDK/env-var behaviour unchanged)."""
        s = APISettings()
        assert s.requests_proxy is None
        assert s.certificate_path is None

    def test_values_pass_through(self):
        """Explicit values are stored verbatim."""
        s = APISettings(
            requests_proxy="http://proxy.internal:3128",
            certificate_path="/etc/ssl/certs/custom-ca.pem",
        )
        assert s.requests_proxy == "http://proxy.internal:3128"
        assert s.certificate_path == "/etc/ssl/certs/custom-ca.pem"


class TestLogFormat:
    """#310 - structured-log renderer selection (logfmt|json)."""

    def test_default_is_logfmt(self):
        """The default renderer is logfmt."""
        assert LoggingSettings().log_format == "logfmt"

    @pytest.mark.parametrize("value", ["json", "JSON", "  Json ", "logfmt", "LOGFMT"])
    def test_accepts_case_insensitive(self, value):
        """logfmt/json accepted in any case, normalised to lower-case."""
        s = LoggingSettings(log_format=value)
        assert s.log_format == value.strip().lower()

    def test_rejects_unknown_format(self):
        """Anything other than logfmt|json is rejected."""
        with pytest.raises(ValidationError):
            LoggingSettings(log_format="xml")


class TestServerUiEnabled:
    """#558 - ui_enabled gate on sensitive GET UI/status endpoints."""

    def test_default_true(self):
        """UI is enabled by default."""
        assert ServerSettings().ui_enabled is True

    def test_can_disable(self):
        """ui_enabled can be turned off."""
        assert ServerSettings(ui_enabled=False).ui_enabled is False


class TestWebhookAllowInsecure:
    """#561 - explicit opt-in to run the webhook receiver without a secret."""

    def test_default_false(self):
        """Insecure webhook operation is off by default."""
        assert WebhookSettings().allow_insecure is False

    def test_can_enable(self):
        """allow_insecure can be explicitly enabled."""
        assert WebhookSettings(allow_insecure=True).allow_insecure is True


class TestUnrecognizedEnvVars:
    """#515 - reconcile observed MERAKI_EXPORTER_* env against the schema."""

    def test_known_keys_not_flagged(self):
        """Recognised keys (and non-prefixed keys) are not flagged."""
        env = {
            "MERAKI_EXPORTER_MERAKI__API_KEY": "x",
            "MERAKI_EXPORTER_MERAKI__ORG_ID": "1",
            "MERAKI_EXPORTER_LOGGING__LEVEL": "INFO",
            "MERAKI_EXPORTER_COLLECTORS__ENABLED_COLLECTORS": "device",
            "PATH": "/usr/bin",
        }
        assert find_unrecognized_env_vars(env, Settings) == []

    def test_unknown_key_flagged(self):
        """An unknown prefixed key is returned."""
        env = {
            "MERAKI_EXPORTER_MERAKI__API_KEY": "x",
            "MERAKI_EXPORTER_FOO__BAR": "oops",
        }
        assert find_unrecognized_env_vars(env, Settings) == ["MERAKI_EXPORTER_FOO__BAR"]

    def test_typo_of_known_key_flagged(self):
        """A typo'd known key is flagged."""
        env = {"MERAKI_EXPORTER_LOGGIN__LEVEL": "INFO"}
        assert find_unrecognized_env_vars(env, Settings) == ["MERAKI_EXPORTER_LOGGIN__LEVEL"]

    def test_case_insensitive_match(self):
        """Lower-case env keys still match the schema."""
        env = {"meraki_exporter_meraki__api_key": "x"}
        assert find_unrecognized_env_vars(env, Settings) == []

    def test_file_suffix_variant_recognized(self):
        """The #587 _FILE variant of a known key is not flagged."""
        env = {"MERAKI_EXPORTER_MERAKI__API_KEY_FILE": "/run/secrets/key"}
        assert find_unrecognized_env_vars(env, Settings) == []
