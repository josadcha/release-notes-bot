from __future__ import annotations
from typing import Any, Dict
from jsonschema import validate, Draft7Validator, ValidationError

RELEASE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["tldr", "repos", "upgrade_notes", "contributors"],
    "properties": {
        "tldr": {
            "type": "array",
            "items": {"type": "string"}
        },
        "repos": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "sections"],
                "properties": {
                    "name": {"type": "string"},
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["title", "items"],
                            "properties": {
                                "title": {"type": "string"},
                                "items": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["text", "prs"],
                                        "properties": {
                                            "text": {"type": "string"},
                                            "prs": {
                                                "type": "array",
                                                "items": {"type": "integer"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "upgrade_notes": {
            "type": "array",
            "items": {"type": "string"}
        },
        "contributors": {
            "type": "array",
            "items": {"type": "string"}
        }
    }
}


def is_valid_release(obj: Dict[str, Any]) -> bool:
    v = Draft7Validator(RELEASE_SCHEMA)
    return v.is_valid(obj)


def assert_valid_release(obj: Dict[str, Any]) -> None:
    validate(obj, RELEASE_SCHEMA)
