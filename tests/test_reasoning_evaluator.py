"""Tests for Knowledge-Intensive (HotpotQA) and Decision-Making (ALFWorld) evaluation."""
import pytest
from src.reasoning_evaluator import (
    evaluate_alfworld_response,
    evaluate_hotpotqa_response,
    parse_action_steps,
)


def test_hotpotqa_success():
    spec = {
        "expected_answer": "Interstellar",
        "acceptable_variants": ["interstellar"],
        "hallucinated_entities": ["Inception", "Tenet"],
    }
    resp = "Based on Passage A, Christopher Nolan directed Interstellar which won Best Visual Effects in 2014.\nAnswer: Interstellar"
    outcome, note, meta = evaluate_hotpotqa_response(resp, spec)
    assert outcome == "SUCCESS"
    assert "Interstellar" in meta["answer_found"]


def test_hotpotqa_hallucination():
    spec = {
        "expected_answer": "Interstellar",
        "acceptable_variants": ["interstellar"],
        "hallucinated_entities": ["Inception", "Tenet"],
    }
    resp = "The film directed by Christopher Nolan was Inception.\nAnswer: Inception"
    outcome, note, meta = evaluate_hotpotqa_response(resp, spec)
    assert outcome == "HALLUCINATION"
    assert "Inception" in meta["detected_hallucinations"]


def test_alfworld_success():
    spec = {
        "valid_objects": ["mug 1", "lamp 1"],
        "valid_receptacles": ["cabinet 2", "microwave 1", "desk 1"],
        "hallucinated_targets": ["coffee maker 1", "mug 2"],
        "target_object": "mug 1",
        "target_receptacle": "desk 1",
        "required_treatment": "heat",
        "optimal_step_range": [7, 11],
    }
    plan = (
        "1. go to cabinet 2\n"
        "2. open cabinet 2\n"
        "3. take mug 1 from cabinet 2\n"
        "4. go to microwave 1\n"
        "5. open microwave 1\n"
        "6. heat mug 1 with microwave 1\n"
        "7. close microwave 1\n"
        "8. go to desk 1\n"
        "9. put mug 1 on desk 1"
    )
    outcome, note, meta = evaluate_alfworld_response(plan, spec)
    assert outcome == "SUCCESS"


def test_alfworld_hallucination():
    spec = {
        "valid_objects": ["mug 1"],
        "valid_receptacles": ["cabinet 2", "microwave 1", "desk 1"],
        "hallucinated_targets": ["coffee maker 1", "mug 2"],
        "target_object": "mug 1",
        "target_receptacle": "desk 1",
    }
    plan = (
        "1. go to coffee maker 1\n"
        "2. take mug 2 from coffee maker 1\n"
        "3. go to desk 1\n"
        "4. put mug 2 on desk 1"
    )
    outcome, note, meta = evaluate_alfworld_response(plan, spec)
    assert outcome == "HALLUCINATION"


def test_alfworld_invalid_action():
    spec = {
        "valid_objects": ["mug 1"],
        "valid_receptacles": ["cabinet 2", "microwave 1", "desk 1"],
        "hallucinated_targets": [],
        "target_object": "mug 1",
        "target_receptacle": "desk 1",
    }
    # Taking mug 1 from cabinet 2 without opening it first
    plan = (
        "1. go to cabinet 2\n"
        "2. take mug 1 from cabinet 2\n"
        "3. go to desk 1\n"
        "4. put mug 1 on desk 1"
    )
    outcome, note, meta = evaluate_alfworld_response(plan, spec)
    assert outcome == "INVALID_ACTION"


def test_alfworld_inefficient_planning():
    spec = {
        "valid_objects": ["mug 1"],
        "valid_receptacles": ["cabinet 2", "microwave 1", "desk 1"],
        "hallucinated_targets": [],
        "target_object": "mug 1",
        "target_receptacle": "desk 1",
        "optimal_step_range": [3, 5],
    }
    # Redundant loops
    plan = (
        "1. go to cabinet 2\n"
        "2. go to desk 1\n"
        "3. go to cabinet 2\n"
        "4. open cabinet 2\n"
        "5. take mug 1 from cabinet 2\n"
        "6. go to desk 1\n"
        "7. put mug 1 on desk 1"
    )
    outcome, note, meta = evaluate_alfworld_response(plan, spec)
    assert outcome == "INEFFICIENT_PLANNING"
