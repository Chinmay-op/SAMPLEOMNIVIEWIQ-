"""
Tests for omniview.edge.injector — OI-12
==========================================

Unit tests for the CSV → MQTT electrical replay injector.
All MQTT interactions are mocked.
"""

from __future__ import annotations

import csv
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Column mapping tests ───────────────────────────────────────────────────


class TestColumnMapping:
    """Verify CSV column name auto-detection."""

    def test_exact_match(self) -> None:
        from omniview.edge.injector import _map_csv_columns

        header = ["voltage_r", "current_r", "kva_total", "pf_avg"]
        mapping = _map_csv_columns(header)
        assert mapping == {
            "voltage_r": "voltage_r",
            "current_r": "current_r",
            "kva_total": "kva_total",
            "pf_avg": "pf_avg",
        }

    def test_alias_match(self) -> None:
        from omniview.edge.injector import _map_csv_columns

        header = ["V_R", "I_R", "KVA", "PF", "KW"]
        mapping = _map_csv_columns(header)
        assert mapping["V_R"] == "voltage_r"
        assert mapping["I_R"] == "current_r"
        assert mapping["KVA"] == "kva_total"
        assert mapping["PF"] == "pf_avg"
        assert mapping["KW"] == "kw_total"

    def test_uci_steel_columns(self) -> None:
        """UCI Steel Industry dataset uses non-standard column names."""
        from omniview.edge.injector import _map_csv_columns

        header = [
            "Usage_kWh",
            "Lagging_Current_Reactive_Power_kVARh",
            "Leading_Current_Reactive_Power_kVARh",
            "Lagging_Current_Power_Factor",
        ]
        mapping = _map_csv_columns(header)
        assert len(mapping) >= 2  # should match at least some

    def test_no_match_returns_empty(self) -> None:
        from omniview.edge.injector import _map_csv_columns

        header = ["foo", "bar", "baz"]
        mapping = _map_csv_columns(header)
        assert mapping == {}

    def test_case_insensitive(self) -> None:
        from omniview.edge.injector import _map_csv_columns

        header = ["VOLTAGE_R", "Current_R", "kVa_Total"]
        mapping = _map_csv_columns(header)
        assert len(mapping) == 3


# ── CSV reader tests ───────────────────────────────────────────────────────


class TestReadCsvRows:
    """Verify CSV reading and mapping."""

    def _write_csv(self, path: Path, header: list[str], rows: list[list]) -> None:
        """Helper to write a test CSV."""
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)

    def test_reads_valid_csv(self, tmp_path: Path) -> None:
        from omniview.edge.injector import read_csv_rows

        csv_path = tmp_path / "test.csv"
        self._write_csv(
            csv_path,
            ["voltage_r", "current_r", "kva_total", "pf_avg"],
            [
                ["240.5", "100.2", "450.0", "0.85"],
                ["239.8", "101.1", "452.3", "0.84"],
            ],
        )

        rows = list(read_csv_rows(csv_path))
        assert len(rows) == 2
        assert rows[0]["voltage_r"] == 240.5
        assert rows[0]["kva_total"] == 450.0

    def test_file_not_found_raises(self) -> None:
        from omniview.edge.injector import read_csv_rows

        with pytest.raises(FileNotFoundError):
            list(read_csv_rows(Path("/nonexistent/file.csv")))

    def test_no_matching_columns_raises(self, tmp_path: Path) -> None:
        from omniview.edge.injector import read_csv_rows

        csv_path = tmp_path / "bad.csv"
        self._write_csv(csv_path, ["x", "y", "z"], [["1", "2", "3"]])

        with pytest.raises(ValueError, match="No recognised"):
            list(read_csv_rows(csv_path))

    def test_loop_replays(self, tmp_path: Path) -> None:
        from omniview.edge.injector import read_csv_rows

        csv_path = tmp_path / "loop.csv"
        self._write_csv(
            csv_path,
            ["kva_total", "pf_avg"],
            [["400", "0.85"], ["410", "0.86"]],
        )

        # Take 5 rows from a 2-row file with loop=True
        gen = read_csv_rows(csv_path, loop=True)
        rows = [next(gen) for _ in range(5)]
        assert len(rows) == 5
        # Should see the pattern repeat
        assert rows[0]["kva_total"] == rows[2]["kva_total"]


# ── Synthetic generator tests ──────────────────────────────────────────────


