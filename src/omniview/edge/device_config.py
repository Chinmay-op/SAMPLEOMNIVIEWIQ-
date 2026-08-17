"""
Edge Device Configuration Loader
==================================

Loads ``config/edge_nodes.json``, validates it against the JSON Schema,
and provides typed lookup functions used by edge pollers (OI-13) and
replay bots (OI-12).

This module is the **runtime bridge** between the static config file and
the rest of the edge layer.  ``node_registry.py`` (OI-51) defined the
node map as a Python dict; this module adds:

* Formal ``device_id`` → node resolution
* Per-device Modbus addressing and register maps
* JSON Schema validation at load time
* Site-level metadata (contracted demand, timezone, utility)

Usage::

    from omniview.edge.device_config import load_edge_config, EdgeConfig

    cfg = load_edge_config()                         # loads default config
    cfg.get_device("pune-comp-mfm384")               # device dict
    cfg.get_devices_for_node("compressor-01")         # all devices on node
    cfg.get_poll_interval("pune-comp-mfm384")         # 15
    cfg.get_all_device_ids()                          # sorted list
    cfg.site_id                                       # "pune-isbm"
    cfg.contracted_demand_kva                         # 500
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import jsonschema

logger = logging.getLogger(__name__)

# ── Default paths ───────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "edge_nodes.json"
DEFAULT_SCHEMA_PATH = _REPO_ROOT / "schemas" / "edge_config_schema.json"


class EdgeConfigError(Exception):
    """Raised when edge config loading or validation fails."""


class EdgeConfig:
    """Loaded and validated edge device configuration.

    Parameters
    ----------
    raw : dict
        The parsed JSON config (already validated against schema).
    """

    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw

        # ── Site-level properties ───────────────────────────────────────
        site = raw["site"]
        self.site_id: str = site["site_id"]
        self.site_name: str = site["name"]
        self.contracted_demand_kva: float = site["contracted_demand_kva"]
        self.timezone: str = site.get("timezone", "UTC")
        self.utility: str = site.get("utility", "")
        self.tariff_category: str = site.get("tariff_category", "")

        # ── Config version ──────────────────────────────────────────────
        self.config_version: str = raw["config_version"]

        # ── Gateway ─────────────────────────────────────────────────────
        self.gateway: dict[str, Any] = raw.get("gateway", {})

        # ── Build lookup indexes ────────────────────────────────────────
        self._nodes: dict[str, dict[str, Any]] = raw["nodes"]
        self._device_index: dict[str, dict[str, Any]] = {}
        self._device_to_node: dict[str, str] = {}

        for node_id, node in self._nodes.items():
            for device in node["devices"]:
                did = device["device_id"]
                if did in self._device_index:
                    raise EdgeConfigError(
                        f"Duplicate device_id {did!r} found in config. "
                        f"device_id must be globally unique."
                    )
                self._device_index[did] = device
                self._device_to_node[did] = node_id

        logger.info(
            "EdgeConfig loaded: site=%s, version=%s, nodes=%d, devices=%d",
            self.site_id,
            self.config_version,
            len(self._nodes),
            len(self._device_index),
        )

    # ── Node lookups ────────────────────────────────────────────────────

    def get_node_ids(self) -> list[str]:
        """Return sorted list of all node IDs."""
        return sorted(self._nodes.keys())

    def get_node(self, node_id: str) -> dict[str, Any]:
        """Return full node definition by node_id.

        Raises
        ------
        KeyError
            If *node_id* is not in the config.
        """
        if node_id not in self._nodes:
            raise KeyError(
                f"Unknown node_id {node_id!r}. "
                f"Known nodes: {self.get_node_ids()}"
            )
        return self._nodes[node_id]

    # ── Device lookups ──────────────────────────────────────────────────

    def get_all_device_ids(self) -> list[str]:
        """Return sorted list of all device_ids across all nodes."""
        return sorted(self._device_index.keys())

    def get_device(self, device_id: str) -> dict[str, Any]:
        """Return device definition by device_id.

        Raises
        ------
        KeyError
            If *device_id* is not in the config.
        """
        if device_id not in self._device_index:
            raise KeyError(
                f"Unknown device_id {device_id!r}. "
                f"Known devices: {self.get_all_device_ids()}"
            )
        return self._device_index[device_id]

    def get_node_for_device(self, device_id: str) -> str:
        """Return the node_id that a device belongs to.

        Raises
        ------
        KeyError
            If *device_id* is not in the config.
        """
        if device_id not in self._device_to_node:
            raise KeyError(
                f"Unknown device_id {device_id!r}. "
                f"Known devices: {self.get_all_device_ids()}"
            )
        return self._device_to_node[device_id]

    def get_devices_for_node(self, node_id: str) -> list[dict[str, Any]]:
        """Return all device definitions attached to a node.

        Raises
        ------
        KeyError
            If *node_id* is not in the config.
        """
        node = self.get_node(node_id)
        return node["devices"]

    def get_poll_interval(self, device_id: str) -> int:
        """Return poll interval (seconds) for a specific device.

        Raises
        ------
        KeyError
            If *device_id* is not in the config.
        """
        device = self.get_device(device_id)
        return device["poll_interval_s"]

    def get_sensor_type(self, device_id: str) -> str:
        """Return the sensor_type for a specific device.

        Raises
        ------
        KeyError
            If *device_id* is not in the config.
        """
        device = self.get_device(device_id)
        return device["sensor_type"]

    def get_devices_by_sensor_type(self, sensor_type: str) -> list[dict[str, Any]]:
        """Return all devices of a given sensor_type across all nodes."""
        return [
            d for d in self._device_index.values()
            if d["sensor_type"] == sensor_type
        ]

    def get_register_map(self, device_id: str) -> dict[str, Any]:
        """Return the Modbus register map for a device.

        Returns empty dict if no register_map is defined.

        Raises
        ------
        KeyError
            If *device_id* is not in the config.
        """
        device = self.get_device(device_id)
        return device.get("register_map", {})

    # ── Convenience ─────────────────────────────────────────────────────

    @property
    def node_count(self) -> int:
        """Total number of nodes."""
        return len(self._nodes)

    @property
    def device_count(self) -> int:
        """Total number of devices across all nodes."""
        return len(self._device_index)

    def __repr__(self) -> str:
        return (
            f"EdgeConfig(site={self.site_id!r}, version={self.config_version!r}, "
            f"nodes={self.node_count}, devices={self.device_count})"
        )


# ── Module-level loader ────────────────────────────────────────────────────


def load_edge_config(
    config_path: str | Path | None = None,
    schema_path: str | Path | None = None,
    validate: bool = True,
) -> EdgeConfig:
    """Load and optionally validate the edge device configuration.

    Parameters
    ----------
    config_path : str or Path, optional
        Path to the edge config JSON file.
        Defaults to ``config/edge_nodes.json`` at the repo root.
    schema_path : str or Path, optional
        Path to the JSON Schema file for validation.
        Defaults to ``schemas/edge_config_schema.json`` at the repo root.
    validate : bool, default True
        Whether to validate the config against the JSON Schema.

    Returns
    -------
    EdgeConfig
        The loaded, validated, and indexed configuration.

    Raises
    ------
    EdgeConfigError
        If the config file is missing, malformed, or fails validation.
    """
    config_path = Path(config_path or DEFAULT_CONFIG_PATH)
    schema_path = Path(schema_path or DEFAULT_SCHEMA_PATH)

    # ── Load config ─────────────────────────────────────────────────────
    if not config_path.exists():
        raise EdgeConfigError(
            f"Edge config not found at {config_path}. "
            f"Expected config/edge_nodes.json in the repo root."
        )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise EdgeConfigError(
            f"Edge config at {config_path} is not valid JSON: {exc}"
        ) from exc

    # ── Validate against schema ─────────────────────────────────────────
    if validate:
        if not schema_path.exists():
            logger.warning(
                "Schema file not found at %s — skipping validation", schema_path
            )
        else:
            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema = json.load(f)
                jsonschema.validate(instance=raw, schema=schema)
                logger.debug("Edge config validated against %s", schema_path)
            except jsonschema.ValidationError as exc:
                raise EdgeConfigError(
                    f"Edge config validation failed: {exc.message}\n"
                    f"Path: {list(exc.absolute_path)}"
                ) from exc

    return EdgeConfig(raw)


def get_default_config() -> EdgeConfig:
    """Load the default edge config (convenience wrapper).

    This is the function most callers should use::

        from omniview.edge.device_config import get_default_config
        cfg = get_default_config()
    """
    return load_edge_config()
