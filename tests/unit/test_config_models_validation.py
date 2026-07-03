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
    CardinalitySettings,
    CollectorSettings,
    LoggingSettings,
    MerakiSettings,
    OTelMetricsSettings,
    OTelSettings,
    SchedulerSettings,
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


class TestApiScaleSettings:
    """Phase-3 rate-limit/scale config seam on APISettings (#550/#546/RETRY)."""

    def test_shared_fraction_default_is_0_8(self):
        """rate_limit_shared_fraction now leaves ~20% org headroom by default (#550)."""
        assert APISettings().rate_limit_shared_fraction == 0.8

    def test_shared_fraction_still_bounded(self):
        """The fraction keeps its 0.1..1.0 bounds."""
        assert APISettings(rate_limit_shared_fraction=1.0).rate_limit_shared_fraction == 1.0
        with pytest.raises(ValidationError):
            APISettings(rate_limit_shared_fraction=0.0)
        with pytest.raises(ValidationError):
            APISettings(rate_limit_shared_fraction=1.5)

    def test_new_scale_field_defaults(self):
        """New RETRY/deadline/executor fields default to the frozen seam values."""
        s = APISettings()
        assert s.retry_after_max_seconds == 60
        assert s.executor_workers == 10
        assert s.per_fetch_deadline_seconds == 120

    def test_new_scale_fields_configurable(self):
        """The new fields accept explicit overrides within bounds."""
        s = APISettings(
            retry_after_max_seconds=120,
            executor_workers=20,
            per_fetch_deadline_seconds=300,
        )
        assert s.retry_after_max_seconds == 120
        assert s.executor_workers == 20
        assert s.per_fetch_deadline_seconds == 300

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("retry_after_max_seconds", 0),
            ("executor_workers", 0),
            ("per_fetch_deadline_seconds", 0),
        ],
    )
    def test_new_scale_fields_reject_below_min(self, field, value):
        """Each new field enforces a positive lower bound."""
        with pytest.raises(ValidationError):
            APISettings(**{field: value})

    def test_single_request_timeout_default_unchanged(self):
        """#556: the SDK single_request_timeout default (api.timeout) stays 30s."""
        assert APISettings().timeout == 30


class TestCardinalitySettings:
    """New CardinalitySettings nested model (SCALE-01 / #540 family)."""

    def test_defaults(self):
        """All fields default to the frozen seam values."""
        c = CardinalitySettings()
        assert c.max_series_per_family == 50000
        assert c.action == "warn"
        assert c.disabled_metrics == set()
        assert c.monitor_interval_seconds == 300
        assert c.monitor_max_label_values == 100

    def test_action_literal_rejects_unknown(self):
        """action only accepts 'warn' or 'drop'."""
        assert CardinalitySettings(action="drop").action == "drop"
        with pytest.raises(ValidationError):
            CardinalitySettings(action="explode")

    def test_disabled_metrics_csv_string(self):
        """A bare comma-separated string parses into a set (NoDecode + CSV, #514 pattern)."""
        c = CardinalitySettings(disabled_metrics="meraki_foo,meraki_bar")
        assert c.disabled_metrics == {"meraki_foo", "meraki_bar"}

    def test_disabled_metrics_json_array(self):
        """The JSON-array form also parses."""
        c = CardinalitySettings(disabled_metrics='["meraki_foo","meraki_bar"]')
        assert c.disabled_metrics == {"meraki_foo", "meraki_bar"}

    def test_disabled_metrics_native_set(self):
        """A native set passes through, whitespace stripped."""
        c = CardinalitySettings(disabled_metrics={" meraki_foo ", "meraki_bar"})
        assert c.disabled_metrics == {"meraki_foo", "meraki_bar"}

    def test_disabled_metrics_empty_string(self):
        """An empty string yields an empty set, not a crash."""
        assert CardinalitySettings(disabled_metrics="").disabled_metrics == set()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("max_series_per_family", 0),
            ("monitor_interval_seconds", 0),
            ("monitor_max_label_values", 0),
        ],
    )
    def test_numeric_lower_bounds(self, field, value):
        """Numeric guard-rail fields reject below-minimum values."""
        with pytest.raises(ValidationError):
            CardinalitySettings(**{field: value})


