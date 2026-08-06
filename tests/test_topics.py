"""
Unit tests for omniview.edge.topics — OI-51

No broker required — these test the topic hierarchy contract purely in-memory.
"""

import pytest

from omniview.edge.topics import (
    SENSOR_TYPES,
    ParsedTopic,
    build_alert_topic,
    build_status_topic,
    build_topic,
    build_wildcard,
    parse_topic,
)
from omniview.edge.node_registry import NODES, get_all_topics, get_topics_for_node


# ── SENSOR_TYPES ────────────────────────────────────────────────────────────


class TestSensorTypes:
    """Validate the canonical sensor type set."""

    def test_contains_all_seven_families(self):
        expected = {
            "electrical",
            "vibration",
            "thermal",
            "pressure",
            "gas",
            "stroke",
            "ambient",
        }
        assert SENSOR_TYPES == expected

    def test_is_frozenset(self):
        assert isinstance(SENSOR_TYPES, frozenset)


# ── build_topic ─────────────────────────────────────────────────────────────


class TestBuildTopic:
    """Validate topic string construction."""

    def test_basic_construction(self):
        topic = build_topic("pune-isbm", "compressor-01", "electrical")
        assert topic == "omniview/pune-isbm/compressor-01/electrical"

    def test_all_sensor_types_accepted(self):
        for sensor_type in SENSOR_TYPES:
            topic = build_topic("site-x", "node-y", sensor_type)
            assert topic == f"omniview/site-x/node-y/{sensor_type}"

    def test_invalid_sensor_type_raises(self):
        with pytest.raises(ValueError, match="Unknown sensor_type"):
            build_topic("pune-isbm", "compressor-01", "invalid_sensor")

    def test_rejects_empty_sensor_type(self):
        with pytest.raises(ValueError):
            build_topic("pune-isbm", "compressor-01", "")


# ── parse_topic ─────────────────────────────────────────────────────────────


class TestParseTopic:
    """Validate topic string parsing."""

    def test_round_trip(self):
        """Build a topic, parse it, verify fields match."""
        original = build_topic("pune-isbm", "compressor-01", "vibration")
        parsed = parse_topic(original)
        assert parsed == ParsedTopic("pune-isbm", "compressor-01", "vibration")

    def test_named_tuple_fields(self):
        parsed = parse_topic("omniview/site-a/node-b/thermal")
        assert parsed.site_id == "site-a"
        assert parsed.node_id == "node-b"
        assert parsed.sensor_type == "thermal"

    def test_rejects_wrong_prefix(self):
        with pytest.raises(ValueError, match="Cannot parse topic"):
            parse_topic("wrongprefix/site/node/sensor")

    def test_rejects_too_few_segments(self):
        with pytest.raises(ValueError):
            parse_topic("omniview/site/node")

    def test_rejects_too_many_segments(self):
        with pytest.raises(ValueError):
            parse_topic("omniview/site/node/sensor/extra")


# ── System topics ───────────────────────────────────────────────────────────


class TestSystemTopics:
    """Validate status, alert, and wildcard topic builders."""

    def test_status_topic(self):
        topic = build_status_topic("pune-isbm", "compressor-01")
        assert topic == "omniview/pune-isbm/_status/compressor-01"

    def test_alert_topic(self):
        topic = build_alert_topic("pune-isbm", "md_breach")
        assert topic == "omniview/pune-isbm/_alerts/md_breach"

    def test_wildcard(self):
        topic = build_wildcard("pune-isbm")
        assert topic == "omniview/pune-isbm/#"


# ── Pune POC topics (integration with node_registry) ───────────────────────


class TestPuneTopics:
    """Validate that the node registry produces the expected 9 topics."""

    EXPECTED_TOPICS = [
        "omniview/pune-isbm/compressor-01/electrical",
        "omniview/pune-isbm/compressor-01/vibration",
        "omniview/pune-isbm/compressor-01/pressure",
        "omniview/pune-isbm/compressor-01/thermal",
        "omniview/pune-isbm/compressor-01/gas",
        "omniview/pune-isbm/isbm-01/electrical",
        "omniview/pune-isbm/isbm-01/thermal",
        "omniview/pune-isbm/isbm-01/stroke",
        "omniview/pune-isbm/floor/ambient",
    ]

    def test_pune_topic_count(self):
        topics = get_all_topics("pune-isbm")
        assert len(topics) == 9

    def test_pune_topics_complete(self):
        topics = get_all_topics("pune-isbm")
        assert set(topics) == set(self.EXPECTED_TOPICS)

    def test_compressor_topics(self):
        topics = get_topics_for_node("pune-isbm", "compressor-01")
        assert len(topics) == 5
        assert "omniview/pune-isbm/compressor-01/electrical" in topics

    def test_isbm_topics(self):
        topics = get_topics_for_node("pune-isbm", "isbm-01")
        assert len(topics) == 3

    def test_floor_topics(self):
        topics = get_topics_for_node("pune-isbm", "floor")
        assert topics == ["omniview/pune-isbm/floor/ambient"]

    def test_unknown_node_raises(self):
        with pytest.raises(KeyError, match="Unknown node_id"):
            get_topics_for_node("pune-isbm", "nonexistent-node")
