"""
omniview.ingest — Cloud Ingestion & Storage Layer (Layer 3, part 1)
====================================================================

Handles MQTT → TimescaleDB writes:

* **db** — Connection pool, hypertable creation, migrations  (OI-54)

Future modules:
* Payload schema validation + version check  (OI-55)
* Idempotent insert logic                    (OI-55)
* Day-1 seed script                          (OI-55)
"""