class TestSchedulerSettings:
    """New SchedulerSettings nested model (#617 adaptive budget-aware scheduler)."""

    def test_defaults(self):
        """Every field defaults to the frozen BUILD SPEC §1d value."""
        s = SchedulerSettings()
        assert s.mode == "adaptive"
        assert s.target_utilization == 0.7
        assert s.max_stretch_factor == 4.0
        assert s.max_interval_seconds == 3600
        assert s.resolve_interval_seconds == 900
        assert s.aimd_enabled is True
        assert s.aimd_backoff_multiplier == 0.5
        assert s.aimd_recovery_rps_per_minute == 0.1
        assert s.aimd_resolve_hysteresis == 0.2
        assert s.group_interval_overrides == {}

    def test_mode_literal_rejects_unknown(self):
        """mode only accepts 'adaptive' or 'fixed'."""
        assert SchedulerSettings(mode="fixed").mode == "fixed"
        with pytest.raises(ValidationError):
            SchedulerSettings(mode="turbo")

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("target_utilization", 0.05),
            ("target_utilization", 1.5),
            ("max_stretch_factor", 0.5),
            ("max_stretch_factor", 17.0),
            ("max_interval_seconds", 299),
            ("max_interval_seconds", 86401),
            ("resolve_interval_seconds", 59),
            ("resolve_interval_seconds", 86401),
            ("aimd_backoff_multiplier", 0.05),
            ("aimd_backoff_multiplier", 0.95),
            ("aimd_recovery_rps_per_minute", 0.005),
            ("aimd_recovery_rps_per_minute", 5.5),
            ("aimd_resolve_hysteresis", 0.04),
            ("aimd_resolve_hysteresis", 1.1),
        ],
    )
    def test_numeric_bounds_rejected(self, field, value):
        """Each numeric knob enforces its frozen ge/le bounds."""
        with pytest.raises(ValidationError):
            SchedulerSettings(**{field: value})

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("target_utilization", 1.0),
            ("target_utilization", 0.1),
            ("max_stretch_factor", 1.0),
            ("max_stretch_factor", 16.0),
            ("max_interval_seconds", 300),
            ("max_interval_seconds", 86400),
            ("resolve_interval_seconds", 60),
            ("resolve_interval_seconds", 86400),
            ("aimd_backoff_multiplier", 0.1),
            ("aimd_backoff_multiplier", 0.9),
            ("aimd_recovery_rps_per_minute", 0.01),
            ("aimd_recovery_rps_per_minute", 5.0),
            ("aimd_resolve_hysteresis", 0.05),
            ("aimd_resolve_hysteresis", 1.0),
        ],
    )
    def test_numeric_bounds_accepted(self, field, value):
        """Boundary values inside the frozen ge/le range are accepted."""
        s = SchedulerSettings(**{field: value})
        assert getattr(s, field) == value

    def test_aimd_toggle(self):
        """aimd_enabled can be turned off explicitly."""
        assert SchedulerSettings(aimd_enabled=False).aimd_enabled is False

    def test_group_interval_overrides_dict(self):
        """group_interval_overrides accepts a native dict[str, int]."""
        s = SchedulerSettings(group_interval_overrides={"nh_connection_stats": 900})
        assert s.group_interval_overrides == {"nh_connection_stats": 900}

    def test_group_interval_overrides_json_object_string(self):
        """A JSON-object string parses into the dict (env-var form)."""
        s = SchedulerSettings(group_interval_overrides='{"nh_connection_stats": 900}')
        assert s.group_interval_overrides == {"nh_connection_stats": 900}


