"""
Tests for Day-1 Seed Script — OI-55
======================================

Comprehensive test suite covering:
* Timeline generation (reading counts, poll intervals)
* Scenario injection (MD near-miss, lazy-idle, leak proxy labels)
* Device mapping (all 9 devices from edge_nodes.json)
* Idempotency (via mocked backfill_insert)
* CLI flags (--hours, --no-scenarios, --families, --dry-run)
* SeedResult / FamilySeedResult dataclasses

All DB calls are mocked — no real TimescaleDB needed.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from omniview.ingest.seed import (
    FamilySeedResult,
    SeedResult,
    _get_devices_by_family,
    generate_timeline,
    seed_all,
    seed_sensor_family,
)

# ── Timezone ────────────────────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))


# ── Helpers ─────────────────────────────────────────────────────────────


def _make_start(hour: int = 0) -> datetime:
    """Create a start time on a fixed date for deterministic tests."""
    return datetime(2026, 8, 18, hour, 0, 0, tzinfo=IST)


# ═════════════════════════════════════════════════════════════════════════
# 1. Timeline generation
# ═════════════════════════════════════════════════════════════════════════


class TestGenerateTimeline:
    """Tests for the generate_timeline() function."""

    def test_electrical_1h_count(self):
        """1 hour at 15s interval = 240 readings."""
        readings = generate_timeline(
            device_id="test-elec-01",
            sensor_type="electrical",
            site_id="pune-isbm",
            node_id="compressor-01",
            poll_interval_s=15,
            start=_make_start(0),
            end=_make_start(1),
            inject_scenarios=False,
        )
        assert len(readings) == 240

    def test_vibration_1h_count(self):
        """1 hour at 60s interval = 60 readings."""
        readings = generate_timeline(
            device_id="test-vib-01",
            sensor_type="vibration",
            site_id="pune-isbm",
            node_id="compressor-01",
            poll_interval_s=60,
            start=_make_start(0),
            end=_make_start(1),
            inject_scenarios=False,
        )
        assert len(readings) == 60

    def test_24h_electrical_count(self):
        """24 hours at 15s = 5760 readings."""
        readings = generate_timeline(
            device_id="test-elec-01",
            sensor_type="electrical",
            site_id="pune-isbm",
            node_id="compressor-01",
            poll_interval_s=15,
            start=_make_start(0),
            end=_make_start(0) + timedelta(hours=24),
            inject_scenarios=False,
        )
        assert len(readings) == 5760

    def test_readings_are_chronological(self):
        readings = generate_timeline(
            device_id="test-elec-01",
            sensor_type="electrical",
            site_id="pune-isbm",
            node_id="compressor-01",
            poll_interval_s=15,
            start=_make_start(0),
            end=_make_start(1),
            inject_scenarios=False,
        )
        times = [r["time"] for r in readings]
        assert times == sorted(times)

    def test_reading_has_required_keys(self):
        readings = generate_timeline(
            device_id="test-elec-01",
            sensor_type="electrical",
            site_id="pune-isbm",
            node_id="compressor-01",
            poll_interval_s=15,
            start=_make_start(0),
            end=_make_start(0) + timedelta(minutes=1),
            inject_scenarios=False,
        )
        assert len(readings) > 0
        r = readings[0]
        assert "device_id" in r
        assert "site_id" in r
        assert "time" in r
        assert "data" in r
        assert "schema_version" in r
        assert r["device_id"] == "test-elec-01"
        assert r["site_id"] == "pune-isbm"

    def test_ambient_works_without_anomaly_flag(self):
        """Ambient bot's generate_reading() takes no args."""
        readings = generate_timeline(
            device_id="test-ambient-01",
            sensor_type="ambient",
            site_id="pune-isbm",
            node_id="floor",
            poll_interval_s=60,
            start=_make_start(0),
            end=_make_start(0) + timedelta(minutes=5),
            inject_scenarios=False,
        )
        assert len(readings) == 5

    def test_unknown_sensor_type_returns_empty(self):
        readings = generate_timeline(
            device_id="test-unknown",
            sensor_type="unknown_sensor",
            site_id="pune-isbm",
            node_id="test-node",
            poll_interval_s=60,
            start=_make_start(0),
            end=_make_start(1),
            inject_scenarios=False,
        )
        assert readings == []

    def test_empty_range_returns_empty(self):
        t = _make_start(5)
        readings = generate_timeline(
            device_id="test-elec-01",
            sensor_type="electrical",
            site_id="pune-isbm",
            node_id="compressor-01",
            poll_interval_s=15,
            start=t,
            end=t,  # same start and end
            inject_scenarios=False,
        )
        assert readings == []


