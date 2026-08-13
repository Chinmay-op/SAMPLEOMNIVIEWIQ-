"""
omniview.edge — Edge Connectivity Layer (Layer 2)
==================================================

Handles communication between the factory floor and the cloud:

* **mqtt_client**   — MQTT publish/subscribe client              (OI-51)
* **topics**        — Topic hierarchy contract + helpers          (OI-51)
* **node_registry** — Device/node map for the Pune POC           (OI-51)
* **injector**      — CSV → MQTT electrical replay               (OI-12)
* **offline_buffer** — SQLite offline cache for network outages  (OI-28)
* **parsers**       — 7 sensor data parsers (DevB)               (OI-23)
* **bots**          — 7 live edge simulators (DevB)              (OI-23)
"""

from omniview.edge.injector import ElectricalInjector
from omniview.edge.mqtt_client import OmniViewMQTTClient
from omniview.edge.node_registry import NODES, get_all_topics, get_node
from omniview.edge.offline_buffer import OfflineBuffer
from omniview.edge.topics import SENSOR_TYPES, build_topic, parse_topic
from omniview.edge import parsers  # noqa: F401 — DevB sensor parsers
from omniview.edge import bots  # noqa: F401 — DevB live edge simulators

__all__ = [
    "ElectricalInjector",
    "OfflineBuffer",
    "OmniViewMQTTClient",
    "NODES",
    "SENSOR_TYPES",
    "bots",
    "build_topic",
    "get_all_topics",
    "get_node",
    "parse_topic",
    "parsers",
]
