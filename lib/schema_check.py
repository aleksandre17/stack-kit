"""The manifest schema, enforced on every machine (ADR-001 K4).

Before this module `validate` handed `manifest.schema.json` to `jsonschema` when it was installed
and skipped it when it was not -- so on a host that had installed nothing, every `required`,
`enum` and `additionalProperties: false` in the schema was decoration, and a misspelled key passed.
A contract that holds only on some machines is not a contract.

So the schema is interpreted here, for exactly the keywords it uses -- the agent kit's validator
(`kit/interpreters/validation.py`) in the same handwriting, with the three this schema also needs:
`oneOf`, `additionalProperties` as a schema, `patternProperties`, and the `default` annotation. A keyword outside that
set is refused loudly: a validator that silently ignores half its schema is a surface that lies.
"""
from __future__ import annotations

import re
from typing import Any

SUPPORTED = {
    "$id", "$schema", "title", "description", "default",
    "type", "enum", "const", "required", "properties", "additionalProperties", "patternProperties",
    "items", "minItems", "minLength", "pattern", "minimum", "maximum", "oneOf",
}

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


class UnsupportedSchema(Exception):
    """The schema uses a keyword this interpreter cannot honour."""


def _type_ok(value: Any, name: str) -> bool:
    if name in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[name])


def validate(instance: Any, schema: dict[str, Any], path: str = "(root)") -> list[str]:
    """Human-readable errors, `path: what is wrong`; an empty list means valid."""
    unknown = set(schema) - SUPPORTED
    if unknown:
        raise UnsupportedSchema(f"{path}: unsupported schema keywords {sorted(unknown)}")
    errors: list[str] = []

    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        for name in names:
            if name not in _TYPES:
                raise UnsupportedSchema(f"{path}: unknown type {name!r}")
        if not any(_type_ok(instance, n) for n in names):
            return [f"{path}: expected {'/'.join(names)}, got {type(instance).__name__}"]

    if "oneOf" in schema:
        held = [b for b in schema["oneOf"] if not validate(instance, b, path)]
        if len(held) != 1:
            errors.append(f"{path}: must match exactly one of {len(schema['oneOf'])} shapes, matched {len(held)}")

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']!r}")

    numeric = isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if "minimum" in schema and numeric and instance < schema["minimum"]:
        errors.append(f"{path}: {instance!r} is below the minimum {schema['minimum']!r}")
    if "maximum" in schema and numeric and instance > schema["maximum"]:
        errors.append(f"{path}: {instance!r} is above the maximum {schema['maximum']!r}")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match {schema['pattern']!r}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, item in enumerate(instance):
                errors += validate(item, schema["items"], f"{path}[{i}]")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required {key!r}")
        properties = schema.get("properties", {})
        for key, sub in properties.items():
            if key in instance:
                errors += validate(instance[key], sub, key if path == "(root)" else f"{path}.{key}")
        extra = schema.get("additionalProperties", True)
        patterned = schema.get("patternProperties", {})
        for key in instance:
            if key in properties:
                continue
            where = key if path == "(root)" else f"{path}.{key}"
            matched = [sub for pattern, sub in patterned.items() if re.search(pattern, key)]
            if matched:
                for sub in matched:
                    errors += validate(instance[key], sub, where)
                continue
            if extra is False:
                errors.append(f"{where}: not declared by the schema")
            elif isinstance(extra, dict):
                errors += validate(instance[key], extra, where)
    return errors