# ═════════════════════════════════════════════════════════════════════════
# 2. Scenario injection
# ═════════════════════════════════════════════════════════════════════════


class TestScenarioInjection:
    """Tests for scenario labels in generated timelines."""

    def test_md_nearmiss_labels_present(self):
        """Electrical readings between 10:15-10:45 should have md_nearmiss label."""
        readings = generate_timeline(
            device_id="pune-comp-mfm384",
            sensor_type="electrical",
            site_id="pune-isbm",
            node_id="compressor-01",
            poll_interval_s=15,
            start=_make_start(0),
            end=_make_start(0) + timedelta(hours=24),
            inject_scenarios=True,
        )

        md_readings = [
            r for r in readings
            if r.get("scenario_label") == "md_nearmiss"
        ]
        assert len(md_readings) > 0

        # All MD readings should be between 10:15 and 10:45
        for r in md_readings:
            assert r["time"].hour == 10
            assert 15 <= r["time"].minute < 45

    def test_md_nearmiss_kva_elevated(self):
        """During MD near-miss, kVA should be > 350."""
        readings = generate_timeline(
            device_id="pune-comp-mfm384",
            sensor_type="electrical",
            site_id="pune-isbm",
            node_id="compressor-01",
            poll_interval_s=15,
            start=_make_start(10),
            end=_make_start(11),
            inject_scenarios=True,
        )

        md_readings = [
            r for r in readings
            if r.get("scenario_label") == "md_nearmiss"
        ]
        for r in md_readings:
            assert r["data"]["apparent_power_kva_total"] >= 350

    def test_lazy_idle_labels_on_isbm_electrical(self):
        """ISBM electrical should have lazy_idle labels at 14:00-14:20."""
        readings = generate_timeline(
            device_id="pune-isbm-mfm384",
            sensor_type="electrical",
            site_id="pune-isbm",
            node_id="isbm-01",
            poll_interval_s=15,
            start=_make_start(0),
            end=_make_start(0) + timedelta(hours=24),
            inject_scenarios=True,
        )

        idle_readings = [
            r for r in readings
            if r.get("scenario_label") == "lazy_idle"
        ]
        assert len(idle_readings) > 0

        for r in idle_readings:
            assert r["data"]["current_a_avg"] < 10  # low current

    def test_lazy_idle_not_on_compressor_electrical(self):
        """Compressor electrical should NOT have lazy_idle labels."""
        readings = generate_timeline(
            device_id="pune-comp-mfm384",
            sensor_type="electrical",
            site_id="pune-isbm",
            node_id="compressor-01",
            poll_interval_s=15,
            start=_make_start(0),
            end=_make_start(0) + timedelta(hours=24),
            inject_scenarios=True,
        )

        idle_readings = [
            r for r in readings
            if r.get("scenario_label") == "lazy_idle"
        ]
        assert len(idle_readings) == 0

    def test_leak_proxy_labels_on_compressor_pressure(self):
        """Compressor pressure should have leak_proxy labels at 16:00-16:10."""
        readings = generate_timeline(
            device_id="pune-comp-wika01",
            sensor_type="pressure",
            site_id="pune-isbm",
            node_id="compressor-01",
            poll_interval_s=60,
            start=_make_start(0),
            end=_make_start(0) + timedelta(hours=24),
            inject_scenarios=True,
        )

        leak_readings = [
            r for r in readings
            if r.get("scenario_label") == "leak_proxy"
        ]
        assert len(leak_readings) > 0

    def test_no_scenarios_when_disabled(self):
        """No scenario labels when inject_scenarios=False."""
        readings = generate_timeline(
            device_id="pune-comp-mfm384",
            sensor_type="electrical",
            site_id="pune-isbm",
            node_id="compressor-01",
            poll_interval_s=15,
            start=_make_start(0),
            end=_make_start(0) + timedelta(hours=24),
            inject_scenarios=False,
        )

        labeled = [
            r for r in readings
            if r.get("scenario_label") is not None
        ]
        assert len(labeled) == 0


# ═════════════════════════════════════════════════════════════════════════
# 3. Device mapping from edge config
# ═════════════════════════════════════════════════════════════════════════


