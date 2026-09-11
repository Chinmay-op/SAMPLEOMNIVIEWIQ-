"""
Day-1 Seed Script — OI-55
===========================

One-command loader that populates TimescaleDB with a 24-hour hybrid
dataset for demos, dashboard development, and rule-engine testing —
**without requiring live edge hardware, MQTT, or running bots**.

What it does
------------
1. Reads the device manifest from ``config/edge_nodes.json`` (OI-52).
2. For each of the 9 devices, generates a chronological timeline of
   sensor readings using DevB's bot ``generate_reading()`` functions.
3. Injects three labeled scenarios into the stream (MD near-miss,
   lazy-idle, pressure-decay leak proxy) so the rule engine has
   something to detect out of the box.
4. Loads all readings into TimescaleDB via ``backfill_insert()`` (OI-15),
   which is idempotent — re-running is a safe no-op.

Usage::

    # Default: 24 hours of data for all families
    python -m omniview.ingest.seed

    # Custom: 6 hours, skip scenarios
    python -m omniview.ingest.seed --hours 6 --no-scenarios

    # Dry run: generate + count, don't insert
    python -m omniview.ingest.seed --dry-run

    # Specific families only
    python -m omniview.ingest.seed --families electrical vibration

Depends on
----------
- OI-54 (hypertables + migrations)
- OI-15 (backfill_insert with BackfillResult)
- OI-52 (edge_nodes.json device manifest)
- DevB bots (generate_reading functions)
"""

from __future__ import annotations

import argparse
import logging
import math
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from omniview.edge.bots import (
    generate_ambient,
    generate_electrical,
    generate_gas,
    generate_pressure,
    generate_stroke,
    generate_thermal,
    generate_vibration,
)
from omniview.edge.device_config import load_edge_config
from omniview.edge.topics import SENSOR_TYPES
from omniview.ingest.db import BackfillResult, backfill_insert

logger = logging.getLogger(__name__)

# ── Timezone ─────────────────────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))

# ── Bot generator mapping ───────────────────────────────────────────────

# Maps sensor_type → bot generate_reading function.
# Each function returns a dict with device_id, timestamp, sensor_type, data.
_BOT_GENERATORS: dict[str, Any] = {
    "electrical": generate_electrical,
    "vibration": generate_vibration,
    "thermal": generate_thermal,
    "pressure": generate_pressure,
    "gas": generate_gas,
    "stroke": generate_stroke,
    "ambient": generate_ambient,
}


# ── Result types ─────────────────────────────────────────────────────────


@dataclass
class FamilySeedResult:
    """Result of seeding one sensor family."""

    sensor_type: str = ""
    readings_generated: int = 0
    readings_inserted: int = 0
    readings_duplicates: int = 0
    devices_seeded: int = 0


@dataclass
class SeedResult:
    """Aggregate result of the full seed operation."""

    families: list[FamilySeedResult] = field(default_factory=list)
    total_generated: int = 0
    total_inserted: int = 0
    total_duplicates: int = 0
    elapsed_seconds: float = 0.0
    dry_run: bool = False

    def summary(self) -> str:
        """Human-readable summary string."""
        lines = [
            "=" * 60,
            "OI-55 Seed Summary",
            "=" * 60,
        ]
        for f in self.families:
            lines.append(
                f"  {f.sensor_type:12s}  "
                f"generated={f.readings_generated:>6,}  "
                f"inserted={f.readings_inserted:>6,}  "
                f"duplicates={f.readings_duplicates:>6,}  "
                f"devices={f.devices_seeded}"
            )
        lines.append("-" * 60)
        mode = "DRY RUN" if self.dry_run else "LIVE"
        lines.append(
            f"  TOTAL [{mode}]  "
            f"generated={self.total_generated:>6,}  "
            f"inserted={self.total_inserted:>6,}  "
            f"duplicates={self.total_duplicates:>6,}  "
            f"elapsed={self.elapsed_seconds:.1f}s"
        )
        lines.append("=" * 60)
        return "\n".join(lines)


# ── Scenario injection ──────────────────────────────────────────────────


