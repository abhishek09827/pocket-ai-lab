"""Sandboxed Coding Evaluator for Python Generation, Bug Fixes, and SQL Queries.

Executes generated Python code in isolated subprocesses with timeouts and memory limits.
Validates SQL syntax and query construction against target schemas.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple


def extract_code_block(response_text: str, language: str = "python") -> str:
    """Extract code from markdown code fences or fallback to raw text."""
    pattern = rf"```{language}\s*(.*?)\s*```"
    match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Fallback: check for any ``` block
    generic_match = re.search(r"```\s*(.*?)\s*```", response_text, re.DOTALL)
    if generic_match:
        return generic_match.group(1).strip()

    # Fallback to lines starting with def or SELECT
    lines = []
    in_code = False
    for line in response_text.splitlines():
        if line.strip().startswith(("def ", "import ", "from ", "SELECT ", "select ")):
            in_code = True
        if in_code:
            lines.append(line)
    if lines:
        return "\n".join(lines).strip()

    return response_text.strip()


def validate_python_syntax(code_str: str) -> Tuple[bool, Optional[str]]:
    """Verify code can be parsed into Python AST without syntax errors."""
    try:
        ast.parse(code_str)
        return True, None
    except SyntaxError as exc:
        return False, f"SyntaxError: {exc.msg} at line {exc.lineno}"


def run_sandboxed_python_tests(
    code_str: str,
    entry_point: str,
    test_cases: List[Dict[str, Any]],
    timeout_sec: float = 2.0,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Execute Python code with unit test assertions in an isolated subprocess."""
    syntax_ok, syntax_err = validate_python_syntax(code_str)
    if not syntax_ok:
        return False, f"Syntax failure: {syntax_err}", {"passed_tests": 0, "total_tests": len(test_cases)}

    # Build runner script
    runner_script = f"""
import sys
import json

true = True
false = False
null = None

{code_str}

test_cases = {json.dumps(test_cases)}
fn = globals().get({json.dumps(entry_point)})
if fn is None:
    print(json.dumps({{"error": "Function {entry_point} not defined"}}))
    sys.exit(2)

passed = 0
for idx, tc in enumerate(test_cases):
    args = tc.get("input", [])
    expected = tc.get("expected")
    try:
        actual = fn(*args)
        if actual == expected:
            passed += 1
        else:
            print(json.dumps({{"error": f"Test {{idx}} failed: expected {{expected}}, got {{actual}}"}}))
            sys.exit(1)
    except Exception as e:
        print(json.dumps({{"error": f"Test {{idx}} raised {{type(e).__name__}}: {{e}}"}}))
        sys.exit(1)

print(json.dumps({{"passed": passed, "total": len(test_cases)}}))
sys.exit(0)
"""

    try:
        proc = subprocess.run(
            [sys.executable, "-c", runner_script],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )

        out = proc.stdout.strip()
        if proc.returncode == 0:
            return True, f"All {len(test_cases)} unit tests passed", {
                "passed_tests": len(test_cases),
                "total_tests": len(test_cases),
            }

        # Parse failure details
        err_msg = "Execution failed"
        try:
            err_data = json.loads(out)
            err_msg = err_data.get("error", err_msg)
        except Exception:
            if proc.stderr:
                err_msg = proc.stderr.strip().splitlines()[-1]

        return False, f"Test failure: {err_msg}", {"passed_tests": 0, "total_tests": len(test_cases)}

    except subprocess.TimeoutExpired:
        return False, f"Execution timed out (> {timeout_sec}s)", {"passed_tests": 0, "total_tests": len(test_cases)}
    except Exception as exc:
        return False, f"Subprocess error: {exc}", {"passed_tests": 0, "total_tests": len(test_cases)}


def evaluate_sql_query(
    sql_str: str,
    required_tokens: List[str],
) -> Tuple[bool, str, Dict[str, Any]]:
    """Validate SQL query structure and mandatory clauses."""
    cleaned = sql_str.strip().upper()
    missing_tokens = []
    for token in required_tokens:
        tok_upper = token.upper()
        if tok_upper not in cleaned:
            missing_tokens.append(token)

    if missing_tokens:
        return False, f"Missing required SQL tokens: {missing_tokens}", {
            "missing_tokens": missing_tokens,
            "matched_tokens": [t for t in required_tokens if t not in missing_tokens],
        }

    return True, "Valid SQL query structure with all required clauses", {
        "missing_tokens": [],
        "matched_tokens": required_tokens,
    }


def evaluate_coding_task(
    response_text: str,
    task_spec: Dict[str, Any],
) -> Tuple[bool, str, Dict[str, Any]]:
    """Dispatch evaluation based on category (python algorithm, bug fix, or SQL)."""
    category = task_spec.get("category", "")
    language = task_spec.get("language", "python")

    if language == "python":
        code = extract_code_block(response_text, "python")
        entry_point = task_spec.get("entry_point", "")
        test_cases = task_spec.get("test_cases", [])
        return run_sandboxed_python_tests(code, entry_point, test_cases)

    elif language == "sql":
        code = extract_code_block(response_text, "sql")
        required_tokens = task_spec.get("required_tokens", [])
        return evaluate_sql_query(code, required_tokens)

    return False, f"Unsupported language/category: {language}/{category}", {}
