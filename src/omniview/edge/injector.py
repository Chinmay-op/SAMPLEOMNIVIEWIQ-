"""
CSV → MQTT Electrical Replay Injector — OI-12
===============================================

Reads an electrical-parameter CSV (from DevB's replay bot, OI-8) and publishes
rows as timestamped JSON payloads to the MQTT broker at the configured poll
interval (default 15 s).

This is the Day-1 mechanism for seeding the pipeline without live hardware.

Features:

* Reads any CSV with electrical columns (auto-detects column mapping)
* Publishes to ``omniview/{site_id}/{node_id}/electrical`` via OI-51 MQTT
* Configurable replay speed (real-time, accelerated, or burst)
* Built-in synthetic generator for demo/testing when no CSV is available
* Loops the CSV for continuous operation (optional)
* Graceful shutdown via Ctrl+C / SIGTERM

Usage::

    # Replay from a CSV file
    python -m omniview.edge.injector --csv data/electrical_replay.csv

    # Use built-in synthetic data (no CSV needed)
    python -m omniview.edge.injector --synthetic

    # Fast replay (5x speed)
    python -m omniview.edge.injector --csv data/replay.csv --speed 5

    # Burst mode (no delay — for backfilling TSDB)
    python -m omniview.edge.injector --csv data/replay.csv --burst

    # Target a specific node (default: compressor-01)
    python -m omniview.edge.injector --synthetic --node isbm-01
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import math
import random
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from omniview.config import (
    CONTRACTED_DEMAND_KVA,
    POLL_ELECTRICAL_INTERVAL,
    SITE_ID,
)
from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.topics import build_topic

logger = logging.getLogger(__name__)

# ── Electrical parameter contract ───────────────────────────────────────────
# These are the fields the downstream rule engine (OI-56) and dashboard
# (OI-68) expect in the JSONB `data` column.  Matches the Selec MFM384
# Modbus register map and PRD §2.5 FR1.

ELECTRICAL_FIELDS: list[str] = [
    "voltage_r",        # V phase R (line-to-neutral)
    "voltage_y",        # V phase Y
    "voltage_b",        # V phase B
    "voltage_avg",      # V average
    "current_r",        # A phase R
    "current_y",        # A phase Y
    "current_b",        # A phase B
    "current_avg",      # A average
    "current_neutral",  # A neutral
    "kw_total",         # kW total active power
    "kw_r",             # kW phase R
    "kw_y",             # kW phase Y
    "kw_b",             # kW phase B
    "kva_total",        # kVA total apparent power
    "kvar_total",       # kVAR total reactive power
    "pf_avg",           # Power factor average
    "pf_r",             # Power factor phase R
    "pf_y",             # Power factor phase Y
    "pf_b",             # Power factor phase B
    "frequency",        # Hz
    "thd_v_avg",        # Voltage THD %
    "thd_i_avg",        # Current THD %
    "kwh_total",        # kWh cumulative
]

# ── Column name mapping (handles common CSV naming conventions) ─────────────

_COLUMN_ALIASES: dict[str, list[str]] = {
    "voltage_r": ["voltage_r", "v_r", "vr", "voltage_phase_r", "v_rn", "voltage_rn"],
    "voltage_y": ["voltage_y", "v_y", "vy", "voltage_phase_y", "v_yn", "voltage_yn"],
    "voltage_b": ["voltage_b", "v_b", "vb", "voltage_phase_b", "v_bn", "voltage_bn"],
    "voltage_avg": ["voltage_avg", "v_avg", "voltage_average", "voltage"],
    "current_r": ["current_r", "i_r", "ir", "current_phase_r", "amp_r"],
    "current_y": ["current_y", "i_y", "iy", "current_phase_y", "amp_y"],
    "current_b": ["current_b", "i_b", "ib", "current_phase_b", "amp_b"],
    "current_avg": ["current_avg", "i_avg", "current_average", "current"],
    "current_neutral": ["current_neutral", "i_n", "in_", "neutral_current"],
    "kw_total": [
        "kw_total", "kw", "active_power", "power_kw", "lagging_current_reactive_power_kvarh",
        "usage_kwh", "total_kw",
    ],
    "kw_r": ["kw_r", "kw_phase_r", "active_power_r"],
    "kw_y": ["kw_y", "kw_phase_y", "active_power_y"],
    "kw_b": ["kw_b", "kw_phase_b", "active_power_b"],
    "kva_total": [
        "kva_total", "kva", "apparent_power", "power_kva",
        "leading_current_reactive_power_kvarh", "total_kva",
    ],
    "kvar_total": ["kvar_total", "kvar", "reactive_power", "power_kvar"],
    "pf_avg": [
        "pf_avg", "pf", "power_factor", "lagging_current_power_factor",
        "leading_current_power_factor", "power_factor_avg",
    ],
    "pf_r": ["pf_r", "power_factor_r", "pf_phase_r"],
    "pf_y": ["pf_y", "power_factor_y", "pf_phase_y"],
    "pf_b": ["pf_b", "power_factor_b", "pf_phase_b"],
    "frequency": ["frequency", "freq", "hz"],
    "thd_v_avg": ["thd_v_avg", "thd_v", "voltage_thd", "thd_voltage"],
    "thd_i_avg": ["thd_i_avg", "thd_i", "current_thd", "thd_current"],
    "kwh_total": ["kwh_total", "kwh", "energy_kwh", "cumulative_kwh", "total_kwh"],
}

# Reverse map: alias → canonical name
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for canonical, aliases in _COLUMN_ALIASES.items():
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias.lower()] = canonical


def _map_csv_columns(header: list[str]) -> dict[str, str]:
    """Map CSV column names to canonical electrical field names.

    Parameters
    ----------
    header : list[str]
        CSV header row.

    Returns
    -------
    dict[str, str]
        Mapping from CSV column name → canonical field name.
    """
    mapping: dict[str, str] = {}
    for col in header:
        normalised = col.strip().lower().replace(" ", "_").replace("-", "_")
        if normalised in _ALIAS_TO_CANONICAL:
            mapping[col] = _ALIAS_TO_CANONICAL[normalised]
    return mapping


# ── CSV reader ──────────────────────────────────────────────────────────────


def read_csv_rows(
    csv_path: Path,
    loop: bool = False,
) -> Generator[dict[str, Any], None, None]:
    """Yield electrical readings from a CSV file.

    Parameters
    ----------
    csv_path : Path
        Path to the CSV file.
    loop : bool
        If ``True``, restart from the beginning when the file ends.

    Yields
    ------
    dict[str, Any]
        Each row mapped to canonical electrical field names.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    while True:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise ValueError(f"CSV file has no header row: {csv_path}")

            col_map = _map_csv_columns(list(reader.fieldnames))
            if not col_map:
                raise ValueError(
                    f"No recognised electrical columns in CSV. "
                    f"Header: {reader.fieldnames}. "
                    f"Expected columns like: {', '.join(ELECTRICAL_FIELDS[:6])}"
                )

            logger.info(
                "CSV column mapping (%d/%d matched): %s",
                len(col_map),
                len(ELECTRICAL_FIELDS),
                col_map,
            )

            row_count = 0
            for row in reader:
                data: dict[str, Any] = {}
                for csv_col, canonical in col_map.items():
                    raw = row.get(csv_col, "").strip()
                    if raw:
                        try:
                            data[canonical] = float(raw)
                        except ValueError:
                            data[canonical] = raw
                if data:
                    row_count += 1
                    yield data

            logger.info("CSV pass complete: %d rows read from %s", row_count, csv_path.name)

        if not loop:
            break
        logger.info("Looping CSV replay…")