def _inject_md_nearmiss(
    reading: dict[str, Any],
    t: datetime,
    scenario_start: datetime,
    scenario_end: datetime,
) -> dict[str, Any]:
    """Inject MD near-miss: kVA ramps 350 → 480 → 350 over the window."""
    progress = (t - scenario_start).total_seconds() / (
        scenario_end - scenario_start
    ).total_seconds()

    # Bell curve: peaks at midpoint
    peak_factor = math.sin(progress * math.pi)
    kva = 350.0 + (130.0 * peak_factor)  # 350 → 480 → 350
    kw = kva * 0.92  # high PF during peak load
    current = kva * 1000 / (415 * 1.732)

    data = reading["data"].copy()
    data["apparent_power_kva_total"] = round(kva, 2)
    data["active_power_kw_total"] = round(kw, 2)
    data["current_a_avg"] = round(current, 2)
    data["rolling_kva_15min"] = round(kva + random.uniform(-5, 5), 2)
    data["md_proximity_percent"] = round((kva / 500.0) * 100, 2)

    result = {**reading, "data": data}
    result["scenario_label"] = "md_nearmiss"
    return result


def _inject_lazy_idle_electrical(
    reading: dict[str, Any],
) -> dict[str, Any]:
    """Inject lazy-idle: ISBM current drops but machine stays on."""
    data = reading["data"].copy()
    data["current_a_avg"] = round(random.uniform(3.0, 8.0), 2)
    data["active_power_kw_total"] = round(random.uniform(1.5, 4.0), 2)
    data["apparent_power_kva_total"] = round(random.uniform(2.0, 5.0), 2)
    data["power_factor_avg"] = round(random.uniform(0.4, 0.6), 3)
    result = {**reading, "data": data}
    result["scenario_label"] = "lazy_idle"
    return result


def _inject_lazy_idle_thermal(
    reading: dict[str, Any],
) -> dict[str, Any]:
    """Inject lazy-idle: barrel temp stays elevated despite low current."""
    data = reading["data"].copy()
    # Thermal bot data keys
    if "barrel_temp_c" in data:
        data["barrel_temp_c"] = round(random.uniform(240.0, 258.0), 1)
    elif "process_variable_c" in data:
        data["process_variable_c"] = round(random.uniform(240.0, 258.0), 1)
    elif "temperature_c" in data:
        data["temperature_c"] = round(random.uniform(240.0, 258.0), 1)
    result = {**reading, "data": data}
    result["scenario_label"] = "lazy_idle"
    return result


def _inject_leak_proxy(
    reading: dict[str, Any],
    t: datetime,
    scenario_start: datetime,
    scenario_end: datetime,
) -> dict[str, Any]:
    """Inject leak proxy: pressure decays 33 → 22 bar over the window."""
    progress = (t - scenario_start).total_seconds() / (
        scenario_end - scenario_start
    ).total_seconds()

    pressure = 33.0 - (11.0 * progress)  # 33 → 22 bar linear decay
    data = reading["data"].copy()

    # Pressure bot data keys
    if "pressure_bar" in data:
        data["pressure_bar"] = round(pressure, 2)
        data["pressure_psi"] = round(pressure * 14.5038, 2)
    elif "discharge_pressure_bar" in data:
        data["discharge_pressure_bar"] = round(pressure, 2)

    result = {**reading, "data": data}
    result["scenario_label"] = "leak_proxy"
    return result


# ── Timeline generation ─────────────────────────────────────────────────