class TestSyntheticGenerator:
    """Verify synthetic data generation."""

    def test_generates_all_fields(self) -> None:
        from omniview.edge.injector import ELECTRICAL_FIELDS, generate_synthetic_readings

        gen = generate_synthetic_readings()
        reading = next(gen)

        for field in ELECTRICAL_FIELDS:
            assert field in reading, f"Missing field: {field}"

    def test_kva_in_reasonable_range(self) -> None:
        from omniview.edge.injector import generate_synthetic_readings

        gen = generate_synthetic_readings(contracted_kva=500.0)
        readings = [next(gen) for _ in range(100)]

        kvas = [r["kva_total"] for r in readings]
        assert min(kvas) > 0
        assert max(kvas) < 1000  # shouldn't exceed 2× contracted

    def test_deterministic_with_seed(self) -> None:
        from omniview.edge.injector import generate_synthetic_readings

        g1 = generate_synthetic_readings()
        g2 = generate_synthetic_readings()
        r1 = [next(g1) for _ in range(10)]
        r2 = [next(g2) for _ in range(10)]
        assert r1 == r2  # same seed → same output

    def test_pf_within_valid_range(self) -> None:
        from omniview.edge.injector import generate_synthetic_readings

        gen = generate_synthetic_readings()
        for _ in range(50):
            r = next(gen)
            assert 0.0 < r["pf_avg"] <= 1.0
            assert 0.0 < r["pf_r"] <= 1.0
            assert 0.0 < r["pf_y"] <= 1.0
            assert 0.0 < r["pf_b"] <= 1.0

    def test_cumulative_kwh_increases(self) -> None:
        from omniview.edge.injector import generate_synthetic_readings

        gen = generate_synthetic_readings()
        readings = [next(gen) for _ in range(20)]
        kwh_values = [r["kwh_total"] for r in readings]
        assert kwh_values == sorted(kwh_values)  # monotonically increasing


# ── Payload builder tests ──────────────────────────────────────────────────


class TestBuildPayload:
    """Verify payload envelope construction."""

    def test_includes_required_fields(self) -> None:
        from omniview.edge.injector import build_payload

        payload = build_payload({"kva_total": 450.0})
        assert "timestamp" in payload
        assert "sensor_type" in payload
        assert payload["sensor_type"] == "electrical"
        assert "schema_version" in payload
        assert "data" in payload
        assert payload["data"]["kva_total"] == 450.0

    def test_custom_timestamp(self) -> None:
        from omniview.edge.injector import build_payload

        ts = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
        payload = build_payload({"kva_total": 450.0}, timestamp=ts)
        assert payload["timestamp"] == "2026-08-10T12:00:00+00:00"


# ── ElectricalInjector tests ──────────────────────────────────────────────


class TestElectricalInjector:
    """Verify injector orchestration."""

    def test_default_topic(self) -> None:
        from omniview.edge.injector import ElectricalInjector

        inj = ElectricalInjector()
        assert "electrical" in inj.topic
        assert "compressor-01" in inj.topic

    def test_custom_node(self) -> None:
        from omniview.edge.injector import ElectricalInjector

        inj = ElectricalInjector(node_id="isbm-01")
        assert "isbm-01" in inj.topic

    def test_synthetic_publishes_messages(self) -> None:
        from omniview.edge.injector import ElectricalInjector

        mock_client = MagicMock()
        inj = ElectricalInjector(burst=True)

        count = inj.run_synthetic(mock_client, max_readings=10)
        assert count == 10
        assert mock_client.publish.call_count == 10

    def test_csv_publishes_messages(self, tmp_path: Path) -> None:
        from omniview.edge.injector import ElectricalInjector

        csv_path = tmp_path / "test.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["kva_total", "kw_total", "pf_avg"])
            for i in range(5):
                writer.writerow([400 + i, 340 + i, 0.85])

        mock_client = MagicMock()
        inj = ElectricalInjector(burst=True)

        count = inj.run_csv(csv_path, mock_client)
        assert count == 5
        assert mock_client.publish.call_count == 5

    def test_stop_halts_synthetic(self) -> None:
        from omniview.edge.injector import ElectricalInjector

        mock_client = MagicMock()
        inj = ElectricalInjector(burst=True)

        # Stop after 3 publishes via a side effect
        call_count = {"n": 0}
        original_publish = mock_client.publish

        def counting_publish(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] >= 3:
                inj.stop()

        mock_client.publish.side_effect = counting_publish

        count = inj.run_synthetic(mock_client, max_readings=100)
        assert count == 3

    def test_published_count_tracks(self) -> None:
        from omniview.edge.injector import ElectricalInjector

        mock_client = MagicMock()
        inj = ElectricalInjector(burst=True)

        assert inj.published_count == 0
        inj.run_synthetic(mock_client, max_readings=7)
        assert inj.published_count == 7


# ── CLI parser tests ───────────────────────────────────────────────────────


class TestCLI:
    """Verify argument parsing."""

    def test_csv_argument(self) -> None:
        from omniview.edge.injector import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--csv", "data/replay.csv"])
        assert args.csv == Path("data/replay.csv")
        assert not args.synthetic

    def test_synthetic_argument(self) -> None:
        from omniview.edge.injector import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--synthetic"])
        assert args.synthetic
        assert args.csv is None

    def test_speed_argument(self) -> None:
        from omniview.edge.injector import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--synthetic", "--speed", "5"])
        assert args.speed == 5.0

    def test_burst_argument(self) -> None:
        from omniview.edge.injector import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--synthetic", "--burst"])
        assert args.burst is True

    def test_mutually_exclusive(self) -> None:
        from omniview.edge.injector import _build_parser

        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--csv", "file.csv", "--synthetic"])

    def test_requires_source(self) -> None:
        from omniview.edge.injector import _build_parser

        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])
