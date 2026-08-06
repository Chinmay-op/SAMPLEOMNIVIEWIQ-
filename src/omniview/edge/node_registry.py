"""
Device / Node Registry — OI-51
================================

Maps physical equipment nodes to their sensor families and MQTT topics.

The Pune ISBM-PET POC instruments two primary nodes and one ambient point
(PRD §1.4).  This registry is the single source of truth for:

* Which nodes exist at a site
* What sensors are attached to each node
* Generating the full set of MQTT topics for a site

Usage::

    from omniview.edge.node_registry import NODES, get_all_topics

    for topic in get_all_topics("pune-isbm"):
        client.subscribe(topic)
"""

from __future__ import annotations

from typing import Any

from omniview.edge.topics import build_topic

# ── Pune ISBM-PET POC Node Map (PRD §1.4) ──────────────────────────────────

NODES: dict[str, dict[str, Any]] = {
    "compressor-01": {
        "display_name": "High-Pressure Compressor (25–40 bar)",
        "location": "Compressor room — bearing housing + output receiver manifold",
        "sensors": ["electrical", "vibration", "pressure", "thermal", "gas"],
        "poll_intervals": {
            "electrical": 15,  # seconds — FR1: ≤15s for demand forecast density
            "vibration": 60,  # seconds — slower-moving mechanical parameter
            "pressure": 60,  # seconds — leak decay is a slow trend
            "thermal": 60,  # seconds — surface temperature
            "gas": 60,  # seconds — micro-particle / overheating
        },
    },
    "isbm-01": {
        "display_name": "ISBM Machine (Nissei ASB-70DPH)",
        "location": "Production floor — main electrical panel + barrel zone",
        "sensors": ["electrical", "thermal", "stroke"],
        "poll_intervals": {
            "electrical": 15,
            "thermal": 60,
            "stroke": 15,  # cycle counting at electrical cadence
        },
    },
    "floor": {
        "display_name": "Factory Floor Ambient",
        "location": "Shop floor / control room — wall/pillar mount",
        "sensors": ["ambient"],
        "poll_intervals": {
            "ambient": 60,
        },
    },
}


def get_node(node_id: str) -> dict[str, Any]:
    """Return metadata for a single node.

    Parameters
    ----------
    node_id : str
        Node identifier, e.g. ``"compressor-01"``.

    Returns
    -------
    dict
        Node metadata including ``display_name``, ``location``, ``sensors``,
        and ``poll_intervals``.

    Raises
    ------
    KeyError
        If *node_id* is not in the registry.
    """
    if node_id not in NODES:
        raise KeyError(
            f"Unknown node_id {node_id!r}. "
            f"Known nodes: {sorted(NODES.keys())}"
        )
    return NODES[node_id]


def get_topics_for_node(site_id: str, node_id: str) -> list[str]:
    """Return all MQTT topics for a specific node at a site.

    Parameters
    ----------
    site_id : str
        Site identifier, e.g. ``"pune-isbm"``.
    node_id : str
        Node identifier, e.g. ``"compressor-01"``.

    Returns
    -------
    list[str]
        List of topic strings, e.g.
        ``["omniview/pune-isbm/compressor-01/electrical", ...]``.
    """
    node = get_node(node_id)
    return [build_topic(site_id, node_id, s) for s in node["sensors"]]


def get_all_topics(site_id: str) -> list[str]:
    """Return every MQTT topic for all nodes at a site.

    Parameters
    ----------
    site_id : str
        Site identifier, e.g. ``"pune-isbm"``.

    Returns
    -------
    list[str]
        All topic strings across every registered node (9 topics for Pune POC).
    """
    topics: list[str] = []
    for node_id in NODES:
        topics.extend(get_topics_for_node(site_id, node_id))
    return topics


def get_all_node_ids() -> list[str]:
    """Return all registered node IDs.

    Returns
    -------
    list[str]
        Sorted list of node identifiers.
    """
    return sorted(NODES.keys())
