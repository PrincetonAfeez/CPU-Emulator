"""Unit tests for the Quirks module."""

import pytest

from chip8.quirks import PROFILES, QuirkProfile, get_quirks


def test_modern_profile_values() -> None:
    profile = get_quirks("modern")
    assert profile.name == "modern"
    assert profile.shift_uses_vy is False
    assert profile.load_store_increment_i is False
    assert profile.draw_wrap is False
    assert profile.logic_resets_flag is False


def test_classic_profile_values() -> None:
    profile = get_quirks("classic")
    assert profile.name == "classic"
    assert profile.shift_uses_vy is True
    assert profile.load_store_increment_i is True
    assert profile.draw_wrap is True
    assert profile.logic_resets_flag is True


def test_describe_returns_dict() -> None:
    described = get_quirks("modern").describe()
    assert described["name"] == "modern"
    assert set(described) == {
        "name",
        "shift_uses_vy",
        "load_store_increment_i",
        "draw_wrap",
        "logic_resets_flag",
    }


def test_profiles_contains_both_names() -> None:
    assert set(PROFILES) == {"classic", "modern"}
    assert all(isinstance(profile, QuirkProfile) for profile in PROFILES.values())


def test_unknown_profile_raises() -> None:
    with pytest.raises(ValueError, match="unknown quirk profile"):
        get_quirks("superchip")
