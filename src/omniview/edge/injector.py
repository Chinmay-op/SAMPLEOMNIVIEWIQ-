"""
CSV → MQTT Electrical Replay Injector — OI-12
===============================================

Reads an electrical-parameter CSV (from DevB's replay bot, OI-8) and publishes
rows as timestamped JSON payloads to the MQTT broker at the configured poll
interval (default 15 s).

This is the Day-1 mechanism for seeding the pipeline without live hardware.

Stubbed — implementation lands in OI-12.
"""