# ── Synthetic data generator ────────────────────────────────────────────────


def generate_synthetic_readings(
    contracted_kva: float = CONTRACTED_DEMAND_KVA,
    include_md_spike: bool = True,
) -> Generator[dict[str, Any], None, None]:
    """Generate realistic synthetic electrical readings indefinitely.

    Simulates a factory load profile with:
    - Base load around 60-75% of contracted demand
    - Random fluctuations (±5%)
    - Occasional load ramps (simulating machine starts)
    - Optional MD near-miss spikes (reaches 90-105% of contracted demand)

    Parameters
    ----------
    contracted_kva : float
        Contracted maximum demand in kVA.
    include_md_spike : bool
        If ``True``, inject periodic demand spikes for MD-alert testing.

    Yields
    ------
    dict[str, Any]
        Synthetic electrical reading with all canonical fields.
    """
    base_kva = contracted_kva * 0.65  # 65% base load
    cumulative_kwh = 0.0
    step = 0
    rng = random.Random(42)  # deterministic for reproducibility

    while True:
        # ── Load profile simulation ─────────────────────────────────────
        t_hours = (step * POLL_ELECTRICAL_INTERVAL) / 3600.0

        # Diurnal pattern: sinusoidal variation over 24h
        diurnal = 1.0 + 0.15 * math.sin(2 * math.pi * t_hours / 24.0)

        # Random noise ±5%
        noise = 1.0 + rng.gauss(0, 0.025)

        # Occasional machine start ramp (every ~200 steps, 5% chance)
        ramp = 1.0
        if rng.random() < 0.005:
            ramp = 1.0 + rng.uniform(0.1, 0.25)  # 10-25% spike

        # MD near-miss spike (every ~400 steps)
        md_spike = 1.0
        if include_md_spike and step > 0 and step % 400 == 0:
            md_spike = 1.0 + rng.uniform(0.3, 0.55)  # Push to 90-105% contracted
            logger.info(
                "🔴 Injecting MD near-miss spike at step %d (kVA will reach ~%.0f)",
                step,
                base_kva * diurnal * md_spike,
            )

        kva = base_kva * diurnal * noise * ramp * md_spike
        kva = max(0.0, kva)  # no negative

        # ── Derive other parameters from kVA ────────────────────────────
        pf = rng.uniform(0.82, 0.92)  # typical industrial PF
        kw = kva * pf
        kvar = math.sqrt(max(0, kva**2 - kw**2))

        # Voltage: 415V ±3% three-phase
        v_base = 415.0 / math.sqrt(3)  # line-to-neutral ~239.6V
        v_r = v_base * (1.0 + rng.gauss(0, 0.01))
        v_y = v_base * (1.0 + rng.gauss(0, 0.01))
        v_b = v_base * (1.0 + rng.gauss(0, 0.01))
        v_avg = (v_r + v_y + v_b) / 3.0

        # Current: derived from kVA / (sqrt(3) * V_LL)
        i_total = (kva * 1000.0) / (math.sqrt(3) * 415.0)
        # Slight phase imbalance
        i_r = i_total * (1.0 + rng.gauss(0, 0.03))
        i_y = i_total * (1.0 + rng.gauss(0, 0.03))
        i_b = i_total * (1.0 + rng.gauss(0, 0.03))
        i_avg = (i_r + i_y + i_b) / 3.0
        i_n = abs(i_r - i_y) * rng.uniform(0.1, 0.3)  # small neutral

        # Per-phase power (roughly equal split)
        kw_r = kw / 3.0 * (1.0 + rng.gauss(0, 0.02))
        kw_y = kw / 3.0 * (1.0 + rng.gauss(0, 0.02))
        kw_b = kw - kw_r - kw_y  # ensure sum = total

        # Per-phase PF (slight variation)
        pf_r = pf * (1.0 + rng.gauss(0, 0.01))
        pf_y = pf * (1.0 + rng.gauss(0, 0.01))
        pf_b = pf * (1.0 + rng.gauss(0, 0.01))

        # Frequency
        freq = 50.0 + rng.gauss(0, 0.05)

        # THD
        thd_v = rng.uniform(1.5, 4.5)  # typical 2-4%
        thd_i = rng.uniform(5.0, 15.0)  # typical 5-12%

        # Cumulative energy
        cumulative_kwh += kw * (POLL_ELECTRICAL_INTERVAL / 3600.0)

        reading = {
            "voltage_r": round(v_r, 2),
            "voltage_y": round(v_y, 2),
            "voltage_b": round(v_b, 2),
            "voltage_avg": round(v_avg, 2),
            "current_r": round(i_r, 2),
            "current_y": round(i_y, 2),
            "current_b": round(i_b, 2),
            "current_avg": round(i_avg, 2),
            "current_neutral": round(i_n, 2),
            "kw_total": round(kw, 3),
            "kw_r": round(kw_r, 3),
            "kw_y": round(kw_y, 3),
            "kw_b": round(kw_b, 3),
            "kva_total": round(kva, 3),
            "kvar_total": round(kvar, 3),
            "pf_avg": round(pf, 4),
            "pf_r": round(min(1.0, abs(pf_r)), 4),
            "pf_y": round(min(1.0, abs(pf_y)), 4),
            "pf_b": round(min(1.0, abs(pf_b)), 4),
            "frequency": round(freq, 2),
            "thd_v_avg": round(thd_v, 2),
            "thd_i_avg": round(thd_i, 2),
            "kwh_total": round(cumulative_kwh, 3),
        }

        step += 1
        yield reading