def generate_timeline(
    *,
    device_id: str,
    sensor_type: str,
    site_id: str,
    node_id: str,
    poll_interval_s: int,
    start: datetime,
    end: datetime,
    inject_scenarios: bool = True,
) -> list[dict[str, Any]]:
    """Generate a chronological list of readings for one device.

    Uses the appropriate DevB bot generator for the sensor type, then
    overlays scenario injections at predefined time windows.

    Parameters
    ----------
    device_id : str
        Physical device ID from edge_nodes.json.
    sensor_type : str
        One of the 7 sensor families.
    site_id : str
        Site identifier (e.g. "pune-isbm").
    node_id : str
        Node identifier (e.g. "compressor-01").
    poll_interval_s : int
        Seconds between readings.
    start : datetime
        Timeline start (inclusive).
    end : datetime
        Timeline end (exclusive).
    inject_scenarios : bool
        Whether to inject labeled scenarios into the stream.

    Returns
    -------
    list[dict]
        Each dict has keys: device_id, site_id, time, data, schema_version.
        Ready for ``backfill_insert()``.
    """
    generator = _BOT_GENERATORS.get(sensor_type)
    if generator is None:
        logger.warning(
            "No bot generator for sensor_type %r, skipping device %s",
            sensor_type,
            device_id,
        )
        return []

    # Scenario time windows (relative to start date)
    base_date = start.replace(hour=0, minute=0, second=0, microsecond=0)
    md_start = base_date.replace(hour=10, minute=15)
    md_end = base_date.replace(hour=10, minute=45)
    idle_start = base_date.replace(hour=14, minute=0)
    idle_end = base_date.replace(hour=14, minute=20)
    leak_start = base_date.replace(hour=16, minute=0)
    leak_end = base_date.replace(hour=16, minute=10)

    readings: list[dict[str, Any]] = []
    t = start

    while t < end:
        # Generate base reading from DevB bot
        # All bots use generate_reading() with no args after DevB refactor
        raw = generator()

        # Extract the data payload from the bot output
        data = raw.get("data", raw)

        reading = {
            "device_id": device_id,
            "site_id": site_id,
            "time": t,
            "data": data,
            "schema_version": "1.0",
        }

        # ── Scenario injection ──────────────────────────────────────
        if inject_scenarios and md_start <= t < md_end:
            # MD near-miss: affects compressor + ISBM electrical
            if sensor_type == "electrical":
                reading = _inject_md_nearmiss(
                    reading, t, md_start, md_end
                )

        if inject_scenarios and idle_start <= t < idle_end:
            # Lazy-idle: affects ISBM electrical + thermal
            if (
                sensor_type == "electrical"
                and node_id == "isbm-01"
            ):
                reading = _inject_lazy_idle_electrical(reading)
            elif (
                sensor_type == "thermal"
                and node_id == "isbm-01"
            ):
                reading = _inject_lazy_idle_thermal(reading)

        if inject_scenarios and leak_start <= t < leak_end:
            # Leak proxy: affects compressor pressure
            if (
                sensor_type == "pressure"
                and node_id == "compressor-01"
            ):
                reading = _inject_leak_proxy(
                    reading, t, leak_start, leak_end
                )

        readings.append(reading)
        t += timedelta(seconds=poll_interval_s)

    return readings


# ── Seed functions ───────────────────────────────────────────────────────


def seed_sensor_family(
    *,
    sensor_type: str,
    site_id: str,
    devices: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    inject_scenarios: bool = True,
    dry_run: bool = False,
    engine: Any = None,
) -> FamilySeedResult:
    """Seed one sensor family across all devices that have it.

    Parameters
    ----------
    sensor_type : str
        Sensor family to seed.
    site_id : str
        Site identifier.
    devices : list[dict]
        List of dicts with keys: device_id, node_id, poll_interval_s.
    start, end : datetime
        Time window for the generated data.
    inject_scenarios : bool
        Whether to inject scenario labels.
    dry_run : bool
        If True, generate but don't insert.
    engine : optional
        SQLAlchemy engine override (for testing).

    Returns
    -------
    FamilySeedResult
    """
    result = FamilySeedResult(
        sensor_type=sensor_type,
        devices_seeded=len(devices),
    )

    all_readings: list[dict[str, Any]] = []

    for dev in devices:
        timeline = generate_timeline(
            device_id=dev["device_id"],
            sensor_type=sensor_type,
            site_id=site_id,
            node_id=dev["node_id"],
            poll_interval_s=dev["poll_interval_s"],
            start=start,
            end=end,
            inject_scenarios=inject_scenarios,
        )
        all_readings.extend(timeline)

    # Sort chronologically for backfill
    all_readings.sort(key=lambda r: r["time"])
    result.readings_generated = len(all_readings)

    if dry_run:
        logger.info(
            "[DRY RUN] %s: %d readings generated for %d devices",
            sensor_type,
            result.readings_generated,
            len(devices),
        )
        return result

    if not all_readings:
        return result

    # Use backfill_insert (OI-15) — idempotent
    backfill_kwargs: dict[str, Any] = {
        "sensor_type": sensor_type,
        "readings": all_readings,
    }
    if engine is not None:
        backfill_kwargs["engine"] = engine

    bf_result: BackfillResult = backfill_insert(**backfill_kwargs)
    result.readings_inserted = bf_result.inserted
    result.readings_duplicates = bf_result.duplicates

    logger.info(
        "Seeded %s: %d generated, %d inserted, %d duplicates (%d devices)",
        sensor_type,
        result.readings_generated,
        result.readings_inserted,
        result.readings_duplicates,
        len(devices),
    )

    return result


