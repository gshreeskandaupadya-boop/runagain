import jsonschema

FAILURE_CLASSES = ["dead_pin", "missing_system_library", "python_mismatch",
                   "deprecated_api", "missing_entry_point", "other"]
STRATEGIES = ["pin_version", "apt_install", "python_version", "compat_patch", "give_up"]

DECISION_SCHEMA = {
    "type": "object",
    "required": ["failure_class", "root_cause", "confidence", "strategy", "change", "verification_command"],
    "additionalProperties": False,
    "properties": {
        "failure_class": {"enum": FAILURE_CLASSES},
        "root_cause": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "strategy": {"enum": STRATEGIES},
        "change": {
            "type": "object",
            "properties": {
                "pip_pins": {"type": "object", "additionalProperties": {"type": "string"}},
                "apt_packages": {"type": "array", "items": {"type": "string"}},
                "python_version": {"type": "string"},
                "patch": {"type": "string", "maxLength": 2000},  # unified diff; size-limited
            },
            "additionalProperties": False,
        },
        "verification_command": {"type": "string"},
        "sources_used": {"type": "array", "items": {"type": "string"}},
    },
}

def validate(decision: dict) -> None:
    jsonschema.validate(decision, DECISION_SCHEMA)
