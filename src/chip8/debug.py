"""Step-debug helpers: diff CPU snapshots and format instruction transitions."""

from __future__ import annotations

from .opcode import Opcode


def changed_fields(
    before: dict[str, object], after: dict[str, object]
) -> dict[str, dict[str, object]]:
    return {
        key: {"before": before[key], "after": after[key]}
        for key in before.keys() & after.keys()
        if before[key] != after[key]
    }


def format_transition(
    address: int,
    opcode: Opcode,
    before: dict[str, object],
    after: dict[str, object],
) -> str:
    changes = changed_fields(before, after)
    rendered = ", ".join(
        f"{key}: {value['before']} -> {value['after']}"
        for key, value in changes.items()
    )
    summary = rendered or "no state change"
    return f"{address:03X}: {opcode.value:04X} {opcode.mnemonic()} | {summary}"