def _get_devices_by_family(
    edge_config: Any,
) -> dict[str, list[dict[str, Any]]]:
    """Build a sensor_type → list of device dicts from edge config.

    Each device dict has: device_id, node_id, poll_interval_s.
    """
    by_family: dict[str, list[dict[str, Any]]] = {}

    for node_id, node_data in edge_config._nodes.items():
        for device in node_data["devices"]:
            sensor_type = device["sensor_type"]
            if sensor_type not in by_family:
                by_family[sensor_type] = []
            by_family[sensor_type].append({
                "device_id": device["device_id"],
                "node_id": node_id,
                "poll_interval_s": device["poll_interval_s"],
            })

    return by_family


def seed_all(
    *,
    hours: int = 24,
    start: datetime | None = None,
    inject_scenarios: bool = True,
    families: list[str] | None = None,
    dry_run: bool = False,
    engine: Any = None,
) -> SeedResult:
    """Seed all sensor families into TimescaleDB.

    This is the main entry point — call this from the CLI or from code.

    Parameters
    ----------
    hours : int
        Duration of generated data in hours (default 24).
    start : datetime, optional
        Start time. Default: yesterday midnight IST.
    inject_scenarios : bool
        Whether to inject MD/idle/leak scenarios.
    families : list[str], optional
        Subset of sensor families to seed (default: all 7).
    dry_run : bool
        If True, generate + count but don't write to DB.
    engine : optional
        SQLAlchemy engine override (for testing).

    Returns
    -------
    SeedResult
        Aggregate counts of generated, inserted, and duplicate readings.
    """
    t_start = time.monotonic()

    # Default start: yesterday midnight IST
    if start is None:
        now = datetime.now(IST)
        start = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=1)

    end = start + timedelta(hours=hours)

    logger.info(
        "Seed starting: %s → %s (%d hours, scenarios=%s, dry_run=%s)",
        start.isoformat(),
        end.isoformat(),
        hours,
        inject_scenarios,
        dry_run,
    )

    # Run migrations first (idempotent) — skip in dry run
    if not dry_run:
        try:
            from omniview.ingest.migrations import run_migrations

            run_migrations()
        except Exception as exc:
            logger.warning(
                "Migration check skipped (expected in test): %s", exc
            )

    # Load device manifest from edge_nodes.json
    try:
        edge_config = load_edge_config()
    except Exception as exc:
        logger.error("Failed to load edge config: %s", exc)
        raise

    site_id = edge_config.site_id
    devices_by_family = _get_devices_by_family(edge_config)

    # Filter families if specified
    target_families = families or sorted(devices_by_family.keys())
    target_families = [
        f for f in target_families if f in SENSOR_TYPES
    ]

    result = SeedResult(dry_run=dry_run)

    for sensor_type in target_families:
        devices = devices_by_family.get(sensor_type, [])
        if not devices:
            logger.warning(
                "No devices found for sensor_type %r, skipping",
                sensor_type,
            )
            continue

        family_result = seed_sensor_family(
            sensor_type=sensor_type,
            site_id=site_id,
            devices=devices,
            start=start,
            end=end,
            inject_scenarios=inject_scenarios,
            dry_run=dry_run,
            engine=engine,
        )

        result.families.append(family_result)
        result.total_generated += family_result.readings_generated
        result.total_inserted += family_result.readings_inserted
        result.total_duplicates += family_result.readings_duplicates

    result.elapsed_seconds = time.monotonic() - t_start

    logger.info("\n%s", result.summary())
    return result


# ── CLI ──────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omniview.ingest.seed",
        description=(
            "OI-55: Seed TimescaleDB with Day-1 hybrid datasets. "
            "Generates sensor readings from DevB bot generators and "
            "loads them via idempotent backfill_insert()."
        ),
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Duration of generated data in hours (default: 24)",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help=(
            "Start time in ISO-8601 format "
            "(default: yesterday midnight IST)"
        ),
    )
    parser.add_argument(
        "--no-scenarios",
        action="store_true",
        help="Skip MD near-miss / lazy-idle / leak injection",
    )
    parser.add_argument(
        "--families",
        nargs="+",
        choices=sorted(SENSOR_TYPES),
        default=None,
        help="Seed only specific sensor families (default: all 7)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and count readings without writing to DB",
    )
    return parser


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    parser = _build_parser()
    args = parser.parse_args()

    start = None
    if args.start:
        start = datetime.fromisoformat(args.start)
        if start.tzinfo is None:
            start = start.replace(tzinfo=IST)

    result = seed_all(
        hours=args.hours,
        start=start,
        inject_scenarios=not args.no_scenarios,
        families=args.families,
        dry_run=args.dry_run,
    )

    print(result.summary())


if __name__ == "__main__":
    main()
