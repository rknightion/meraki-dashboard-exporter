"""Tests for per-organization health tracking (OrgHealthTracker)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from meraki_dashboard_exporter.core.org_health import OrgHealth, OrgHealthTracker


class TestOrgHealth:
    """Tests for the OrgHealth dataclass."""

    def test_default_values(self):
        """Test OrgHealth default field values."""
        health = OrgHealth(org_id="123", org_name="Test Org")
        assert health.org_id == "123"
        assert health.org_name == "Test Org"
        assert health.consecutive_failures == 0
        assert health.last_success == 0.0
        assert health.last_failure == 0.0
        assert health.backoff_until == 0.0


class TestOrgHealthTracker:
    """Tests for the OrgHealthTracker class."""

    def setup_method(self):
        """Create a fresh tracker for each test."""
        self.tracker = OrgHealthTracker(
            max_consecutive_failures=3,
            base_backoff=60.0,
            max_backoff=3600.0,
        )

    def test_should_collect_returns_true_for_new_org(self):
        """New orgs with no health record should always be collected."""
        assert self.tracker.should_collect("unknown-org-id") is True

    def test_should_collect_returns_true_after_success(self):
        """Orgs with only successes should always be collected."""
        self.tracker.record_success("org1", "Org One")
        assert self.tracker.should_collect("org1") is True

    def test_success_resets_failure_count(self):
        """Recording success should reset the consecutive failure count."""
        self.tracker.record_failure("org1", "Org One")
        self.tracker.record_failure("org1", "Org One")
        assert self.tracker.get_health("org1").consecutive_failures == 2

        self.tracker.record_success("org1", "Org One")
        assert self.tracker.get_health("org1").consecutive_failures == 0

    def test_success_clears_backoff(self):
        """Recording success should clear the backoff_until timestamp."""
        # Drive org into backoff
        for _ in range(3):
            self.tracker.record_failure("org1", "Org One")

        health = self.tracker.get_health("org1")
        assert health.backoff_until > 0.0

        self.tracker.record_success("org1", "Org One")
        assert self.tracker.get_health("org1").backoff_until == 0.0

    def test_failure_increments_count(self):
        """Each failure should increment the consecutive failure counter."""
        self.tracker.record_failure("org1", "Org One")
        assert self.tracker.get_health("org1").consecutive_failures == 1

        self.tracker.record_failure("org1", "Org One")
        assert self.tracker.get_health("org1").consecutive_failures == 2

    def test_backoff_activates_after_n_failures(self):
        """Backoff should activate after max_consecutive_failures failures."""
        # No backoff before threshold
        for _i in range(self.tracker.max_consecutive_failures - 1):
            self.tracker.record_failure("org1", "Org One")
            assert self.tracker.should_collect("org1") is True

        # Backoff triggers on the Nth failure
        self.tracker.record_failure("org1", "Org One")
        assert self.tracker.should_collect("org1") is False

    def test_backoff_duration_is_base_on_first_trigger(self):
        """First backoff trigger should use the base_backoff duration."""
        fake_now = 1000.0
        with patch("meraki_dashboard_exporter.core.org_health.time") as mock_time:
            mock_time.time.return_value = fake_now
            for _ in range(self.tracker.max_consecutive_failures):
                self.tracker.record_failure("org1", "Org One")

        health = self.tracker.get_health("org1")
        # On first trigger: base_backoff * 2^(N - N) = base_backoff * 1
        expected_backoff_until = fake_now + self.tracker.base_backoff
        assert health.backoff_until == pytest.approx(expected_backoff_until)

    def test_backoff_duration_increases_exponentially(self):
        """Successive failures after threshold should double the backoff each time."""
        fake_now = 1000.0
        with patch("meraki_dashboard_exporter.core.org_health.time") as mock_time:
            mock_time.time.return_value = fake_now
            for _ in range(self.tracker.max_consecutive_failures):
                self.tracker.record_failure("org1", "Org One")
            # One extra failure: 2x base_backoff
            self.tracker.record_failure("org1", "Org One")

        health = self.tracker.get_health("org1")
        expected_backoff = self.tracker.base_backoff * 2
        assert health.backoff_until == pytest.approx(fake_now + expected_backoff)

    def test_backoff_caps_at_max_backoff(self):
        """Backoff should never exceed max_backoff."""
        tracker = OrgHealthTracker(
            max_consecutive_failures=3,
            base_backoff=60.0,
            max_backoff=120.0,
        )
        fake_now = 1000.0
        with patch("meraki_dashboard_exporter.core.org_health.time") as mock_time:
            mock_time.time.return_value = fake_now
            # Many failures to push backoff above cap
            for _ in range(20):
                tracker.record_failure("org1", "Org One")

        health = tracker.get_health("org1")
        assert health.backoff_until == pytest.approx(fake_now + 120.0)

    def test_should_collect_returns_false_during_backoff(self):
        """should_collect must return False while backoff window is active."""
        fake_now = 1000.0
        with patch("meraki_dashboard_exporter.core.org_health.time") as mock_time:
            mock_time.time.return_value = fake_now
            for _ in range(self.tracker.max_consecutive_failures):
                self.tracker.record_failure("org1", "Org One")
            # Still before backoff expires
            assert self.tracker.should_collect("org1") is False

    def test_should_collect_returns_true_after_backoff_expires(self):
        """should_collect must return True once the backoff window has passed."""
        trigger_time = 1000.0
        with patch("meraki_dashboard_exporter.core.org_health.time") as mock_time:
            mock_time.time.return_value = trigger_time
            for _ in range(self.tracker.max_consecutive_failures):
                self.tracker.record_failure("org1", "Org One")

            # Advance time past backoff window
            mock_time.time.return_value = trigger_time + self.tracker.base_backoff + 1
            assert self.tracker.should_collect("org1") is True

    def test_recovery_after_backoff(self):
        """After backoff expires and a successful collection, org should be healthy."""
        trigger_time = 1000.0
        with patch("meraki_dashboard_exporter.core.org_health.time") as mock_time:
            mock_time.time.return_value = trigger_time
            for _ in range(self.tracker.max_consecutive_failures):
                self.tracker.record_failure("org1", "Org One")

            # Advance past backoff, record success
            mock_time.time.return_value = trigger_time + self.tracker.base_backoff + 1
            self.tracker.record_success("org1", "Org One")

        health = self.tracker.get_health("org1")
        assert health.consecutive_failures == 0
        assert health.backoff_until == 0.0
        assert self.tracker.should_collect("org1") is True

    def test_get_health_returns_none_for_unknown_org(self):
        """get_health should return None when the org has never been seen."""
        assert self.tracker.get_health("nonexistent") is None

    def test_get_health_returns_state_after_recording(self):
        """get_health should return the OrgHealth object after recording activity."""
        self.tracker.record_failure("org1", "Org One")
        health = self.tracker.get_health("org1")
        assert isinstance(health, OrgHealth)
        assert health.org_id == "org1"
        assert health.org_name == "Org One"

    def test_org_name_populated_on_first_record(self):
        """org_name should be set when first recorded via success or failure."""
        self.tracker.record_success("org1", "My Org")
        assert self.tracker.get_health("org1").org_name == "My Org"

    def test_org_name_updated_if_previously_empty(self):
        """org_name should be updated if the record was created without a name."""
        # Create record without name via the internal helper
        self.tracker._get_or_create("org1", "")
        assert not self.tracker.get_health("org1").org_name

        # Update name via subsequent record
        self.tracker.record_success("org1", "Filled Name")
        assert self.tracker.get_health("org1").org_name == "Filled Name"

    def test_multiple_orgs_tracked_independently(self):
        """Failures in one org should not affect another org's health state."""
        for _ in range(self.tracker.max_consecutive_failures):
            self.tracker.record_failure("org1", "Org One")

        self.tracker.record_success("org2", "Org Two")

        assert self.tracker.should_collect("org1") is False
        assert self.tracker.should_collect("org2") is True

    def test_last_failure_timestamp_updated(self):
        """last_failure should be updated to the current time on failure."""
        fake_now = 5000.0
        with patch("meraki_dashboard_exporter.core.org_health.time") as mock_time:
            mock_time.time.return_value = fake_now
            self.tracker.record_failure("org1", "Org One")

        assert self.tracker.get_health("org1").last_failure == fake_now

    def test_last_success_timestamp_updated(self):
        """last_success should be updated to the current time on success."""
        fake_now = 9999.0
        with patch("meraki_dashboard_exporter.core.org_health.time") as mock_time:
            mock_time.time.return_value = fake_now
            self.tracker.record_success("org1", "Org One")

        assert self.tracker.get_health("org1").last_success == fake_now
