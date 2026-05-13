# CFP v2 — Simulation-First Constraint Flow Protocol

## Meta

**Version:** 2.0
**Supersedes:** CFP v0.1 (live-check only)
**Status:** Draft — implementation in `src/cfp_v2.py`

---

## 1. Motivation: Compare vs Compute

CFP v1 treats every constraint as a **live check**: the bytecode runs at
verification time, consuming compute proportional to the constraint's
complexity. This works for small rooms but doesn't scale when agents
exchange hundreds of constraints across a fleet.

**Key insight:** During planning/simulation, the constraint was *already
checked*. The agent computed the result, encoded it as bytecode, and
stored it in a PLATO tile. At runtime, we don't need to re-run the
bytecode — we just need to **compare the actual result against the
predicted result**.

This is the "compare vs compute" optimization:

| Mode    | Cost         | When                       |
|---------|-------------|----------------------------|
| Compute | O(n) ops    | No prediction exists (v1)  |
| Compare | O(1) ops    | Prediction exists (v2)     |

CFP v2 makes predictions first-class. The constraint flow becomes:

```
Planning phase:  compute constraint → store prediction + bytecode
Runtime phase:   observe actual → compare against prediction → match/mismatch
```

---

## 2. New Concepts

### 2.1 ConstraintPrediction

A `ConstraintPrediction` wraps a v1 CFP tile with additional metadata:

```python
class ConstraintPrediction:
    tile: dict               # Standard CFP tile (v1 compatible)
    expected_result: Any      # What the constraint should evaluate to
    t_minus_event: float      # Seconds until this constraint becomes "live"
    lamport: int              # Lamport clock for causal ordering
    state: ConstraintState    # Active | Superseded | Retracted
```

### 2.2 t_minus_event Annotations

FLUX bytecode in v2 can carry `t_minus_event` annotations — a countdown
to when the constraint becomes operationally relevant.

**Use case:** An agent plans a deployment at T=0. During simulation
(T=-300s), it emits constraints with `t_minus_event=300`. At T=0, the
fleet confirms each constraint against reality.

```
T=-300s:  emit prediction (t_minus_event=300, expected_result=True)
T=-150s:  emit prediction (t_minus_event=150, expected_result="healthy")
T=0:      observe actual → confirm_prediction(prediction, actual)
```

### 2.3 Confirmation Tiles

Confirmation tiles close the loop: **planned → actual → match/mismatch**.

```python
confirm_prediction(prediction, actual_result)
# Returns: ConfirmationResult.MATCH or ConfirmationResult.MISMATCH
```

A MATCH means the prediction was correct — the constraint holds.
A MISMATCH triggers investigation: the simulation diverged from reality.

### 2.4 Lamport Clock Metadata

When multiple agents emit predictions concurrently, we need causal
ordering. v2 adds a Lamport clock to every prediction:

- Before emitting: `lamport = max(local_clock, received_clock) + 1`
- On receiving: `local_clock = max(local_clock, received_clock)`
- Predictions are totally ordered by `(lamport, agent_id)`

This replaces v1's timestamp-only ordering, which is insufficient for
distributed agents with clock skew.

### 2.5 Constraint State Lifecycle

v2 maps constraint states to tile lifecycle:

```
                ┌──────────┐
                │  Active  │ ← prediction confirmed (MATCH)
                └────┬─────┘
                     │ tighter constraint emitted
                ┌────▼─────┐
                │Superseded│ ← replaced by newer prediction
                └────┬─────┘
                     │ prediction falsified
                ┌────▼─────┐
                │Retracted │ ← MISMATCH, constraint no longer valid
                └──────────┘
```

State transitions:

| From       | Event                    | To         |
|-----------|--------------------------|------------|
| Active     | Tighter constraint       | Superseded |
| Active     | Falsified (MISMATCH)     | Retracted  |
| Superseded | Reactivated              | Active     |
| Retracted  | — (terminal)             | Retracted  |

---

## 3. Wire Format

v2 predictions are encoded as standard CFP tiles with a `cfp_v2` extension:

```json
{
  "domain": "cfp",
  "question": "Fleet health: services check",
  "answer": "01 00 04 01 00 04 20 ...",
  "source": "forgemaster-v2",
  "confidence": 1.0,
  "provenance": {
    "constraint_hash": "a1b2c3...",
    "agent_id": "forgemaster",
    "opcode_count": 13,
    "cfp_version": 2,
    "expected_result": true,
    "t_minus_event": 300.0,
    "lamport": 42,
    "constraint_state": "Active"
  }
}
```

v1 agents ignore the extra `provenance` fields. v2 agents read them.
**Backward compatible.**

---

## 4. Compare vs Compute Optimization

The core optimization is in the verification path:

```python
def verify(prediction, observed_value):
    if prediction.expected_result is not None:
        # COMPARE path: O(1) — just check equality
        return prediction.expected_result == observed_value
    else:
        # COMPUTE path: O(n) — fall back to v1 bytecode execution
        vm = FluxVM()
        vm.load(prediction.opcodes)
        vm.run()
        return vm.result != "ASSERT_FAIL"
```

When the fleet processes 1,000 constraints at runtime:
- **v1:** 1,000 bytecode executions
- **v2:** 1,000 equality comparisons (if all have predictions)

That's potentially 100-1000x cheaper at runtime.

---

## 5. Confirmation Protocol

The confirmation flow is:

1. **Agent A** emits a `ConstraintPrediction` during planning
2. **Agent B** (or A's future self) observes the actual state
3. **Agent B** calls `confirm_prediction(prediction, actual)`
4. Result is a `ConfirmationResult` (MATCH/MISMATCH)
5. If MISMATCH, the constraint state transitions to `Retracted`

Multiple confirmations can be batched:

```python
results = batch_confirm(predictions, actuals)
# Returns list of (prediction_hash, ConfirmationResult)
```

---

## 6. API Summary

```python
from src.cfp_v2 import (
    ConstraintPrediction,    # Prediction wrapper
    ConstraintState,         # Enum: Active, Superseded, Retracted
    ConfirmationResult,      # Enum: MATCH, MISMATCH
    confirm_prediction,      # Compare expected vs actual
    lifecycle_transition,    # State machine for constraint lifecycle
    LamportClock,            # Distributed causal ordering
    batch_confirm,           # Batch confirmation
)
```

---

## 7. Compatibility

| Feature            | v1   | v2   |
|-------------------|------|------|
| Encode/decode      | ✅   | ✅   |
| FluxVM execution   | ✅   | ✅   |
| ConstraintManifold | ✅   | ✅   |
| Predictions        | ❌   | ✅   |
| t_minus_event      | ❌   | ✅   |
| Lamport clocks     | ❌   | ✅   |
| Lifecycle states   | ❌   | ✅   |
| Compare vs compute | ❌   | ✅   |
| Confirmation tiles | ❌   | ✅   |

v2 is a strict superset of v1. All v1 code works unchanged.

---

## 8. Future Work

- **Prediction chains:** predictions that depend on other predictions
- **Confidence decay:** predictions lose confidence as `t_minus_event` grows
- **Speculative execution:** pre-compute predictions for multiple scenarios
- **Rollback:** automatic retraction when a chain of predictions cascades MISMATCH
