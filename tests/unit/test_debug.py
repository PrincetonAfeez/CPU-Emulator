"""Unit tests for the Debug module."""

from chip8.debug import changed_fields, format_transition
from chip8.opcode import decode


def test_changed_fields_empty_when_identical() -> None:
    state = {"pc": 0x200, "v": [0] * 16}
    assert changed_fields(state, dict(state)) == {}


def test_changed_fields_only_compares_shared_keys() -> None:
    before: dict[str, object] = {"pc": 0x200, "cycles": 0}
    after: dict[str, object] = {"pc": 0x202, "cycles": 1}
    changes = changed_fields(before, after)
    assert set(changes) == {"pc", "cycles"}


def test_format_transition_reports_no_state_change() -> None:
    state: dict[str, object] = {
        "pc": 0x200,
        "v": [0] * 16,
        "i": 0,
        "cycles": 0,
        "awaiting_key": False,
    }
    text = format_transition(0x200, decode(0x1200), state, dict(state))
    assert "no state change" in text
    assert "1200" in text


def test_format_transition_lists_multiple_changes() -> None:
    before: dict[str, object] = {"pc": 0x200, "i": 0}
    after: dict[str, object] = {"pc": 0x202, "i": 0x300}
    text = format_transition(0x200, decode(0xA300), before, after)
    assert "pc:" in text
    assert "i:" in text
