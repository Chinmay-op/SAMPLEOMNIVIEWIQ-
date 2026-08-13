import pytest
from omniview.ingest.validation import validate_payload

def test_validate_payload_valid_electrical():
    payload = {
        "kva": 100.5,
        "kw": 95.0,
        "pf": 0.95,
        "v_ry": 415.0,
        "i_r": 120.0,
        "thd_v": 2.5
    }
    assert validate_payload("electrical", "1.0", payload) is True

def test_validate_payload_missing_required():
    payload = {
        "kva": 100.5,
        "kw": 95.0,
        # missing "pf"
    }
    assert validate_payload("electrical", "1.0", payload) is False

def test_validate_payload_wrong_type():
    payload = {
        "kva": "100.5",  # string instead of number
        "kw": 95.0,
        "pf": 0.95
    }
    assert validate_payload("electrical", "1.0", payload) is False

def test_validate_payload_unknown_sensor_type():
    # Since we have no schema for "vibration" yet, it should return True (allowed through)
    payload = {"rms_velocity": 5.5}
    assert validate_payload("vibration", "1.0", payload) is True
