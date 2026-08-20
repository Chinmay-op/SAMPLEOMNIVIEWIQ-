"""
omniview.edge — Edge Connectivity Layer (Layer 2)
==================================================

Handles communication between the factory floor and the cloud:

* **mqtt_client**    — MQTT publish/subscribe client              (OI-51)
* **topics**         — Topic hierarchy contract + helpers          (OI-51)
* **node_registry**  — Device/node map for the Pune POC           (OI-51)
* **device_config**  — Edge config loader (device_id → node map)  (OI-52)
* **injector**       — CSV → MQTT electrical replay               (OI-12)
* **offline_buffer** — SQLite offline cache for network outages   (OI-28)
* **buffer_replay**  — Chronological replay engine                (OI-29)
* **ntp_guard**      — NTP drift monitor + alert guard            (OI-53)
* **parsers**        — 7 sensor data parsers (DevB)               (OI-23)
* **bots**           — 7 live edge simulators (DevB)              (OI-23)
"""

from omniview.edge.buffer_replay import BufferReplayEngine, ReplayResult
from omniview.edge.device_config import EdgeConfig, load_edge_config
from omniview.edge.injector import ElectricalInjector
from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.node_registry import NODES, get_all_topics, get_node
from omniview.edge.ntp_guard import DriftStatus, NTPDriftGuard, check_drift
from omniview.edge.offline_buffer import OfflineBuffer
from omniview.edge.topics import SENSOR_TYPES, build_topic, parse_topic
from omniview.edge import parsers  # noqa: F401 — DevB sensor parsers
from omniview.edge import bots  # noqa: F401 — DevB live edge simulators

__all__ = [
    "BufferReplayEngine",
    "DriftStatus",
    "EdgeConfig",
    "ElectricalInjector",
    "NTPDriftGuard",
    "OfflineBuffer",
    "OmniViewMQTTClient",
    "NODES",
    "ReplayResult",
    "SENSOR_TYPES",
    "bots",
    "build_topic",
    "check_drift",
    "get_all_topics",
    "get_node",
    "load_edge_config",
    "parse_topic",
    "parsers",
]
