"""Unit tests for the Keyboard module."""

import os
import sys

import pytest

from chip8.errors import InputUnavailableError, InvalidKeyError
from chip8.keyboard import Keypad, TerminalKeypad


def test_terminal_keypad_requires_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    keypad = TerminalKeypad()
    with pytest.raises(InputUnavailableError, match="requires a terminal"), keypad:
        pass


def test_terminal_keypad_poll_raises_on_ctrl_c(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "name", "posix")
    stream = _FakeStream("\x03")
    ready = {"once": True}

    def fake_select(
        readers: list[object], *_: object
    ) -> tuple[list[object], list[object], list[object]]:
        if ready["once"]:
            ready["once"] = False
            return (readers, [], [])
        return ([], [], [])

    monkeypatch.setattr("select.select", fake_select)
    keypad = TerminalKeypad()
    with pytest.raises(KeyboardInterrupt):
        keypad.poll(stream=stream)  # type: ignore[arg-type]


def test_terminal_keypad_poll_raises_on_ctrl_c_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready = {"once": True}

    def kbhit() -> bool:
        if ready["once"]:
            ready["once"] = False
            return True
        return False

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr("msvcrt.kbhit", kbhit)
    monkeypatch.setattr("msvcrt.getwch", lambda: "\x03")
    keypad = TerminalKeypad()
    with pytest.raises(KeyboardInterrupt):
        keypad.poll()


def test_release_rejects_invalid_key() -> None:
    keypad = Keypad()
    with pytest.raises(InvalidKeyError):
        keypad.release(0x20)


def test_keypad_press_release_and_edge_queue() -> None:
    keypad = Keypad()
    keypad.press(0x5)
    assert keypad.is_pressed(0x5)
    keypad.release(0x5)
    assert not keypad.is_pressed(0x5)
    assert keypad.next_key_press() == 0x5
    assert keypad.next_key_press() is None


def test_begin_wait_clears_buffered_edges() -> None:
    keypad = Keypad()
    keypad.press(0x1)
    keypad.release(0x1)
    keypad.begin_wait()
    assert keypad.next_key_press() is None


def test_reset_clears_pressed_and_buffered_keys() -> None:
    keypad = Keypad()
    keypad.press(0x2)
    keypad.release(0x2)
    keypad.reset()
    assert not keypad.is_pressed(0x2)
    assert keypad.next_key_press() is None


def test_terminal_keypad_maps_host_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "name", "posix")
    stream = _FakeStream("1")
    ready = {"once": True}

    def fake_select(
        readers: list[object], *_: object
    ) -> tuple[list[object], list[object], list[object]]:
        if ready["once"]:
            ready["once"] = False
            return (readers, [], [])
        return ([], [], [])

    monkeypatch.setattr("select.select", fake_select)
    keypad = TerminalKeypad(hold_seconds=10.0)
    keypad.poll(stream=stream)  # type: ignore[arg-type]
    assert keypad.is_pressed(0x1)


def test_terminal_keypad_auto_releases_after_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "name", "posix")
    times = iter([0.0, 0.2])
    monkeypatch.setattr("chip8.keyboard.time.monotonic", lambda: next(times))
    stream = _FakeStream("x")
    ready = {"once": True}

    def fake_select(
        readers: list[object], *_: object
    ) -> tuple[list[object], list[object], list[object]]:
        if ready["once"]:
            ready["once"] = False
            return (readers, [], [])
        return ([], [], [])

    monkeypatch.setattr("select.select", fake_select)
    keypad = TerminalKeypad(hold_seconds=0.1)
    keypad.poll(stream=stream)  # type: ignore[arg-type]
    assert keypad.is_pressed(0x0)
    keypad.poll(stream=stream)  # type: ignore[arg-type]
    assert not keypad.is_pressed(0x0)
    assert keypad.next_key_press() == 0x0


def test_terminal_keypad_sets_cbreak_on_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdin, "fileno", lambda: 0)
    calls: list[str] = []

    class FakeTermios:
        TCSADRAIN = 1

        @staticmethod
        def tcgetattr(_: object) -> list[int]:
            calls.append("get")
            return [0]

        @staticmethod
        def tcsetattr(_: object, _when: int, _attrs: object) -> None:
            calls.append("set")

    class FakeTty:
        @staticmethod
        def setcbreak(_: int) -> None:
            calls.append("cbreak")

    monkeypatch.setitem(sys.modules, "termios", FakeTermios())
    monkeypatch.setitem(sys.modules, "tty", FakeTty())
    keypad = TerminalKeypad()
    with keypad:
        assert calls == ["get", "cbreak"]
    assert calls[-1] == "set"


class _FakeStream:
    def __init__(self, data: str) -> None:
        self._data = data

    def fileno(self) -> int:
        return 0

    def read(self, _: int) -> str:
        return self._data
