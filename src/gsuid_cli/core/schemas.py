from __future__ import annotations

from gsuid_cli.core.envelope import SCHEMA


def command_envelope_schema(command: str) -> dict[str, object]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"{command} success envelope",
        "type": "object",
        "required": [
            "ok",
            "schema",
            "command",
            "request_id",
            "generated_at",
            "duration_ms",
            "warnings",
            "data",
            "artifacts",
            "source",
            "pagination",
        ],
        "properties": {
            "ok": {"const": True},
            "schema": {"const": SCHEMA},
            "command": {"const": command},
            "request_id": {"type": "string"},
            "generated_at": {"type": "string", "format": "date-time"},
            "duration_ms": {"type": "integer", "minimum": 0},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "data": {"type": "object", "additionalProperties": True},
            "artifacts": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "source": {"type": "object", "additionalProperties": True},
            "pagination": {
                "anyOf": [
                    {"type": "object", "additionalProperties": True},
                    {"type": "null"},
                ]
            },
        },
        "additionalProperties": False,
    }


def error_envelope_schema() -> dict[str, object]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "error envelope",
        "type": "object",
        "required": [
            "ok",
            "schema",
            "command",
            "request_id",
            "generated_at",
            "duration_ms",
            "warnings",
            "error",
            "artifacts",
            "source",
        ],
        "properties": {
            "ok": {"const": False},
            "schema": {"const": SCHEMA},
            "command": {"type": "string"},
            "request_id": {"type": "string"},
            "generated_at": {"type": "string", "format": "date-time"},
            "duration_ms": {"type": "integer", "minimum": 0},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "error": {
                "type": "object",
                "required": ["code", "message", "details", "retryable"],
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                    "details": {"type": "object", "additionalProperties": True},
                    "retryable": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            "artifacts": {"type": "array"},
            "source": {"type": "object", "additionalProperties": True},
        },
        "additionalProperties": False,
    }
