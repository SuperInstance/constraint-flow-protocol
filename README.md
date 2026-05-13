# CFP — Constraint Flow Protocol


## Meta

**Domain:** constraint-theory
**Depends on:** —
**Depended by:** —
**Implements:** Share understanding between AI agents at the FLUX bytecode level — zero semantic...
**Related:** —


Share understanding between models at the bytecode level.

## Vision

Models in a PLATO room don't just share text — they compile their understanding into FLUX bytecode constraints, exchange them through PLATO tiles, and verify shared understanding through re-execution. Zero semantic drift.

## The Stack

```
┌─────────────────────────────┐
│  PLATO (persistence layer)  │ ← rooms, tiles, hash chain
├─────────────────────────────┤
│  CFP (protocol layer)       │ ← encoded constraints, attribution graphs
├─────────────────────────────┤
│  FLUX ISA (execution layer) │ ← 30-opcode constraint subset
├─────────────────────────────┤
│  SAE (understanding layer)  │ ← future: feature extraction
└─────────────────────────────┘
```

## Why Bytecode?

Three reasons:

1. **Exactness** — Same bytecode, same result, every model. No natural language ambiguity.
2. **Compression** — Bytecode is ~33× denser than natural language for the same constraint.
3. **Verifiability** — Re-execute the bytecode to confirm shared understanding. Proof, not trust.

## Quick Start

```python
from cfp import encode_cfp, decode_cfp, ConstraintManifold

# Encode a constraint as CFP tile
tile = encode_cfp(
    question="Fleet health check",
    answer="4/4 services up",
    opcodes=[(0x01, 4), (0x01, 4), (0x07, None), (0x0E, None)],
    agent_id="my-agent"
)

# Decode a CFP tile
result = decode_cfp(tile)
print(result['constraint_hash'])
```

## Components

- `encode_cfp()` — Encode constraints as CFP tiles
- `decode_cfp()` — Decode CFP tiles with validation
- `ConstraintManifold` — Room-level constraint state
- `FluxVM` — Sandboxed FLUX bytecode executor (30 opcodes)
- `monitor_room()` — Live PLATO room scanner

## Related Fleet Projects

- [PLATO](https://github.com/SuperInstance/plato-sdk) — persistence layer: rooms, tiles, hash-chained memory
- [FLUX ISA](https://github.com/SuperInstance/flux-isa) — 30-opcode constraint bytecode ISA
- **Fleet math** — Laman constraint graphs, H¹ cohomology, ZHC bounds, Pythagorean48
- **A2A protocol** — agent-to-agent routing and discovery
- **Sparse autoencoders** — future: feature extraction from constraint manifolds

## v2 — Simulation-First Extensions

CFP v2 adds prediction-based verification with a "compare vs compute" optimization:
constraints checked during planning only need a cheap O(1) comparison at runtime.

**New in v2:**
- `ConstraintPrediction` — wraps tiles with expected results and t_minus_event annotations
- Confirmation tiles — planned → actual → MATCH/MISMATCH
- Lamport clocks — causal ordering across distributed agents
- Constraint lifecycle — Active → Superseded → Retracted state machine
- PredictionRegistry — v2-aware manifold with batch confirmation

See `CFP-V2-SPEC.md` for the full specification.
See `src/cfp_v2.py` for the implementation.
Run tests: `python -m pytest tests/test_cfp_v2.py -v`

## Status

- **v0.1** — Core encode/decode/manifold working. Full constraint flow over PLATO operational.
- **v2** — Simulation-first extensions with predictions, Lamport clocks, lifecycle states. Tests passing.
- **PLANNED** — SAE integration for feature-level understanding. Attribution graph tracking for provenance.

## Repo Map

- `cfp.py` — CLI + library with encode, decode, manifold, and FluxVM
- `src/cfp_v2.py` — v2 extensions: predictions, Lamport clocks, lifecycle, confirmation
- `tests/test_cfp_v2.py` — unit tests for v2 (15 tests)
- `CFP-V2-SPEC.md` — v2 protocol specification
- `README.md` — this file
