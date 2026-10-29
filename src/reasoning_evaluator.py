"""Evaluator for Knowledge-Intensive (HotpotQA) and Decision-Making (ALFWorld) Tasks.

Classifies agent outcomes and failure modes:
- SUCCESS
- HALLUCINATION (as identified in Shinn & Labash et al., 2023 - Reflexion)
- INEFFICIENT_PLANNING (redundant loops, sub-optimal paths)
- INVALID_ACTION / PRECONDITION_VIOLATION
- INCOMPLETE / FORMAT_ERROR
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional, Tuple

OutcomeType = Literal[
    "SUCCESS",
    "HALLUCINATION",
    "INEFFICIENT_PLANNING",
    "INVALID_ACTION",
    "INCOMPLETE",
]


def evaluate_hotpotqa_response(
    response_text: str,
    spec: Dict[str, Any],
) -> Tuple[OutcomeType, str, Dict[str, Any]]:
    """Evaluate multi-hop knowledge retrieval response."""
    text = response_text.strip()
    text_lower = text.lower()
    orig_expected = spec.get("expected_answer", "")
    expected = orig_expected.lower()
    acceptable = [v.lower() for v in spec.get("acceptable_variants", [])]
    hallucinated_candidates = spec.get("hallucinated_entities", [])
    hallucinated_map = {h.lower(): h for h in hallucinated_candidates}

    # Check for hallucinated entities from context or memory
    detected_hallucinations = [
        hallucinated_map[cand_lower]
        for cand_lower in hallucinated_map
        if cand_lower in text_lower
    ]

    # Check if correct answer is present
    has_expected = (expected in text_lower) or any(v in text_lower for v in acceptable)

    # Check the final line or explicit 'Answer:' declaration if present
    answer_match = re.search(r"answer\s*:\s*([^\n\.]+)", text_lower)
    extracted_answer = answer_match.group(1).strip() if answer_match else None

    if extracted_answer:
        extracted_matches = (expected in extracted_answer) or any(v in extracted_answer for v in acceptable)
        if extracted_matches:
            return "SUCCESS", "Correct multi-hop answer derived", {
                "detected_hallucinations": [],
                "answer_found": orig_expected,
            }
        else:
            # Check if extracted answer is an explicitly tracked hallucination
            for h_lower, h_orig in hallucinated_map.items():
                if h_lower in extracted_answer:
                    return "HALLUCINATION", f"Hallucinated entity declared as answer: '{h_orig}'", {
                        "detected_hallucinations": [h_orig],
                        "answer_found": extracted_answer,
                    }
            return "HALLUCINATION", f"Incorrect answer derived: '{extracted_answer}'", {
                "detected_hallucinations": detected_hallucinations,
                "answer_found": extracted_answer,
            }

    if has_expected and not detected_hallucinations:
        return "SUCCESS", "Correct multi-hop answer present in response", {
            "detected_hallucinations": [],
            "answer_found": expected,
        }

    if detected_hallucinations:
        return "HALLUCINATION", f"Hallucinated false entities detected: {detected_hallucinations}", {
            "detected_hallucinations": detected_hallucinations,
            "answer_found": None,
        }

    return "INCOMPLETE", "Failed to derive or declare expected multi-hop answer", {
        "detected_hallucinations": [],
        "answer_found": None,
    }


def parse_action_steps(text: str) -> List[str]:
    """Extract ordered action steps from response text."""
    steps = []
    lines = text.strip().splitlines()
    for line in lines:
        line = line.strip()
        # Match lines like "1. go to cabinet 1" or "Step 1: go to cabinet 1" or "- go to cabinet 1"
        match = re.match(r"^(?:\d+[\.\)]|step\s*\d+:?|-|\*)\s*(.*)", line, re.IGNORECASE)
        if match:
            action = match.group(1).strip()
            if action:
                steps.append(action)
        elif any(line.lower().startswith(prefix) for prefix in ["go to ", "take ", "open ", "close ", "heat ", "clean ", "cool ", "examine ", "put "]):
            steps.append(line)
    return steps


def evaluate_alfworld_response(
    response_text: str,
    spec: Dict[str, Any],
) -> Tuple[OutcomeType, str, Dict[str, Any]]:
    """Evaluate embodied agent action plan for ALFWorld tasks."""
    steps = parse_action_steps(response_text)
    if not steps:
        return "INCOMPLETE", "No formatted action steps found in response", {"steps_count": 0}

    valid_objects = [o.lower() for o in spec.get("valid_objects", [])]
    valid_receptacles = [r.lower() for r in spec.get("valid_receptacles", [])]
    hallucinated_targets = [h.lower() for h in spec.get("hallucinated_targets", [])]
    target_object = spec.get("target_object", "").lower()
    target_receptacle = spec.get("target_receptacle", "").lower()
    required_treatment = spec.get("required_treatment", "").lower()
    optimal_range = spec.get("optimal_step_range", [5, 10])

    # 1. Check for Hallucinations (referencing objects/receptacles not present in the room)
    detected_hallucinations = []
    for step in steps:
        step_lower = step.lower()
        for h in hallucinated_targets:
            if h in step_lower:
                detected_hallucinations.append(h)

    if detected_hallucinations:
        return (
            "HALLUCINATION",
            f"Agent hallucinated unobserved objects/receptacles: {list(set(detected_hallucinations))}",
            {"steps_count": len(steps), "hallucinations": detected_hallucinations},
        )

    # 2. Check for Precondition / Physical Causality Violations
    held_object: Optional[str] = None
    open_receptacles = set()
    current_location: Optional[str] = None
    treatment_applied = False
    goal_placed = False

    for idx, step in enumerate(steps, start=1):
        step_lower = step.lower()

        # Movement: "go to <receptacle>"
        go_match = re.search(r"go to\s+([a-zA-Z0-9_\s]+)", step_lower)
        if go_match:
            current_location = go_match.group(1).strip()
            continue

        # Open: "open <receptacle>"
        open_match = re.search(r"open\s+([a-zA-Z0-9_\s]+)", step_lower)
        if open_match:
            rec = open_match.group(1).strip()
            open_receptacles.add(rec)
            continue

        # Close: "close <receptacle>"
        close_match = re.search(r"close\s+([a-zA-Z0-9_\s]+)", step_lower)
        if close_match:
            rec = close_match.group(1).strip()
            open_receptacles.discard(rec)
            continue

        # Take: "take <object> from <receptacle>"
        take_match = re.search(r"take\s+([a-zA-Z0-9_\s]+?)\s+from\s+([a-zA-Z0-9_\s]+)", step_lower)
        if take_match:
            obj = take_match.group(1).strip()
            rec = take_match.group(2).strip()
            # If receptacle is a cabinet/fridge that requires opening:
            if any(k in rec for k in ["cabinet", "fridge", "drawer", "microwave"]) and rec not in open_receptacles:
                return (
                    "INVALID_ACTION",
                    f"Precondition violation at step {idx}: tried to take '{obj}' from closed receptacle '{rec}'",
                    {"violated_step": idx, "action": step},
                )
            held_object = obj
            continue

        # Treatment: "heat/clean/cool/examine <object>"
        if required_treatment and required_treatment in step_lower:
            if target_object not in step_lower and (held_object != target_object):
                return (
                    "INVALID_ACTION",
                    f"Precondition violation at step {idx}: attempted {required_treatment} without holding target object '{target_object}'",
                    {"violated_step": idx, "action": step},
                )
            treatment_applied = True
            continue

        # Put: "put <object> on/in <receptacle>"
        put_match = re.search(r"put\s+([a-zA-Z0-9_\s]+?)\s+(?:in|on)\s+([a-zA-Z0-9_\s]+)", step_lower)
        if put_match:
            obj = put_match.group(1).strip()
            rec = put_match.group(2).strip()
            if target_object in obj and target_receptacle in rec:
                goal_placed = True
                held_object = None

    # 3. Check for Inefficient Planning (cycles or excessive steps)
    action_counts: Dict[str, int] = {}
    for step in steps:
        clean = re.sub(r"^\d+\.\s*", "", step.lower())
        action_counts[clean] = action_counts.get(clean, 0) + 1

    redundant_actions = [act for act, count in action_counts.items() if count > 1]
    is_excessive = len(steps) > (optimal_range[1] + 3)

    if redundant_actions or is_excessive:
        return (
            "INEFFICIENT_PLANNING",
            f"Inefficient action plan with redundant cycles: {redundant_actions} (total steps: {len(steps)})",
            {"steps_count": len(steps), "redundant": redundant_actions},
        )

    # 4. Check Goal Completion
    if goal_placed and (not required_treatment or treatment_applied):
        return (
            "SUCCESS",
            f"Optimal physical plan generated in {len(steps)} steps",
            {"steps_count": len(steps), "treatment_applied": treatment_applied},
        )

    return (
        "INCOMPLETE",
        f"Plan did not reach goal completion: goal_placed={goal_placed}, treatment_applied={treatment_applied}",
        {"steps_count": len(steps)},
    )
