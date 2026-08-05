"""
MQTT client helpers — OI-51
============================

Will provide:
- ``connect()``  — connect to Mosquitto with config from ``omniview.config``
- ``publish()``  — publish a JSON payload to a topic
- ``subscribe()`` — subscribe to a topic with a callback

Topic hierarchy (from PRD §5.2 / sprint planning OI-51)::

    omniview/{site_id}/{node_id}/{sensor_type}

Example::

    omniview/pune-isbm/compressor-01/electrical

Stubbed — implementation lands in OI-51.
"""
