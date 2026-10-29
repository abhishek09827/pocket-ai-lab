"""Deterministic response evaluation engine for edge AI benchmarking."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


def extract_json_candidate(text: str) -> Optional[Any]:
    """Attempt to parse JSON from direct text or markdown codeblocks."""
    cleaned = text.strip()
    # Check for markdown code blocks
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1).strip())
        except Exception:
            pass

    # Try raw JSON directly
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Try finding the first '{' and last '}'
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(cleaned[first_brace : last_brace + 1])
        except Exception:
            pass

    return None


def evaluate_response(response_text: str, rules: Dict[str, Any]) -> Tuple[bool, str]:
    """Evaluate response against deterministic validation rules.
    
    Returns:
        (passed: bool, notes: str)
    """
    if not rules:
        return True, "No validation rules specified"

    failures: List[str] = []
    text = response_text.strip()
    text_lower = text.lower()

    # Rule: contains_all
    if "contains_all" in rules:
        required_items = rules["contains_all"]
        missing = [item for item in required_items if item.lower() not in text_lower]
        if missing:
            failures.append(f"Missing required keywords: {missing}")

    # Rule: contains_any
    if "contains_any" in rules:
        candidate_items = rules["contains_any"]
        found = any(item.lower() in text_lower for item in candidate_items)
        if not found:
            failures.append(f"None of candidate keywords found: {candidate_items}")

    # Rule: regex
    if "regex" in rules:
        pattern = rules["regex"]
        if not re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            failures.append(f"Did not match regex pattern: {pattern}")

    # Rule: max_words
    if "max_words" in rules:
        max_words = int(rules["max_words"])
        words = text.split()
        if len(words) > max_words:
            failures.append(f"Word count ({len(words)}) exceeds maximum allowed ({max_words})")

    # Rule: max_words_no_char
    if "max_words_no_char" in rules:
        config = rules["max_words_no_char"]
        forbidden_char = config.get("char", "")
        max_words = int(config.get("max_words", 999999))
        words = text.split()
        if forbidden_char and forbidden_char in text:
            failures.append(f"Forbidden character '{forbidden_char}' detected in response")
        if len(words) > max_words:
            failures.append(f"Word count ({len(words)}) exceeds maximum allowed ({max_words})")

    # Rule: json_keys
    if "json_keys" in rules:
        expected_keys = rules["json_keys"]
        parsed = extract_json_candidate(text)
        if parsed is None or not isinstance(parsed, dict):
            failures.append("Failed to parse valid JSON dictionary object")
        else:
            missing_keys = [k for k in expected_keys if k not in parsed]
            if missing_keys:
                failures.append(f"Missing required JSON keys: {missing_keys}")

    passed = len(failures) == 0
    notes = "Passed all checks" if passed else "; ".join(failures)
    return passed, notes
