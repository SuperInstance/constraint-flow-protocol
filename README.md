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

## Status

- **v0.1** — Core encode/decode/manifold working. Full constraint flow over PLATO operational.
- **PLANNED** — SAE integration for feature-level understanding. Attribution graph tracking for provenance.

## Repo Map

- `cfp.py` — 1,102 lines: CLI + library with encode, decode, manifold, and FluxVM
- `CFP-SPEC.md` — 142 lines: protocol specification (placeholder — coming soon)
- `README.md` — this file