class TestDeviceMapping:
    """Tests that the seed script correctly uses edge_nodes.json."""

    def test_get_devices_by_family(self):
        """All 7 families should be present in the mapping."""
        from omniview.edge.device_config import load_edge_config

        cfg = load_edge_config()
        by_family = _get_devices_by_family(cfg)

        # Should have all sensor types that exist in edge_nodes.json
        assert "electrical" in by_family
        assert "vibration" in by_family
        assert "thermal" in by_family
        assert "pressure" in by_family
        assert "gas" in by_family
        assert "stroke" in by_family
        assert "ambient" in by_family

    def test_electrical_has_two_devices(self):
        """Compressor + ISBM both have electrical meters."""
        from omniview.edge.device_config import load_edge_config

        cfg = load_edge_config()
        by_family = _get_devices_by_family(cfg)

        elec_devices = by_family["electrical"]
        assert len(elec_devices) == 2
        device_ids = {d["device_id"] for d in elec_devices}
        assert "pune-comp-mfm384" in device_ids
        assert "pune-isbm-mfm384" in device_ids

    def test_ambient_has_one_device(self):
        from omniview.edge.device_config import load_edge_config

        cfg = load_edge_config()
        by_family = _get_devices_by_family(cfg)

        assert len(by_family["ambient"]) == 1
        assert by_family["ambient"][0]["device_id"] == "pune-floor-ambient01"

    def test_device_dicts_have_required_keys(self):
        from omniview.edge.device_config import load_edge_config

        cfg = load_edge_config()
        by_family = _get_devices_by_family(cfg)

        for family, devices in by_family.items():
            for dev in devices:
                assert "device_id" in dev
                assert "node_id" in dev
                assert "poll_interval_s" in dev

    def test_total_device_count_is_nine(self):
        from omniview.edge.device_config import load_edge_config

        cfg = load_edge_config()
        by_family = _get_devices_by_family(cfg)

        total = sum(len(devs) for devs in by_family.values())
        assert total == 9


# ═════════════════════════════════════════════════════════════════════════
# 4. seed_sensor_family with mocked DB
# ═════════════════════════════════════════════════════════════════════════


class TestSeedSensorFamily:
    """Tests for seed_sensor_family() with mocked backfill."""

    @patch("omniview.ingest.seed.backfill_insert")
    def test_dry_run_skips_insert(self, mock_backfill):
        result = seed_sensor_family(
            sensor_type="electrical",
            site_id="pune-isbm",
            devices=[{
                "device_id": "test-01",
                "node_id": "compressor-01",
                "poll_interval_s": 15,
            }],
            start=_make_start(0),
            end=_make_start(1),
            inject_scenarios=False,
            dry_run=True,
        )

        mock_backfill.assert_not_called()
        assert result.readings_generated == 240
        assert result.readings_inserted == 0

    @patch("omniview.ingest.seed.backfill_insert")
    def test_live_calls_backfill(self, mock_backfill):
        mock_backfill.return_value = MagicMock(
            inserted=240, duplicates=0
        )
        result = seed_sensor_family(
            sensor_type="electrical",
            site_id="pune-isbm",
            devices=[{
                "device_id": "test-01",
                "node_id": "compressor-01",
                "poll_interval_s": 15,
            }],
            start=_make_start(0),
            end=_make_start(1),
            inject_scenarios=False,
            dry_run=False,
        )

        mock_backfill.assert_called_once()
        assert result.readings_generated == 240
        assert result.readings_inserted == 240

    @patch("omniview.ingest.seed.backfill_insert")
    def test_idempotent_second_run(self, mock_backfill):
        """Second run should report all duplicates."""
        mock_backfill.return_value = MagicMock(
            inserted=0, duplicates=240
        )
        result = seed_sensor_family(
            sensor_type="electrical",
            site_id="pune-isbm",
            devices=[{
                "device_id": "test-01",
                "node_id": "compressor-01",
                "poll_interval_s": 15,
            }],
            start=_make_start(0),
            end=_make_start(1),
            inject_scenarios=False,
            dry_run=False,
        )

        assert result.readings_generated == 240
        assert result.readings_inserted == 0
        assert result.readings_duplicates == 240

    @patch("omniview.ingest.seed.backfill_insert")
    def test_multiple_devices_merged(self, mock_backfill):
        """Two electrical devices → readings merged in one backfill call."""
        mock_backfill.return_value = MagicMock(
            inserted=480, duplicates=0
        )
        result = seed_sensor_family(
            sensor_type="electrical",
            site_id="pune-isbm",
            devices=[
                {
                    "device_id": "dev-01",
                    "node_id": "compressor-01",
                    "poll_interval_s": 15,
                },
                {
                    "device_id": "dev-02",
                    "node_id": "isbm-01",
                    "poll_interval_s": 15,
                },
            ],
            start=_make_start(0),
            end=_make_start(1),
            inject_scenarios=False,
            dry_run=False,
        )

        assert result.readings_generated == 480  # 240 × 2 devices
        assert result.devices_seeded == 2


