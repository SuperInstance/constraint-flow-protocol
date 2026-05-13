#!/usr/bin/env python3
"""
CFP v2 — Simulation-First Constraint Flow Protocol
====================================================
Extends CFP v1 with prediction-based verification, Lamport clocks,
and constraint lifecycle management.

Key optimization: "Compare vs Compute"
  - If a prediction exists, just compare (cheap) instead of recompute (expensive)
  - Predictions are made during planning/simulation, confirmed at runtime

Components:
  1. ConstraintPrediction — wraps a CFP tile with expected result + metadata
  2. LamportClock — distributed causal ordering
  3. confirm_prediction() — compare expected vs actual
  4. lifecycle_transition() — state machine: Active → Superseded → Retracted
  5. batch_confirm() — batch confirmation of multiple predictions

Python stdlib only. No external dependencies.
"""

import hashlib
import json
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# Re-export v1 for backward compatibility
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cfp import encode_cfp, decode_cfp, FluxVM, ConstraintManifold


# ═══════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════

class ConstraintState(Enum):
    """Lifecycle states for a constraint prediction."""
    ACTIVE = "Active"
    SUPERSEDED = "Superseded"
    RETRACTED = "Retracted"


class ConfirmationResult(Enum):
    """Result of confirming a prediction against actual data."""
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"


class LifecycleEvent(Enum):
    """Events that trigger state transitions."""
    CONFIRMED = "confirmed"           # prediction matched reality
    TIGHTENED = "tightened"           # newer, tighter constraint emitted
    FALSIFIED = "falsified"           # prediction did not match reality
    REACTIVATED = "reactivated"       # superseded constraint re-activated


# ═══════════════════════════════════════════════════════════════════
# State Machine
# ═══════════════════════════════════════════════════════════════════

# Valid transitions: (from_state, event) → to_state
_TRANSITIONS: Dict[Tuple[ConstraintState, LifecycleEvent], ConstraintState] = {
    (ConstraintState.ACTIVE, LifecycleEvent.TIGHTENED):    ConstraintState.SUPERSEDED,
    (ConstraintState.ACTIVE, LifecycleEvent.FALSIFIED):    ConstraintState.RETRACTED,
    (ConstraintState.SUPERSEDED, LifecycleEvent.REACTIVATED): ConstraintState.ACTIVE,
    (ConstraintState.SUPERSEDED, LifecycleEvent.FALSIFIED):   ConstraintState.RETRACTED,
    # CONFIRMED is a no-op for ACTIVE (stays ACTIVE)
    (ConstraintState.ACTIVE, LifecycleEvent.CONFIRMED):    ConstraintState.ACTIVE,
}


def lifecycle_transition(
    state: ConstraintState,
    event: LifecycleEvent,
) -> ConstraintState:
    """
    Apply a lifecycle event to a constraint state.

    Parameters
    ----------
    state : ConstraintState
        Current state of the constraint.
    event : LifecycleEvent
        Event triggering the transition.

    Returns
    -------
    ConstraintState
        New state after the transition.

    Raises
    ------
    ValueError
        If the transition is invalid.
    """
    key = (state, event)
    if key in _TRANSITIONS:
        return _TRANSITIONS[key]
    raise ValueError(
        f"Invalid lifecycle transition: {state.value} + {event.value}"
    )


# ═══════════════════════════════════════════════════════════════════
# Lamport Clock
# ═══════════════════════════════════════════════════════════════════

class LamportClock:
    """
    Lamport clock for causal ordering across distributed agents.

    Usage:
      - Before emitting a prediction: clock.tick()
      - On receiving a remote clock value: clock.merge(remote_value)
      - Current value: clock.value
    """

    def __init__(self, initial: int = 0):
        self._value = initial

    @property
    def value(self) -> int:
        return self._value

    def tick(self) -> int:
        """Increment and return the new clock value (before emitting)."""
        self._value += 1
        return self._value

    def merge(self, remote_value: int) -> int:
        """Merge with a remote clock value (on receiving)."""
        self._value = max(self._value, remote_value)
        return self._value

    def __repr__(self) -> str:
        return f"LamportClock({self._value})"

    def __eq__(self, other) -> bool:
        if isinstance(other, LamportClock):
            return self._value == other._value
        return NotImplemented

    def __lt__(self, other) -> bool:
        if isinstance(other, LamportClock):
            return self._value < other._value
        return NotImplemented