# ── Payload builder ─────────────────────────────────────────────────────────


def build_payload(
    data: dict[str, Any],
    timestamp: datetime | None = None,
    schema_version: str = "1.0",
) -> dict[str, Any]:
    """Wrap a data dict into the standard OmniView payload envelope.

    Parameters
    ----------
    data : dict
        Electrical reading data.
    timestamp : datetime, optional
        Reading timestamp.  Defaults to UTC now.
    schema_version : str
        Schema version tag.

    Returns
    -------
    dict
        Payload with ``timestamp``, ``schema_version``, ``sensor_type``,
        ``data``, and ``device_id`` fields.
    """
    ts = timestamp or datetime.now(timezone.utc)
    return {
        "timestamp": ts.isoformat(),
        "sensor_type": "electrical",
        "schema_version": schema_version,
        "data": data,
    }


# ── Injector core ──────────────────────────────────────────────────────────


class ElectricalInjector:
    """CSV / synthetic → MQTT electrical replay injector.

    Parameters
    ----------
    site_id : str
        Site identifier (default from config).
    node_id : str
        Node to publish to (default ``"compressor-01"``).
    interval : float
        Seconds between publishes (default from config: 15s).
    speed : float
        Replay speed multiplier (e.g. 5.0 = 5× faster).
    burst : bool
        If ``True``, publish all rows without delay.
    """

    def __init__(
        self,
        site_id: str = SITE_ID,
        node_id: str = "compressor-01",
        interval: float = POLL_ELECTRICAL_INTERVAL,
        speed: float = 1.0,
        burst: bool = False,
    ) -> None:
        self.site_id = site_id
        self.node_id = node_id
        self.interval = interval
        self.speed = speed
        self.burst = burst
        self.topic = build_topic(site_id, node_id, "electrical")
        self._stop = False
        self._published = 0

    @property
    def published_count(self) -> int:
        """Number of messages published so far."""
        return self._published

    def stop(self) -> None:
        """Signal the injector to stop after the current publish."""
        self._stop = True

    def run_csv(
        self,
        csv_path: Path,
        client: OmniViewMQTTClient,
        loop: bool = False,
    ) -> int:
        """Replay a CSV file through MQTT.

        Parameters
        ----------
        csv_path : Path
            Path to the electrical CSV.
        client : OmniViewMQTTClient
            Connected MQTT client.
        loop : bool
            Loop the CSV indefinitely.

        Returns
        -------
        int
            Number of messages published.
        """
        logger.info(
            "Starting CSV replay: %s → %s (interval=%.1fs, speed=%.1fx, loop=%s)",
            csv_path.name,
            self.topic,
            self.interval,
            self.speed,
            loop,
        )

        for data in read_csv_rows(csv_path, loop=loop):
            if self._stop:
                break
            self._publish_one(client, data)

        logger.info("CSV replay finished: %d messages published", self._published)
        return self._published

    def run_synthetic(
        self,
        client: OmniViewMQTTClient,
        max_readings: int | None = None,
    ) -> int:
        """Generate and publish synthetic electrical data.

        Parameters
        ----------
        client : OmniViewMQTTClient
            Connected MQTT client.
        max_readings : int, optional
            Stop after this many readings.  ``None`` = run until stopped.

        Returns
        -------
        int
            Number of messages published.
        """
        logger.info(
            "Starting synthetic replay → %s (interval=%.1fs, speed=%.1fx, max=%s)",
            self.topic,
            self.interval,
            self.speed,
            max_readings or "∞",
        )

        for i, data in enumerate(generate_synthetic_readings()):
            if self._stop:
                break
            if max_readings is not None and i >= max_readings:
                break
            self._publish_one(client, data)

        logger.info("Synthetic replay finished: %d messages published", self._published)
        return self._published

    def _publish_one(
        self, client: OmniViewMQTTClient, data: dict[str, Any]
    ) -> None:
        """Publish a single reading and sleep for the configured interval."""
        payload = build_payload(data)
        client.publish(self.topic, payload)
        self._published += 1

        if self._published % 50 == 0 or self._published == 1:
            kva = data.get("kva_total", "?")
            kw = data.get("kw_total", "?")
            pf = data.get("pf_avg", "?")
            logger.info(
                "[%d] Published → %s | kVA=%s kW=%s PF=%s",
                self._published,
                self.topic,
                kva,
                kw,
                pf,
            )

        if not self.burst:
            delay = self.interval / self.speed
            time.sleep(delay)


