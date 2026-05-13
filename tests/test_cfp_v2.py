#!/usr/bin/env python3
"""
Unit tests for CFP v2 — Simulation-First Constraint Flow Protocol
==================================================================
Run: python -m pytest tests/test_cfp_v2.py -v
     OR: python -m unittest tests.test_cfp_v2 -v
"""

import sys
import os
import unittest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cfp_v2 import (
    ConstraintPrediction,
    ConstraintState,
    ConfirmationResult,
    LifecycleEvent,
    LamportClock,
    confirm_prediction,
    lifecycle_transition,
    batch_confirm,
    PredictionRegistry,
)


class TestLamportClock(unittest.TestCase):
    """Test Lamport clock operations."""

    def test_initial_value(self):
        clock = LamportClock()
        self.assertEqual(clock.value, 0)

    def test_tick_increments(self):
        clock = LamportClock(5)
        self.assertEqual(clock.tick(), 6)
        self.assertEqual(clock.tick(), 7)
        self.assertEqual(clock.value, 7)

    def test_merge_takes_max(self):
        clock = LamportClock(10)
        clock.merge(15)
        self.assertEqual(clock.value, 15)

    def test_merge_no_decrease(self):
        clock = LamportClock(20)
        clock.merge(5)
        self.assertEqual(clock.value, 20)

    def test_comparison(self):
        a = LamportClock(3)
        b = LamportClock(5)
        self.assertTrue(a < b)
        self.assertFalse(b < a)

    def test_equality(self):
        a = LamportClock(7)
        b = LamportClock(7)
        self.assertEqual(a, b)


class TestLifecycleTransition(unittest.TestCase):
    """Test constraint state machine transitions."""

    def test_active_confirmed_stays_active(self):
        result = lifecycle_transition(ConstraintState.ACTIVE, LifecycleEvent.CONFIRMED)
        self.assertEqual(result, ConstraintState.ACTIVE)

    def test_active_tightened_to_superseded(self):
        result = lifecycle_transition(ConstraintState.ACTIVE, LifecycleEvent.TIGHTENED)
        self.assertEqual(result, ConstraintState.SUPERSEDED)

    def test_active_falsified_to_retracted(self):
        result = lifecycle_transition(ConstraintState.ACTIVE, LifecycleEvent.FALSIFIED)
        self.assertEqual(result, ConstraintState.RETRACTED)

    def test_superseded_reactivated_to_active(self):
        result = lifecycle_transition(ConstraintState.SUPERSEDED, LifecycleEvent.REACTIVATED)
        self.assertEqual(result, ConstraintState.ACTIVE)

    def test_superseded_falsified_to_retracted(self):
        result = lifecycle_transition(ConstraintState.SUPERSEDED, LifecycleEvent.FALSIFIED)
        self.assertEqual(result, ConstraintState.RETRACTED)

    def test_invalid_transition_raises(self):
        with self.assertRaises(ValueError):
            lifecycle_transition(ConstraintState.RETRACTED, LifecycleEvent.CONFIRMED)


class TestConstraintPrediction(unittest.TestCase):
    """Test ConstraintPrediction creation and serialization."""

    def test_create_prediction(self):
        pred = ConstraintPrediction(
            question="Health check",
            answer="4/4 up",
            opcodes=[("PUSH", 4), ("PUSH", 4), ("EQ", None), ("ASSERT", None)],
            agent_id="test-agent",
            expected_result=True,
            t_minus_event=300.0,
            lamport=42,
        )
        self.assertEqual(pred.question, "Health check")
        self.assertEqual(pred.expected_result, True)
        self.assertEqual(pred.t_minus_event, 300.0)
        self.assertEqual(pred.lamport, 42)
        self.assertEqual(pred.state, ConstraintState.ACTIVE)
        self.assertTrue(len(pred.constraint_hash) > 0)

    def test_to_tile_has_v2_provenance(self):
        pred = ConstraintPrediction(
            question="Test",
            answer="",
            opcodes=[("PUSH", 1)],
            agent_id="test",
            expected_result=42,
            lamport=10,
        )
        tile = pred.to_tile()
        prov = tile["provenance"]
        self.assertEqual(prov["cfp_version"], 2)
        self.assertEqual(prov["expected_result"], 42)
        self.assertEqual(prov["lamport"], 10)
        self.assertEqual(prov["constraint_state"], "Active")

    def test_from_tile_roundtrip(self):
        pred = ConstraintPrediction(
            question="Roundtrip test",
            answer="test",
            opcodes=[("PUSH", 4), ("PUSH", 4), ("EQ", None)],
            agent_id="roundtrip-agent",
            expected_result=True,
            t_minus_event=60.0,
            lamport=99,
        )
        tile = pred.to_tile()
        restored = ConstraintPrediction.from_tile(tile)
        self.assertEqual(restored.question, pred.question)
        self.assertEqual(restored.expected_result, pred.expected_result)
        self.assertEqual(restored.t_minus_event, pred.t_minus_event)
        self.assertEqual(restored.lamport, pred.lamport)
        self.assertEqual(restored.constraint_hash, pred.constraint_hash)


