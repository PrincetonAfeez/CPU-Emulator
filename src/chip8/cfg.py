"""Static control-flow graph built from a ROM's linear disassembly.

Structured return types are documented in docs/output-formats.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .disasm import Instruction, disassemble


@dataclass(slots=True)
class CFG:
    nodes: dict[int, Instruction]
    edges: dict[int, set[int]] = field(default_factory=dict)
    unresolved: dict[int, str] = field(default_factory=dict)
    jump_targets: set[int] = field(default_factory=set)
    call_targets: set[int] = field(default_factory=set)
    malformed: set[int] = field(default_factory=set)

    def reachable(self, start: int = 0x200) -> set[int]:
        seen: set[int] = set()
        stack = [start]
        while stack:
            address = stack.pop()
            if address in seen or address not in self.nodes:
                continue
            seen.add(address)
            stack.extend(self.edges.get(address, ()))
        return seen

    def format_report(self) -> str:
        reachable = self.reachable()
        dead = set(self.nodes) - reachable
        lines = [
            f"Instruction nodes: {len(self.nodes)}",
            f"Reachable from 0x200: {len(reachable)}",
            "Direct jump targets: " + _addresses(self.jump_targets),
            "Call targets: " + _addresses(self.call_targets),
            "Possible dead/unreachable code: " + _addresses(dead),
            "Malformed/unknown opcodes: " + _addresses(self.malformed),
        ]
        if self.unresolved:
            lines.append(
                "Unresolved edges: "
                + ", ".join(
                    f"0x{address:03X} ({reason})"
                    for address, reason in self.unresolved.items()
                )
            )
        lines.append("Adjacency:")
        for address in sorted(self.nodes):
            targets = ", ".join(
                f"0x{target:03X}" for target in sorted(self.edges.get(address, set()))
            )
            lines.append(f"  0x{address:03X} -> {targets or '[exit/unresolved]'}")
        return "\n".join(lines)


def _addresses(values: set[int]) -> str:
    return ", ".join(f"0x{value:03X}" for value in sorted(values)) or "none"


def build_cfg(rom: bytes) -> CFG:
    instructions = disassemble(rom)
    nodes = {instruction.address: instruction for instruction in instructions}
    graph = CFG(nodes=nodes)
    for instruction in instructions:
        address = instruction.address
        op = instruction.opcode
        next_address = address + 2
        graph.edges[address] = set()
        if not op.is_known:
            graph.malformed.add(address)
            continue
        if op.value == 0x00EE:
            graph.unresolved[address] = "dynamic RET"
            continue
        if op.high == 0x1:
            graph.edges[address].add(op.nnn)
            graph.jump_targets.add(op.nnn)
            if op.nnn not in nodes:
                graph.unresolved[address] = f"jump target 0x{op.nnn:03X} outside ROM image"
        elif op.high == 0x2:
            graph.edges[address].update((op.nnn, next_address))
            graph.call_targets.add(op.nnn)
            if op.nnn not in nodes:
                graph.unresolved[address] = f"call target 0x{op.nnn:03X} outside ROM image"
        elif op.high in (0x3, 0x4, 0x5, 0x9) or (
            op.high == 0xE and op.nn in (0x9E, 0xA1)
        ):
            graph.edges[address].update((next_address, next_address + 2))
            off_rom = [
                target
                for target in (next_address, next_address + 2)
                if target not in nodes
            ]
            if off_rom:
                targets = ", ".join(f"0x{target:03X}" for target in off_rom)
                graph.unresolved[address] = f"skip targets {targets} outside ROM image"
        elif op.high == 0xB:
            graph.unresolved[address] = "dynamic BNNN jump"
        elif op.high == 0xF and op.nn == 0x0A:
            graph.unresolved[address] = "blocking FX0A key wait"
            if next_address in nodes:
                graph.edges[address].add(next_address)
        elif next_address in nodes:
            graph.edges[address].add(next_address)
    return graph