# ── CLI ─────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="omniview.edge.injector",
        description=(
            "CSV → MQTT Electrical Replay Injector (OI-12). "
            "Publishes electrical readings to the MQTT broker for Day-1 "
            "pipeline testing without live Modbus hardware."
        ),
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--csv",
        type=Path,
        metavar="FILE",
        help="Path to an electrical-parameter CSV file.",
    )
    source.add_argument(
        "--synthetic",
        action="store_true",
        help="Use built-in synthetic data generator (no CSV needed).",
    )

    parser.add_argument(
        "--node",
        default="compressor-01",
        help="Target node_id (default: compressor-01).",
    )
    parser.add_argument(
        "--site",
        default=SITE_ID,
        help=f"Site identifier (default: {SITE_ID}).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=POLL_ELECTRICAL_INTERVAL,
        help=f"Seconds between publishes (default: {POLL_ELECTRICAL_INTERVAL}).",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Replay speed multiplier (e.g. 5 = 5× faster). Default: 1.0.",
    )
    parser.add_argument(
        "--burst",
        action="store_true",
        help="Publish all rows without delay (for bulk TSDB seeding).",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Loop the CSV file indefinitely (ignored for --synthetic).",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        metavar="N",
        help="Stop after N readings (synthetic mode only).",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for the CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    injector = ElectricalInjector(
        site_id=args.site,
        node_id=args.node,
        interval=args.interval,
        speed=args.speed,
        burst=args.burst,
    )

    # Graceful shutdown
    def _signal_handler(signum: int, _frame: Any) -> None:
        logger.info("Received signal %d — stopping injector", signum)
        injector.stop()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        with OmniViewMQTTClient() as client:
            if args.csv:
                injector.run_csv(args.csv, client, loop=args.loop)
            else:
                injector.run_synthetic(client, max_readings=args.max)
    except ConnectionError as exc:
        logger.error("MQTT connection failed: %s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted — exiting")


if __name__ == "__main__":
    main()