# ═════════════════════════════════════════════════════════════════════════
# 5. seed_all with mocked DB
# ═════════════════════════════════════════════════════════════════════════


class TestSeedAll:
    """Tests for seed_all() — the main entry point."""

    @patch("omniview.ingest.seed.backfill_insert")
    def test_dry_run_generates_all_families(self, mock_backfill):
        result = seed_all(
            hours=1,
            start=_make_start(0),
            inject_scenarios=False,
            dry_run=True,
        )

        mock_backfill.assert_not_called()
        assert result.dry_run is True
        assert result.total_generated > 0
        assert len(result.families) == 7  # all 7 sensor families

    @patch("omniview.ingest.seed.backfill_insert")
    def test_families_filter(self, mock_backfill):
        mock_backfill.return_value = MagicMock(
            inserted=100, duplicates=0
        )
        result = seed_all(
            hours=1,
            start=_make_start(0),
            families=["electrical", "vibration"],
            dry_run=True,
        )

        assert len(result.families) == 2
        family_types = {f.sensor_type for f in result.families}
        assert family_types == {"electrical", "vibration"}

    @patch("omniview.ingest.seed.backfill_insert")
    def test_seed_result_has_elapsed_time(self, mock_backfill):
        result = seed_all(
            hours=1,
            start=_make_start(0),
            dry_run=True,
        )
        assert result.elapsed_seconds > 0

    @patch("omniview.ingest.seed.backfill_insert")
    def test_24h_total_reading_count(self, mock_backfill):
        """24h seed should generate ~25,920 readings total."""
        result = seed_all(
            hours=24,
            start=_make_start(0),
            inject_scenarios=False,
            dry_run=True,
        )

        # Expected: 2×5760 (electrical) + 1440 (vib) + 2×1440 (thermal)
        # + 1440 (pressure) + 1440 (gas) + 5760 (stroke) + 1440 (ambient)
        # = 11520 + 1440 + 2880 + 1440 + 1440 + 5760 + 1440 = 25920
        assert result.total_generated == 25920


# ═════════════════════════════════════════════════════════════════════════
# 6. Dataclass tests
# ═════════════════════════════════════════════════════════════════════════


class TestDataclasses:
    """Tests for SeedResult and FamilySeedResult."""

    def test_family_result_defaults(self):
        r = FamilySeedResult()
        assert r.sensor_type == ""
        assert r.readings_generated == 0
        assert r.readings_inserted == 0
        assert r.readings_duplicates == 0
        assert r.devices_seeded == 0

    def test_seed_result_defaults(self):
        r = SeedResult()
        assert r.families == []
        assert r.total_generated == 0
        assert r.total_inserted == 0
        assert r.total_duplicates == 0
        assert r.dry_run is False

    def test_seed_result_summary(self):
        r = SeedResult(
            families=[
                FamilySeedResult(
                    sensor_type="electrical",
                    readings_generated=100,
                    readings_inserted=95,
                    readings_duplicates=5,
                    devices_seeded=2,
                )
            ],
            total_generated=100,
            total_inserted=95,
            total_duplicates=5,
            elapsed_seconds=1.5,
        )
        s = r.summary()
        assert "electrical" in s
        assert "100" in s
        assert "95" in s
        assert "LIVE" in s

    def test_seed_result_summary_dry_run(self):
        r = SeedResult(dry_run=True)
        s = r.summary()
        assert "DRY RUN" in s


# ═════════════════════════════════════════════════════════════════════════
# 7. CLI parser tests
# ═════════════════════════════════════════════════════════════════════════


class TestCLI:
    """Tests for CLI argument parsing."""

    def test_parser_defaults(self):
        from omniview.ingest.seed import _build_parser

        parser = _build_parser()
        args = parser.parse_args([])
        assert args.hours == 24
        assert args.start is None
        assert args.no_scenarios is False
        assert args.families is None
        assert args.dry_run is False

    def test_parser_custom_hours(self):
        from omniview.ingest.seed import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--hours", "6"])
        assert args.hours == 6

    def test_parser_dry_run(self):
        from omniview.ingest.seed import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_parser_no_scenarios(self):
        from omniview.ingest.seed import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--no-scenarios"])
        assert args.no_scenarios is True

    def test_parser_families_filter(self):
        from omniview.ingest.seed import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--families", "electrical", "vibration"])
        assert args.families == ["electrical", "vibration"]
