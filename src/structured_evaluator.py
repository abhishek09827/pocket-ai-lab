"""Structured Extraction Evaluator for JSON Schema Compliance and Negative Controls.

Evaluates:
- JSON parsing and markdown fence stripping
- Schema type conformity (string, integer, number, boolean, array, object)
- Missing required keys
- Hallucinated extra keys (negative controls)
- Multilingual and value-level accuracy
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


def extract_json_candidate(text: str) -> Optional[str]:
    """Extract first valid JSON object candidate from text or markdown blocks."""
    # Try markdown json fence
    md_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if md_match:
        return md_match.group(1).strip()

    # Try outermost balanced brackets
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1].strip()

    return None


def validate_type(val: Any, expected_type: str) -> bool:
    """Validate JSON value against primitive JSON schema types."""
    if expected_type == "string":
        return isinstance(val, str)
    elif expected_type == "integer":
        return isinstance(val, int) and not isinstance(val, bool)
    elif expected_type == "number":
        return (isinstance(val, (int, float))) and not isinstance(val, bool)
    elif expected_type == "boolean":
        return isinstance(val, bool)
    elif expected_type == "array":
        return isinstance(val, list)
    elif expected_type == "object":
        return isinstance(val, dict)
    return True


def evaluate_structured_extraction(
    response_text: str,
    task_spec: Dict[str, Any],
) -> Tuple[bool, str, Dict[str, Any]]:
    """Evaluate JSON schema compliance, key presence, types, and prohibited hallucinations."""
    json_candidate = extract_json_candidate(response_text)
    if not json_candidate:
        return False, "No valid JSON object detected in response", {"raw_extracted": None}

    try:
        parsed_data = json.loads(json_candidate)
        if not isinstance(parsed_data, dict):
            return False, "JSON root is not an object/dictionary", {"raw_extracted": parsed_data}
    except json.JSONDecodeError as exc:
        return False, f"JSONDecodeError: {exc}", {"raw_extracted": json_candidate}

    expected_schema = task_spec.get("expected_schema", {})
    required_keys = expected_schema.get("required", [])
    properties = expected_schema.get("properties", {})
    allow_extra_keys = task_spec.get("allow_extra_keys", True)
    prohibited_keys = set(task_spec.get("prohibited_keys", []))

    missing_keys = [k for k in required_keys if k not in parsed_data]
    if missing_keys:
        return False, f"Missing required keys: {missing_keys}", {
            "missing_keys": missing_keys,
            "parsed_keys": list(parsed_data.keys()),
        }

    # Type validation
    type_errors = []
    for prop, prop_def in properties.items():
        if prop in parsed_data:
            expected_type = prop_def.get("type")
            if expected_type and not validate_type(parsed_data[prop], expected_type):
                type_errors.append(f"Key '{prop}' expected {expected_type}, got {type(parsed_data[prop]).__name__}")

    if type_errors:
        return False, f"Type mismatches: {'; '.join(type_errors)}", {
            "type_errors": type_errors,
            "parsed_data": parsed_data,
        }

    # Prohibited / hallucinated keys check
    found_prohibited = [k for k in parsed_data if k in prohibited_keys]
    if found_prohibited:
        return False, f"Hallucinated prohibited keys detected: {found_prohibited}", {
            "hallucinated_keys": found_prohibited,
            "parsed_data": parsed_data,
        }

    if not allow_extra_keys:
        allowed_keys = set(properties.keys())
        extra_keys = [k for k in parsed_data if k not in allowed_keys]
        if extra_keys:
            return False, f"Strict schema violated: extra keys found {extra_keys}", {
                "extra_keys": extra_keys,
                "parsed_data": parsed_data,
            }

    # Value-level matching if specified
    expected_values = task_spec.get("expected_values", {})
    value_mismatches = []
    for k, v in expected_values.items():
        actual_val = parsed_data.get(k)
        if isinstance(v, str):
            if v.lower() not in str(actual_val).lower():
                value_mismatches.append(f"Key '{k}': expected '{v}', got '{actual_val}'")
        elif v != actual_val:
            value_mismatches.append(f"Key '{k}': expected {v}, got {actual_val}")

    if value_mismatches:
        return False, f"Value mismatch: {'; '.join(value_mismatches)}", {
            "value_mismatches": value_mismatches,
            "parsed_data": parsed_data,
        }

    return True, "Schema valid and all constraints satisfied", {
        "parsed_data": parsed_data,
        "matched_keys": list(parsed_data.keys()),
    }
