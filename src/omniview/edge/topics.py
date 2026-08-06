"""
MQTT Topic Hierarchy — OI-51
==============================

Defines the canonical topic structure for OmniView IQ.

Topic pattern::

    omniview/{site_id}/{node_id}/{sensor_type}

Examples::

    omniview/pune-isbm/compressor-01/electrical
    omniview/pune-isbm/isbm-01/thermal
    omniview/pune-isbm/floor/ambient

System topics::

    omniview/{site_id}/_status/{node_id}     — device heartbeat / online status
    omniview/{site_id}/_alerts/{alert_type}   — rule engine alert outputs

All downstream consumers (ingest, rules, dashboard) import from here
rather than hard-coding topic strings.
"""

from __future__ import annotations

from typing import NamedTuple

# ── Valid sensor families (matches DevB's 7 schema families) ────────────────
SENSOR_TYPES: frozenset[str] = frozenset(
    {
        "electrical",  # Selec MFM384 — kVA, kW, PF, THD, per-phase I/V
        "vibration",  # Banner Q45VT — ISO 10816-3 RMS velocity, triaxial accel
        "thermal",  # Surface / barrel temp — RTD / Q45VT co-located probe
        "pressure",  # WIKA A-10 — 0-40 bar pneumatic line
        "gas",  # Schneider HeatTag — micro-particle / overheating
        "stroke",  # Pulse counter — production cycle / OEE
        "ambient",  # Schneider TH110 — shop floor temp + humidity
    }
)

# ── Topic separator ─────────────────────────────────────────────────────────
_SEP = "/"
_PREFIX = "omniview"

# ── System topic prefixes ───────────────────────────────────────────────────
_STATUS_SEGMENT = "_status"
_ALERTS_SEGMENT = "_alerts"


class ParsedTopic(NamedTuple):
    """Result of parsing an OmniView MQTT topic string."""

    site_id: str
    node_id: str
    sensor_type: str


# ── Builders ────────────────────────────────────────────────────────────────


def build_topic(site_id: str, node_id: str, sensor_type: str) -> str:
    """Construct a canonical MQTT topic string.

    Parameters
    ----------
    site_id : str
        Site identifier, e.g. ``"pune-isbm"``.
    node_id : str
        Node / device identifier, e.g. ``"compressor-01"``.
    sensor_type : str
        One of :data:`SENSOR_TYPES`.

    Returns
    -------
    str
        A topic string like ``"omniview/pune-isbm/compressor-01/electrical"``.

    Raises
    ------
    ValueError
        If *sensor_type* is not in :data:`SENSOR_TYPES`.
    """
    if sensor_type not in SENSOR_TYPES:
        raise ValueError(
            f"Unknown sensor_type {sensor_type!r}. "
            f"Must be one of: {sorted(SENSOR_TYPES)}"
        )
    return _SEP.join([_PREFIX, site_id, node_id, sensor_type])


def build_status_topic(site_id: str, node_id: str) -> str:
    """Construct a device heartbeat / status topic.

    Example::

        omniview/pune-isbm/_status/compressor-01
    """
    return _SEP.join([_PREFIX, site_id, _STATUS_SEGMENT, node_id])


def build_alert_topic(site_id: str, alert_type: str) -> str:
    """Construct a rule-engine alert topic.

    Example::

        omniview/pune-isbm/_alerts/md_breach
    """
    return _SEP.join([_PREFIX, site_id, _ALERTS_SEGMENT, alert_type])


def build_wildcard(site_id: str) -> str:
    """Construct a wildcard subscription for an entire site.

    Returns ``"omniview/{site_id}/#"`` — subscribes to every sensor,
    status, and alert topic under the site.
    """
    return _SEP.join([_PREFIX, site_id, "#"])


# ── Parser ──────────────────────────────────────────────────────────────────


def parse_topic(topic: str) -> ParsedTopic:
    """Extract site_id, node_id, and sensor_type from a topic string.

    Parameters
    ----------
    topic : str
        A topic like ``"omniview/pune-isbm/compressor-01/electrical"``.

    Returns
    -------
    ParsedTopic
        Named tuple with ``site_id``, ``node_id``, ``sensor_type``.

    Raises
    ------
    ValueError
        If the topic does not match the expected 4-segment pattern.
    """
    parts = topic.split(_SEP)
    if len(parts) != 4 or parts[0] != _PREFIX:
        raise ValueError(
            f"Cannot parse topic {topic!r}. "
            f"Expected pattern: {_PREFIX}/{{site_id}}/{{node_id}}/{{sensor_type}}"
        )
    return ParsedTopic(site_id=parts[1], node_id=parts[2], sensor_type=parts[3])
