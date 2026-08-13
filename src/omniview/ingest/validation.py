"""
Payload Validation — OI-14
==========================

Validates incoming MQTT payloads against JSON schemas.
If a payload is invalid, it is logged and skipped to prevent Database contamination.
"""

import logging
from typing import Any
import jsonschema
from jsonschema.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Placeholder schema for electrical sensor. 
# DevB will provide final schemas for all sensors in OI-23, OI-5, etc.
_PLACEHOLDER_ELECTRICAL_SCHEMA = {
    "type": "object",
    "properties": {
        "kva": {"type": "number"},
        "kw": {"type": "number"},
        "pf": {"type": "number"},
        "v_ry": {"type": "number"},
        "i_r": {"type": "number"},
        "thd_v": {"type": "number"},
    },
    "required": ["kva", "kw", "pf"]
}

# Mapping of sensor_type to schema.
_SCHEMAS = {
    "electrical": _PLACEHOLDER_ELECTRICAL_SCHEMA
}

def validate_payload(sensor_type: str, schema_version: str, payload: dict[str, Any]) -> bool:
    """Validate a sensor payload against its corresponding JSON schema.

    Parameters
    ----------
    sensor_type : str
        The type of sensor (e.g. "electrical").
    schema_version : str
        The version of the schema.
    payload : dict
        The data dictionary to validate.

    Returns
    -------
    bool
        True if the payload is valid or if no schema is currently defined.
        False if the payload is invalid.
    """
    schema = _SCHEMAS.get(sensor_type)
    
    if not schema:
        # If no schema is defined yet (waiting on DevB), we allow the payload 
        # through so we don't block development on other sensors.
        logger.debug("No schema defined for sensor_type %r, allowing payload.", sensor_type)
        return True
        
    try:
        jsonschema.validate(instance=payload, schema=schema)
        return True
    except ValidationError as e:
        logger.warning(
            "Payload validation failed for sensor_type %r (v%s): %s",
            sensor_type, schema_version, e.message
        )
        return False
