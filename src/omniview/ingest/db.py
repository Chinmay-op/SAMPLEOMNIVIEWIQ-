"""
TimescaleDB connection helpers — OI-54
=======================================

Will provide:
- ``get_engine()``        — SQLAlchemy engine from ``omniview.config.TSDB_DSN``
- ``create_hypertables()`` — idempotent DDL for the telemetry hypertables
- ``insert_reading()``    — insert a single sensor reading (with backfill support)

Hypertable design notes (from PRD §5.4):
- One wide table per sensor family (electrical, vibration, thermal, pressure)
- Partitioned by ``timestamp`` (TimescaleDB auto-chunking)
- ``device_id`` + ``timestamp`` composite key for idempotent upserts

Stubbed — implementation lands in OI-54.
"""
