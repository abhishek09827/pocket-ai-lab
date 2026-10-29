"""Tool Calling and Function Selection Evaluator.

Evaluates:
- Tool selection accuracy (correct function chosen)
- Argument schema and type compliance
- False positive tool calls on queries that do not require external tools (negative controls)
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


def parse_tool_call_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Attempt to parse function / tool invocation from text.
    
    Supports:
    1. Standard JSON with 'name' and 'arguments' / 'parameters'
    2. Function call notation like `call: get_current_weather(city='Tokyo')`
    3. Markdown wrapped JSON tool calls
    """
    # 1. JSON block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = match.group(1).strip() if match else None
    if not candidate:
        first_b = text.find("{")
        last_b = text.rfind("}")
        if first_b != -1 and last_b > first_b:
            candidate = text[first_b : last_b + 1].strip()

    if candidate:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                # Format 1: {"name": "func", "arguments": {...}}
                if "name" in data and ("arguments" in data or "parameters" in data):
                    args = data.get("arguments") or data.get("parameters")
                    return {"name": data["name"], "arguments": args if isinstance(args, dict) else {}}
                # Format 2: {"tool": "func", "args": {...}}
                if "tool" in data:
                    args = data.get("args") or data.get("arguments") or {}
                    return {"name": data["tool"], "arguments": args}
                # Format 3: Direct function call object e.g. {"get_current_weather": {"city": "Tokyo"}}
                for k, v in data.items():
                    if isinstance(v, dict):
                        return {"name": k, "arguments": v}
        except Exception:
            pass

    # 2. Functional text regex e.g. `get_current_weather(city="Tokyo", unit="celsius")`
    func_match = re.search(r"([a-zA-Z0-9_]+)\s*\((.*?)\)", text)
    if func_match:
        fn_name = func_match.group(1)
        args_str = func_match.group(2)
        # Parse keyword arguments
        arg_pairs = re.findall(r"([a-zA-Z0-9_]+)\s*=\s*['\"]?([^'\",\)]+)['\"]?", args_str)
        if arg_pairs:
            args = {k: v.strip() for k, v in arg_pairs}
            return {"name": fn_name, "arguments": args}

    return None


def evaluate_tool_calling(
    response_text: str,
    task_spec: Dict[str, Any],
) -> Tuple[bool, str, Dict[str, Any]]:
    """Evaluate tool selection, arguments, and negative control compliance."""
    should_call = task_spec.get("should_call_tool", True)
    expected_tool = task_spec.get("expected_tool")
    expected_args = task_spec.get("expected_args") or {}

    tool_call = parse_tool_call_from_text(response_text)

    # Negative control evaluation
    if not should_call:
        if tool_call is not None:
            return False, f"False positive: model invoked tool '{tool_call['name']}' when none was needed", {
                "detected_tool": tool_call["name"],
                "should_call_tool": False,
            }
        return True, "Correctly avoided unnecessary tool invocation", {
            "detected_tool": None,
            "should_call_tool": False,
        }

    # Positive tool call evaluation
    if tool_call is None:
        return False, f"Model failed to invoke required tool '{expected_tool}'", {
            "detected_tool": None,
            "expected_tool": expected_tool,
        }

    detected_name = tool_call.get("name")
    if detected_name != expected_tool:
        return False, f"Incorrect tool selected: expected '{expected_tool}', got '{detected_name}'", {
            "detected_tool": detected_name,
            "expected_tool": expected_tool,
        }

    detected_args = tool_call.get("arguments", {})
    arg_errors = []
    for k, v in expected_args.items():
        if k not in detected_args:
            arg_errors.append(f"Missing parameter '{k}'")
        else:
            actual_val = str(detected_args[k]).lower()
            expected_val = str(v).lower()
            if expected_val not in actual_val and actual_val not in expected_val:
                arg_errors.append(f"Param '{k}': expected '{v}', got '{detected_args[k]}'")

    if arg_errors:
        return False, f"Argument errors: {'; '.join(arg_errors)}", {
            "detected_tool": detected_name,
            "detected_args": detected_args,
            "expected_args": expected_args,
            "arg_errors": arg_errors,
        }

    return True, f"Correctly invoked '{expected_tool}' with valid parameters", {
        "detected_tool": detected_name,
        "detected_args": detected_args,
        "expected_args": expected_args,
    }