# ═══════════════════════════════════════════════════════════════════
# ConstraintPrediction
# ═══════════════════════════════════════════════════════════════════

class ConstraintPrediction:
    """
    A prediction about a future constraint state.

    Wraps a v1 CFP tile with:
      - expected_result: what the constraint should evaluate to
      - t_minus_event: seconds until this becomes operationally live
      - lamport: Lamport clock for causal ordering
      - state: lifecycle state (Active/Superseded/Retracted)

    Backward compatible: the underlying tile is a standard v1 CFP tile
    with extra provenance fields.
    """

    def __init__(
        self,
        question: str,
        answer: str,
        opcodes: List[Tuple[str, Optional[int]]],
        agent_id: str,
        expected_result: Any = None,
        t_minus_event: float = 0.0,
        lamport: int = 0,
        state: ConstraintState = ConstraintState.ACTIVE,
    ):
        self.question = question
        self.answer = answer
        self.opcodes = opcodes
        self.agent_id = agent_id
        self.expected_result = expected_result
        self.t_minus_event = t_minus_event
        self.lamport = lamport
        self.state = state

        # Build underlying v1 tile
        self._tile = encode_cfp(question, answer, opcodes, agent_id)
        # Inject v2 provenance
        self._tile["provenance"].update({
            "cfp_version": 2,
            "expected_result": expected_result,
            "t_minus_event": t_minus_event,
            "lamport": lamport,
            "constraint_state": state.value,
        })
        self.constraint_hash = self._tile["provenance"]["constraint_hash"]

    @classmethod
    def from_tile(cls, tile: dict) -> "ConstraintPrediction":
        """
        Reconstruct a ConstraintPrediction from a v2-augmented CFP tile.
        """
        prov = tile.get("provenance", {})
        # Decode opcodes from the tile
        decoded = decode_cfp(tile)
        if decoded is None:
            raise ValueError("Cannot decode CFP tile")

        return cls(
            question=tile.get("question", ""),
            answer=tile.get("answer", ""),
            opcodes=decoded["opcodes"],
            agent_id=tile.get("source", "unknown"),
            expected_result=prov.get("expected_result"),
            t_minus_event=prov.get("t_minus_event", 0.0),
            lamport=prov.get("lamport", 0),
            state=ConstraintState(prov.get("constraint_state", "Active")),
        )

    def to_tile(self) -> dict:
        """Return the v2-augmented CFP tile (backward compatible)."""
        return dict(self._tile)

    def __repr__(self) -> str:
        return (
            f"ConstraintPrediction(hash={self.constraint_hash[:12]}…, "
            f"state={self.state.value}, lamport={self.lamport}, "
            f"t_minus={self.t_minus_event}s)"
        )


# ═══════════════════════════════════════════════════════════════════
# Confirmation
# ═══════════════════════════════════════════════════════════════════

def confirm_prediction(
    prediction: ConstraintPrediction,
    actual_result: Any,
) -> ConfirmationResult:
    """
    Confirm a prediction against an observed actual result.

    If the prediction has an expected_result, this is a O(1) compare.
    If not, falls back to O(n) bytecode execution (v1 path).

    Parameters
    ----------
    prediction : ConstraintPrediction
        The prediction to confirm.
    actual_result : Any
        The observed actual value.

    Returns
    -------
    ConfirmationResult
        MATCH if prediction was correct, MISMATCH otherwise.
    """
    if prediction.expected_result is not None:
        # Compare path: O(1)
        is_match = (prediction.expected_result == actual_result)
    else:
        # Compute path: O(n) — execute bytecode
        vm = FluxVM()
        vm.load(prediction.opcodes)
        vm.run()
        is_match = (vm.result != "ASSERT_FAIL")

    result = ConfirmationResult.MATCH if is_match else ConfirmationResult.MISMATCH

    # Apply lifecycle transition
    event = LifecycleEvent.CONFIRMED if is_match else LifecycleEvent.FALSIFIED
    try:
        prediction.state = lifecycle_transition(prediction.state, event)
    except ValueError:
        pass  # Invalid transition (e.g., confirming a Retracted constraint)

    return result


