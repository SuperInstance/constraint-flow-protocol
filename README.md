# Constraint Flow Protocol (CFP) — v0.1

Share understanding between AI agents at the bytecode level. Models exchange constraints as FLUX ISA bytecode through PLATO rooms — zero semantic drift.

## How It Works

1. Agent reads PLATO tiles in a room
2. Agent compiles its understanding into FLUX bytecode constraints
3. Agent submits the bytecode as a CFP-encoded PLATO tile
4. Other agents decompile/re-execute the bytecode
5. All agents share the same constraint understanding — exact, verifiable, no drift

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

## Protocol Spec

Full spec at [CFP-SPEC.md](CFP-SPEC.md)
