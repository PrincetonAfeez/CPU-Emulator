"""Unit tests for the CFG module."""

from chip8.cfg import build_cfg

def test_format_report_lists_unresolved_edges() -> None:
    graph = build_cfg(bytes.fromhex("1206 0000 B300 00EE"))
    report = graph.format_report()
    assert "Unresolved edges:" in report
    assert "dynamic RET" in report
    assert "Adjacency:" in report


def test_call_target_outside_rom_is_unresolved() -> None:
    graph = build_cfg(bytes.fromhex("2206 6001"))
    assert graph.unresolved[0x200] == "call target 0x206 outside ROM image"
    assert 0x206 in graph.call_targets


def test_reachable_from_custom_start() -> None:
    rom = bytes.fromhex("6001 1200")
    graph = build_cfg(rom)
    assert graph.reachable(start=0x202) == {0x200, 0x202}


def test_reachable_skips_unknown_addresses() -> None:
    graph = build_cfg(bytes.fromhex("1200"))
    assert graph.reachable(start=0x500) == set()


def test_format_report_shows_none_for_empty_sets() -> None:
    graph = build_cfg(bytes.fromhex("6001"))
    report = graph.format_report()
    assert "Direct jump targets: none" in report
    assert "Call targets: none" in report


def test_fx0a_adds_fallthrough_edge_when_present() -> None:
    graph = build_cfg(bytes.fromhex("F00A 6001"))
    assert 0x202 in graph.edges[0x200]
