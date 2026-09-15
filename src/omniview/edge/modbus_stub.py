"""
Modbus Source Stub — OI-13
============================

Stub interface for live Modbus RTU reads.  Day-1 the poller uses
``BotSource`` (synthetic bots).  When hardware arrives, replace the
``read()`` body with ``pymodbus`` calls — everything else stays the
same.

The stub reads ``register_map`` from ``edge_nodes.json`` and
documents exactly what needs to change for live cutover.

Usage::

    from omniview.edge.modbus_stub import ModbusSource

    source = ModbusSource(
        slave_address=10,
        register_map={"rms_velocity_mm_s": {"address": 40001, ...}},
        device_id="pune-comp-vib01",
    )
    # Day-1: raises NotImplementedError
    # Live: returns dict of register_name → value
    data = source.read()
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ModbusSource:
    """Stub for live Modbus RTU sensor reads.

    Parameters
    ----------
    slave_address : int
        Modbus slave address from ``edge_nodes.json``.
    register_map : dict
        Register name → {address, count, type, unit} from config.
    device_id : str
        Device identifier for logging.
    serial_port : str
        Serial port path (e.g. ``/dev/ttyRS485-0``).
    baud_rate : int
        Serial baud rate (default 9600).

    Notes
    -----
    **Live cutover checklist:**

    1. ``pip install pymodbus`` (add to requirements.txt)
    2. Replace ``read()`` body with::

           from pymodbus.client import ModbusSerialClient
           client = ModbusSerialClient(
               port=self.serial_port,
               baudrate=self.baud_rate,
               parity='N', stopbits=1, bytesize=8,
           )
           client.connect()
           result = client.read_holding_registers(
               address=reg["address"],
               count=reg["count"],
               slave=self.slave_address,
           )
           # decode float32 / uint16 / uint32 from result.registers

    3. Handle connection errors, timeouts, CRC failures
    4. Remove ``synthetic: true`` flag from payloads
    """

    def __init__(
        self,
        slave_address: int,
        register_map: dict[str, Any],
        device_id: str = "unknown",
        serial_port: str = "/dev/ttyRS485-0",
        baud_rate: int = 9600,
    ) -> None:
        self.slave_address = slave_address
        self.register_map = register_map
        self.device_id = device_id
        self.serial_port = serial_port
        self.baud_rate = baud_rate

    def read(self) -> dict[str, Any]:
        """Read sensor data from Modbus registers.

        Returns
        -------
        dict
            Register name → decoded value.

        Raises
        ------
        NotImplementedError
            Always — until hardware cutover.
        """
        raise NotImplementedError(
            f"Modbus read not implemented for device {self.device_id!r} "
            f"(slave={self.slave_address}). Use --mode bot for Day-1 "
            f"synthetic data. See docstring for live cutover checklist."
        )

    def __repr__(self) -> str:
        return (
            f"ModbusSource(device={self.device_id!r}, "
            f"slave={self.slave_address}, "
            f"registers={list(self.register_map.keys())})"
        )
