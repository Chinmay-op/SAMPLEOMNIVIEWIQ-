"""
OmniView IQ — Pune ISBM-PET Facility POC
==========================================

Edge-to-cloud IIoT monitoring for demand-penalty avoidance,
compressor leak detection, and lazy-idle thermal degradation alerts.

Package layout:
    omniview.edge       — MQTT client, Modbus poller, CSV injector (OI-51/52/12)
    omniview.ingest     — TimescaleDB writers, schema validation   (OI-54/55)
    omniview.rules      — Rule engine, PdM, arbitration            (OI-56–67)
    omniview.dashboard  — Streamlit live dashboard, action cards    (OI-68/69)
    omniview.config     — Centralised .env config loader
"""

__version__ = "0.1.0"