class TestOTelMetricsSettings:
    """New OTelMetricsSettings nested model + #314 cert fields (#313/#339)."""

    def test_defaults(self):
        """All fields default to the frozen seam values."""
        m = OTelMetricsSettings()
        assert m.enabled is False
        assert m.endpoint is None
        assert m.insecure is None
        assert m.export_interval_seconds == 60
        assert m.include == "all"
        assert m.temporality == "cumulative"

    def test_export_interval_bounds(self):
        """export_interval_seconds enforces its 10..3600 bounds."""
        assert OTelMetricsSettings(export_interval_seconds=10).export_interval_seconds == 10
        assert OTelMetricsSettings(export_interval_seconds=3600).export_interval_seconds == 3600
        with pytest.raises(ValidationError):
            OTelMetricsSettings(export_interval_seconds=9)
        with pytest.raises(ValidationError):
            OTelMetricsSettings(export_interval_seconds=3601)

    def test_include_literal_rejects_unknown(self):
        """include only accepts product|self|all."""
        assert OTelMetricsSettings(include="product").include == "product"
        assert OTelMetricsSettings(include="self").include == "self"
        with pytest.raises(ValidationError):
            OTelMetricsSettings(include="everything")

    def test_temporality_literal_rejects_unknown(self):
        """temporality only accepts 'cumulative' in v1."""
        with pytest.raises(ValidationError):
            OTelMetricsSettings(temporality="delta")

    def test_nested_default_on_otel_settings(self):
        """OTelSettings.metrics defaults to a fresh OTelMetricsSettings instance."""
        s = OTelSettings()
        assert isinstance(s.metrics, OTelMetricsSettings)
        assert s.metrics.enabled is False

    def test_cert_fields_default_none(self):
        """The #314 cert-path fields default to None on the parent OTelSettings."""
        s = OTelSettings()
        assert s.ca_cert_path is None
        assert s.client_cert_path is None
        assert s.client_key_path is None

    def test_cert_fields_pass_through(self):
        """Cert paths are stored verbatim when set (with insecure=False so validation passes)."""
        s = OTelSettings(
            insecure=False,
            ca_cert_path="/etc/otel/ca.pem",
            client_cert_path="/etc/otel/client.pem",
            client_key_path="/etc/otel/client-key.pem",
        )
        assert s.ca_cert_path == "/etc/otel/ca.pem"
        assert s.client_cert_path == "/etc/otel/client.pem"
        assert s.client_key_path == "/etc/otel/client-key.pem"

    def test_enabled_without_resolvable_endpoint_rejected(self):
        """metrics.enabled=True with no own or inherited endpoint is rejected."""
        with pytest.raises(ValidationError, match="OTEL metrics endpoint must be provided"):
            OTelSettings(metrics=OTelMetricsSettings(enabled=True))

    def test_enabled_with_own_endpoint_ok(self):
        """metrics.enabled=True with its own endpoint validates."""
        s = OTelSettings(metrics=OTelMetricsSettings(enabled=True, endpoint="otel:4317"))
        assert s.metrics_endpoint == "otel:4317"

    def test_enabled_inherits_parent_endpoint(self):
        """metrics.enabled=True with no own endpoint inherits the parent endpoint."""
        s = OTelSettings(endpoint="otel:4317", metrics=OTelMetricsSettings(enabled=True))
        assert s.metrics_endpoint == "otel:4317"

    def test_metrics_endpoint_property_prefers_own(self):
        """metrics_endpoint prefers the nested value over the inherited one."""
        s = OTelSettings(endpoint="parent:4317", metrics=OTelMetricsSettings(endpoint="own:4317"))
        assert s.metrics_endpoint == "own:4317"

    def test_metrics_insecure_property_inherits_when_none(self):
        """metrics_insecure inherits otel.insecure when metrics.insecure is None."""
        s = OTelSettings(insecure=False)
        assert s.metrics_insecure is False

    def test_metrics_insecure_property_prefers_own(self):
        """metrics_insecure prefers its own explicit value over the inherited one."""
        s = OTelSettings(insecure=False, metrics=OTelMetricsSettings(insecure=True))
        assert s.metrics_insecure is True

    def test_client_cert_without_key_rejected(self):
        """client_cert_path set without client_key_path is rejected (mTLS needs both)."""
        with pytest.raises(ValidationError):
            OTelSettings(insecure=False, client_cert_path="/etc/otel/client.pem")

    def test_client_key_without_cert_rejected(self):
        """client_key_path set without client_cert_path is rejected (mTLS needs both)."""
        with pytest.raises(ValidationError):
            OTelSettings(insecure=False, client_key_path="/etc/otel/client-key.pem")

    def test_client_cert_and_key_together_ok(self):
        """Both client_cert_path and client_key_path set together validates."""
        s = OTelSettings(
            insecure=False,
            client_cert_path="/etc/otel/client.pem",
            client_key_path="/etc/otel/client-key.pem",
        )
        assert s.client_cert_path == "/etc/otel/client.pem"

    def test_ca_cert_with_all_channels_insecure_rejected(self):
        """A cert path set while every enabled OTLP channel is insecure is rejected."""
        with pytest.raises(ValidationError, match="every OTLP channel is insecure"):
            OTelSettings(
                enabled=True,
                endpoint="otel:4317",
                insecure=True,
                ca_cert_path="/etc/otel/ca.pem",
            )

    def test_ca_cert_with_no_channels_enabled_allowed(self):
        """A cert path set with no OTLP channel enabled at all is allowed (nothing to misconfigure)."""
        s = OTelSettings(ca_cert_path="/etc/otel/ca.pem")
        assert s.ca_cert_path == "/etc/otel/ca.pem"

    def test_ca_cert_with_one_secure_channel_allowed(self):
        """A cert path is allowed when at least one enabled channel resolves insecure=False."""
        s = OTelSettings(
            enabled=True,
            endpoint="otel:4317",
            insecure=False,
            metrics=OTelMetricsSettings(enabled=True, insecure=True),
            ca_cert_path="/etc/otel/ca.pem",
        )
        assert s.ca_cert_path == "/etc/otel/ca.pem"

    def test_env_var_round_trip(self, monkeypatch):
        """MERAKI_EXPORTER_OTEL__METRICS__* env vars populate the nested settings."""
        monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", _KEY)
        monkeypatch.setenv("MERAKI_EXPORTER_OTEL__METRICS__ENABLED", "true")
        monkeypatch.setenv("MERAKI_EXPORTER_OTEL__METRICS__ENDPOINT", "otel-collector:4317")
        monkeypatch.setenv("MERAKI_EXPORTER_OTEL__METRICS__INSECURE", "false")
        monkeypatch.setenv("MERAKI_EXPORTER_OTEL__METRICS__EXPORT_INTERVAL_SECONDS", "120")
        monkeypatch.setenv("MERAKI_EXPORTER_OTEL__METRICS__INCLUDE", "product")
        settings = Settings()
        assert settings.otel.metrics.enabled is True
        assert settings.otel.metrics.endpoint == "otel-collector:4317"
        assert settings.otel.metrics.insecure is False
        assert settings.otel.metrics.export_interval_seconds == 120
        assert settings.otel.metrics.include == "product"

    def test_cert_path_env_var_round_trip(self, monkeypatch):
        """MERAKI_EXPORTER_OTEL__*_CERT_PATH env vars populate the parent cert fields."""
        monkeypatch.setenv("MERAKI_EXPORTER_MERAKI__API_KEY", _KEY)
        monkeypatch.setenv("MERAKI_EXPORTER_OTEL__CA_CERT_PATH", "/etc/otel/ca.pem")
        monkeypatch.setenv("MERAKI_EXPORTER_OTEL__CLIENT_CERT_PATH", "/etc/otel/client.pem")
        monkeypatch.setenv("MERAKI_EXPORTER_OTEL__CLIENT_KEY_PATH", "/etc/otel/client-key.pem")
        settings = Settings()
        assert settings.otel.ca_cert_path == "/etc/otel/ca.pem"
        assert settings.otel.client_cert_path == "/etc/otel/client.pem"
        assert settings.otel.client_key_path == "/etc/otel/client-key.pem"


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
