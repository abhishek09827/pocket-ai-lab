"""Tests for Application-Level AI Evaluators: Coding, Structured Extraction, Tool Calling, and Embeddings."""
import pytest

from src.coding_evaluator import (
    evaluate_coding_task,
    evaluate_sql_query,
    extract_code_block,
    run_sandboxed_python_tests,
    validate_python_syntax,
)
from src.embedding_evaluator import (
    compute_aggregate_retrieval_metrics,
    cosine_similarity,
    evaluate_retrieval_ranking,
)
from src.structured_evaluator import (
    evaluate_structured_extraction,
    extract_json_candidate,
    validate_type,
)
from src.tool_calling_evaluator import (
    evaluate_tool_calling,
    parse_tool_call_from_text,
)


class TestCodingEvaluator:
    """Test sandboxed Python execution and SQL verification."""

    def test_extract_code_block(self):
        md = "Here is the solution:\n```python\ndef add(a, b):\n    return a + b\n```\nDone."
        assert extract_code_block(md, "python") == "def add(a, b):\n    return a + b"

    def test_validate_syntax(self):
        valid_code = "def solve(x):\n    return x * 2"
        ok, err = validate_python_syntax(valid_code)
        assert ok is True
        assert err is None

        invalid_code = "def solve(x) return x * 2"
        ok, err = validate_python_syntax(invalid_code)
        assert ok is False
        assert "SyntaxError" in err

    def test_run_sandboxed_tests_success(self):
        code = "def fib(n):\n    if n <= 1: return n\n    a, b = 0, 1\n    for _ in range(n - 1): a, b = b, a + b\n    return b"
        tcs = [{"input": [0], "expected": 0}, {"input": [1], "expected": 1}, {"input": [6], "expected": 8}]
        passed, notes, details = run_sandboxed_python_tests(code, "fib", tcs)
        assert passed is True
        assert details["passed_tests"] == 3

    def test_run_sandboxed_tests_failure(self):
        code = "def fib(n):\n    return 0"
        tcs = [{"input": [1], "expected": 1}]
        passed, notes, details = run_sandboxed_python_tests(code, "fib", tcs)
        assert passed is False
        assert details["passed_tests"] == 0

    def test_sandboxed_timeout_protection(self):
        infinite_loop = "def hang():\n    while True: pass"
        tcs = [{"input": [], "expected": 1}]
        passed, notes, details = run_sandboxed_python_tests(infinite_loop, "hang", tcs, timeout_sec=0.5)
        assert passed is False
        assert "timed out" in notes

    def test_sql_query_evaluation(self):
        sql = "SELECT c.name, SUM(o.amount) FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.name ORDER BY 2 DESC LIMIT 3;"
        required = ["SELECT", "FROM", "JOIN", "GROUP BY", "ORDER BY", "LIMIT"]
        passed, notes, details = evaluate_sql_query(sql, required)
        assert passed is True

        missing_sql = "SELECT name FROM customers"
        passed, notes, details = evaluate_sql_query(missing_sql, required)
        assert passed is False
        assert "Missing required SQL tokens" in notes


class TestStructuredEvaluator:
    """Test JSON schema compliance, typing, and negative control extra-key rejection."""

    def test_extract_json_candidate(self):
        text = 'Prefix text ```json\n{"name": "Alice", "age": 30}\n``` suffix'
        cand = extract_json_candidate(text)
        assert cand == '{"name": "Alice", "age": 30}'

    def test_schema_types(self):
        assert validate_type("test", "string") is True
        assert validate_type(42, "integer") is True
        assert validate_type(42.5, "number") is True
        assert validate_type(True, "integer") is False  # In Python, bool is subclass of int

    def test_structured_success(self):
        spec = {
            "expected_schema": {
                "required": ["name", "age"],
                "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            },
            "allow_extra_keys": True,
            "expected_values": {"name": "Alice"},
        }
        resp = '{"name": "Alice", "age": 28}'
        passed, notes, details = evaluate_structured_extraction(resp, spec)
        assert passed is True

    def test_negative_control_extra_keys_rejection(self):
        spec = {
            "expected_schema": {
                "required": ["flight_num"],
                "properties": {"flight_num": {"type": "string"}},
            },
            "allow_extra_keys": False,
            "prohibited_keys": ["pilot_name", "weather"],
        }
        resp_hallucinated = '{"flight_num": "AI-101", "pilot_name": "Capt. Roy"}'
        passed, notes, details = evaluate_structured_extraction(resp_hallucinated, spec)
        assert passed is False
        assert "prohibited keys" in notes.lower() or "extra keys" in notes.lower()


class TestToolCallingEvaluator:
    """Test function selection, arguments, and false-positive prevention."""

    def test_parse_tool_call_json(self):
        raw = '{"name": "get_current_weather", "arguments": {"city": "Tokyo", "unit": "celsius"}}'
        parsed = parse_tool_call_from_text(raw)
        assert parsed is not None
        assert parsed["name"] == "get_current_weather"
        assert parsed["arguments"]["city"] == "Tokyo"

    def test_parse_tool_call_syntax(self):
        raw = 'get_current_weather(city="Paris", unit="imperial")'
        parsed = parse_tool_call_from_text(raw)
        assert parsed is not None
        assert parsed["name"] == "get_current_weather"
        assert parsed["arguments"]["city"] == "Paris"

    def test_tool_calling_positive_success(self):
        spec = {
            "should_call_tool": True,
            "expected_tool": "get_current_weather",
            "expected_args": {"city": "Tokyo", "unit": "celsius"},
        }
        resp = '{"name": "get_current_weather", "arguments": {"city": "Tokyo", "unit": "celsius"}}'
        passed, notes, details = evaluate_tool_calling(resp, spec)
        assert passed is True

    def test_tool_calling_negative_control_false_positive(self):
        spec = {
            "should_call_tool": False,
            "expected_tool": None,
        }
        # Model hallucinated a tool call when not needed
        bad_resp = '{"name": "search_knowledge_base", "arguments": {"query": "15*24"}}'
        passed, notes, details = evaluate_tool_calling(bad_resp, spec)
        assert passed is False
        assert "False positive" in notes

        # Model correctly provided direct text
        good_resp = "15 multiplied by 24 is 360."
        passed, notes, details = evaluate_tool_calling(good_resp, spec)
        assert passed is True


class TestEmbeddingEvaluator:
    """Test cosine similarity, Recall@1/5, and MRR metrics."""

    def test_cosine_similarity(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        assert cosine_similarity(v1, v2) == pytest.approx(1.0)

        v_ortho = [0.0, 1.0, 0.0]
        assert cosine_similarity(v1, v_ortho) == pytest.approx(0.0)

    def test_evaluate_retrieval_ranking(self):
        q_vec = [1.0, 0.0]
        corpus = {
            "doc_best": [0.99, 0.01],
            "doc_mid": [0.5, 0.5],
            "doc_worst": [0.0, 1.0],
        }
        res = evaluate_retrieval_ranking(q_vec, corpus, ["doc_best"])
        assert res["recall_at_1"] == 1.0
        assert res["recall_at_5"] == 1.0
        assert res["mrr"] == 1.0
        assert res["top_5_results"][0] == "doc_best"

        # Relevant is second
        res2 = evaluate_retrieval_ranking(q_vec, corpus, ["doc_mid"])
        assert res2["recall_at_1"] == 0.0
        assert res2["recall_at_5"] == 1.0
        assert res2["mrr"] == 0.5