class TestConfirmPrediction(unittest.TestCase):
    """Test prediction confirmation (compare vs compute)."""

    def test_match_with_expected_result(self):
        """Compare path: O(1) equality check."""
        pred = ConstraintPrediction(
            question="Services up",
            answer="",
            opcodes=[("PUSH", 4)],
            agent_id="test",
            expected_result=True,
        )
        result = confirm_prediction(pred, True)
        self.assertEqual(result, ConfirmationResult.MATCH)
        self.assertEqual(pred.state, ConstraintState.ACTIVE)

    def test_mismatch_with_expected_result(self):
        """Compare path: mismatch transitions to Retracted."""
        pred = ConstraintPrediction(
            question="Services up",
            answer="",
            opcodes=[("PUSH", 4)],
            agent_id="test",
            expected_result=True,
        )
        result = confirm_prediction(pred, False)
        self.assertEqual(result, ConfirmationResult.MISMATCH)
        self.assertEqual(pred.state, ConstraintState.RETRACTED)

    def test_compute_fallback_on_no_prediction(self):
        """Compute path: execute bytecode when no expected_result."""
        pred = ConstraintPrediction(
            question="Always true",
            answer="",
            opcodes=[("PUSH", 1), ("ASSERT", None)],
            agent_id="test",
            expected_result=None,  # triggers compute path
        )
        result = confirm_prediction(pred, None)  # actual doesn't matter for compute
        self.assertEqual(result, ConfirmationResult.MATCH)

    def test_compute_fallback_assertion_fail(self):
        """Compute path: assertion failure."""
        pred = ConstraintPrediction(
            question="Always false",
            answer="",
            opcodes=[("PUSH", 0), ("ASSERT", None)],
            agent_id="test",
            expected_result=None,
        )
        result = confirm_prediction(pred, None)
        self.assertEqual(result, ConfirmationResult.MISMATCH)
        self.assertEqual(pred.state, ConstraintState.RETRACTED)


class TestBatchConfirm(unittest.TestCase):
    """Test batch confirmation."""

    def test_batch_confirm_mixed(self):
        preds = [
            ConstraintPrediction("p1", "", [("PUSH", 1)], "a", expected_result=True),
            ConstraintPrediction("p2", "", [("PUSH", 2)], "a", expected_result=False),
            ConstraintPrediction("p3", "", [("PUSH", 3)], "a", expected_result="hello"),
        ]
        actuals = [True, True, "hello"]
        results = batch_confirm(preds, actuals)

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0][1], ConfirmationResult.MATCH)
        self.assertEqual(results[1][1], ConfirmationResult.MISMATCH)
        self.assertEqual(results[2][1], ConfirmationResult.MATCH)

    def test_batch_confirm_length_mismatch(self):
        preds = [ConstraintPrediction("p", "", [("PUSH", 1)], "a")]
        with self.assertRaises(ValueError):
            batch_confirm(preds, [True, False])


class TestPredictionRegistry(unittest.TestCase):
    """Test the prediction registry (v2 manifold)."""

    def test_register_and_confirm(self):
        registry = PredictionRegistry("test-room")
        pred = ConstraintPrediction(
            "Service check", "", [("PUSH", 1)], "agent-1",
            expected_result=True, lamport=5,
        )
        ch = registry.register(pred)
        self.assertEqual(len(registry.predictions), 1)

        result = registry.confirm(ch, True)
        self.assertEqual(result, ConfirmationResult.MATCH)
        self.assertEqual(registry.stats()["matches"], 1)

    def test_stats(self):
        registry = PredictionRegistry("stats-room")
        p1 = ConstraintPrediction("a", "", [("PUSH", 1)], "a", expected_result=1, lamport=1)
        p2 = ConstraintPrediction("b", "", [("PUSH", 2)], "a", expected_result=2, lamport=2)
        registry.register(p1)
        registry.register(p2)

        registry.confirm(p1.constraint_hash, 1)  # match
        registry.confirm(p2.constraint_hash, 99)  # mismatch

        stats = registry.stats()
        self.assertEqual(stats["total_predictions"], 2)
        self.assertEqual(stats["confirmed"], 2)
        self.assertEqual(stats["matches"], 1)
        self.assertEqual(stats["mismatches"], 1)
        self.assertEqual(stats["active"], 1)
        self.assertEqual(stats["retracted"], 1)
        self.assertEqual(stats["lamport"], 2)

    def test_register_from_tile(self):
        pred = ConstraintPrediction(
            "Tile test", "", [("PUSH", 42)], "tile-agent",
            expected_result=42, lamport=10,
        )
        tile = pred.to_tile()
        registry = PredictionRegistry("tile-room")
        ch = registry.register_from_tile(tile)
        self.assertIsNotNone(ch)
        self.assertEqual(len(registry.predictions), 1)

    def test_to_json(self):
        registry = PredictionRegistry("json-room")
        pred = ConstraintPrediction("j", "", [("PUSH", 1)], "j", expected_result=True)
        registry.register(pred)
        data = registry.to_json()
        self.assertEqual(data["room_name"], "json-room")
        self.assertEqual(len(data["predictions"]), 1)

    def test_get_by_state(self):
        registry = PredictionRegistry("state-room")
        p1 = ConstraintPrediction("a", "", [("PUSH", 1)], "a", expected_result=True)
        p2 = ConstraintPrediction("b", "", [("PUSH", 2)], "a", expected_result=True)
        registry.register(p1)
        registry.register(p2)

        # Confirm p1 (match), falsify p2
        registry.confirm(p1.constraint_hash, True)
        registry.confirm(p2.constraint_hash, False)

        self.assertEqual(len(registry.get_active()), 1)
        self.assertEqual(len(registry.get_retracted()), 1)
        self.assertEqual(len(registry.get_superseded()), 0)


if __name__ == "__main__":
    unittest.main()
