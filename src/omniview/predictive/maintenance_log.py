"""
omniview.predictive.maintenance_log — Maintenance Event Logger (Stage 0)
=========================================================================

Logs maintenance events for future Stage B supervised learning.
Stage B needs ~10-20 real logged maintenance events before it can
train a classifier. This module captures them from day one.

Storage: JSONL file (one JSON object per line) at
``data/maintenance_events.jsonl``. Upgradeable to a TSDB table
or CMMS integration later.

Required fields per the Build Spec §2:
    - machine_id
    - event_date
    - event_type (repair | replace | inspection_only)
    - triggered_by (system_alert | manual_observation)

Optional fields:
    - notes, component, cost_inr, downtime_hours
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_LOG_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "maintenance_events.jsonl"
)

# Valid values for constrained fields
VALID_EVENT_TYPES = {"repair", "replace", "inspection_only"}
VALID_TRIGGERED_BY = {"system_alert", "manual_observation"}


@dataclass
class MaintenanceEvent:
    """A single maintenance event record.

    Parameters
    ----------
    machine_id : str
        Which machine was serviced.
    event_date : str
        ISO date (YYYY-MM-DD) of the event.
    event_type : str
        One of: ``repair``, ``replace``, ``inspection_only``.
    triggered_by : str
        One of: ``system_alert``, ``manual_observation``.
    notes : str
        Free-text notes about the event.
    component : str
        Affected component (bearing, motor, winding, compressor, etc.).
    cost_inr : float or None
        Cost in INR if known.
    downtime_hours : float or None
        Duration of downtime if known.
    """

    machine_id: str
    event_date: str
    event_type: str
    triggered_by: str
    notes: str = ""
    component: str = ""
    cost_inr: float | None = None
    downtime_hours: float | None = None

    def validate(self) -> list[str]:
        """Validate the event. Returns a list of error messages (empty = valid)."""
        errors: list[str] = []

        if not self.machine_id:
            errors.append("machine_id is required")
        if not self.event_date:
            errors.append("event_date is required")
        else:
            try:
                date.fromisoformat(self.event_date)
            except ValueError:
                errors.append(f"event_date '{self.event_date}' is not valid ISO format")

        if self.event_type not in VALID_EVENT_TYPES:
            errors.append(
                f"event_type '{self.event_type}' must be one of: "
                f"{', '.join(sorted(VALID_EVENT_TYPES))}"
            )

        if self.triggered_by not in VALID_TRIGGERED_BY:
            errors.append(
                f"triggered_by '{self.triggered_by}' must be one of: "
                f"{', '.join(sorted(VALID_TRIGGERED_BY))}"
            )

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict, omitting None values."""
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


class MaintenanceLogger:
    """Append-only logger for maintenance events.

    Writes to a JSONL file. Thread-safe (append mode).

    Parameters
    ----------
    log_path : str or Path, optional
        Path to the JSONL file. Defaults to
        ``data/maintenance_events.jsonl``.
    """

    def __init__(self, log_path: str | Path | None = None):
        self._path = Path(log_path) if log_path else _DEFAULT_LOG_PATH

    def log(self, event: MaintenanceEvent) -> bool:
        """Validate and append a maintenance event to the log.

        Parameters
        ----------
        event : MaintenanceEvent
            The event to log.

        Returns
        -------
        bool
            True if logged successfully, False if validation failed.
        """
        errors = event.validate()
        if errors:
            logger.error(
                "Maintenance event validation failed: %s",
                "; ".join(errors),
            )
            return False

        # Ensure the directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)

        record = event.to_dict()
        record["logged_at"] = datetime.now(timezone.utc).isoformat()

        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

        logger.info(
            "Logged maintenance event: %s on %s (%s)",
            event.machine_id,
            event.event_date,
            event.event_type,
        )
        return True

    def read_all(self) -> list[MaintenanceEvent]:
        """Read all logged maintenance events.

        Returns
        -------
        list[MaintenanceEvent]
            All events in chronological order.
        """
        if not self._path.exists():
            return []

        events: list[MaintenanceEvent] = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    events.append(
                        MaintenanceEvent(
                            machine_id=data["machine_id"],
                            event_date=data["event_date"],
                            event_type=data["event_type"],
                            triggered_by=data["triggered_by"],
                            notes=data.get("notes", ""),
                            component=data.get("component", ""),
                            cost_inr=data.get("cost_inr"),
                            downtime_hours=data.get("downtime_hours"),
                        )
                    )
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Skipping malformed log entry: %s", e)

        return events

    def count(self) -> int:
        """Return the number of logged events."""
        return len(self.read_all())

    def stage_b_ready(self, min_events: int = 10) -> bool:
        """Check if enough events exist to trigger Stage B.

        Parameters
        ----------
        min_events : int
            Minimum events needed. Default 10 (per Build Spec §2).

        Returns
        -------
        bool
            True if the trigger condition for Stage B is met.
        """
        n = self.count()
        ready = n >= min_events
        if ready:
            logger.info(
                "Stage B trigger: %d events logged (≥ %d threshold)",
                n,
                min_events,
            )
        return ready
