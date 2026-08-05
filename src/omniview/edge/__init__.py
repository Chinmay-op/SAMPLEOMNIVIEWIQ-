"""
omniview.edge — Edge Connectivity Layer (Layer 2)
==================================================

Handles communication between the factory floor and the cloud:

* **mqtt_client** — MQTT publish/subscribe helpers  (OI-51)
* **injector**    — CSV → MQTT electrical replay     (OI-12)

Future modules (not yet scaffolded):
* Modbus RTU poller          (OI-13)
* NTP drift guard            (OI-52)
* Offline buffer & backfill  (OI-53)
"""