def batch_confirm(
    predictions: List[ConstraintPrediction],
    actuals: List[Any],
) -> List[Tuple[str, ConfirmationResult]]:
    """
    Confirm multiple predictions against actual values.

    Parameters
    ----------
    predictions : List[ConstraintPrediction]
        Predictions to confirm.
    actuals : List[Any]
        Corresponding actual values.

    Returns
    -------
    List of (constraint_hash, ConfirmationResult) tuples.
    """
    if len(predictions) != len(actuals):
        raise ValueError(
            f"Mismatched lengths: {len(predictions)} predictions, "
            f"{len(actuals)} actuals"
        )

    results = []
    for pred, actual in zip(predictions, actuals):
        result = confirm_prediction(pred, actual)
        results.append((pred.constraint_hash, result))
    return results


# ═══════════════════════════════════════════════════════════════════
# Prediction Registry (v2 manifold extension)
# ═══════════════════════════════════════════════════════════════════

class PredictionRegistry:
    """
    Tracks predictions and their confirmation status.
    Extends ConstraintManifold with v2 semantics.
    """

    def __init__(self, room_name: str = "unnamed"):
        self.room_name = room_name
        self.predictions: Dict[str, ConstraintPrediction] = {}
        self.confirmations: Dict[str, ConfirmationResult] = {}
        self._lamport = LamportClock()

    def register(self, prediction: ConstraintPrediction) -> str:
        """
        Register a new prediction. Returns the constraint hash.

        Merges Lamport clock from the prediction.
        """
        self._lamport.merge(prediction.lamport)
        ch = prediction.constraint_hash
        self.predictions[ch] = prediction
        return ch

    def register_from_tile(self, tile: dict) -> Optional[str]:
        """Register a prediction from a v2 CFP tile."""
        try:
            pred = ConstraintPrediction.from_tile(tile)
            return self.register(pred)
        except (ValueError, KeyError):
            return None

    def confirm(self, constraint_hash: str, actual: Any) -> Optional[ConfirmationResult]:
        """Confirm a registered prediction."""
        pred = self.predictions.get(constraint_hash)
        if pred is None:
            return None
        result = confirm_prediction(pred, actual)
        self.confirmations[constraint_hash] = result
        return result

    def get_active(self) -> List[ConstraintPrediction]:
        """Return all predictions in Active state."""
        return [
            p for p in self.predictions.values()
            if p.state == ConstraintState.ACTIVE
        ]

    def get_superseded(self) -> List[ConstraintPrediction]:
        """Return all predictions in Superseded state."""
        return [
            p for p in self.predictions.values()
            if p.state == ConstraintState.SUPERSEDED
        ]

    def get_retracted(self) -> List[ConstraintPrediction]:
        """Return all predictions in Retracted state."""
        return [
            p for p in self.predictions.values()
            if p.state == ConstraintState.RETRACTED
        ]

    def stats(self) -> dict:
        """Return summary statistics."""
        total = len(self.predictions)
        confirmed = len(self.confirmations)
        matches = sum(
            1 for r in self.confirmations.values()
            if r == ConfirmationResult.MATCH
        )
        mismatches = confirmed - matches
        return {
            "total_predictions": total,
            "confirmed": confirmed,
            "matches": matches,
            "mismatches": mismatches,
            "active": len(self.get_active()),
            "superseded": len(self.get_superseded()),
            "retracted": len(self.get_retracted()),
            "lamport": self._lamport.value,
        }

    def to_json(self) -> dict:
        """Serialize to JSON-safe dict."""
        return {
            "room_name": self.room_name,
            "lamport": self._lamport.value,
            "predictions": {
                h: {
                    "question": p.question,
                    "agent_id": p.agent_id,
                    "expected_result": p.expected_result,
                    "t_minus_event": p.t_minus_event,
                    "lamport": p.lamport,
                    "state": p.state.value,
                    "constraint_hash": p.constraint_hash,
                }
                for h, p in self.predictions.items()
            },
            "confirmations": {
                h: r.value for h, r in self.confirmations.items()
            },
        }
