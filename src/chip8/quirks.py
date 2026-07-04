"""Historical CHIP-8 behavior choices, grouped into selectable profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class QuirkProfile:
    """Historical behavior choices that differ between CHIP-8 interpreters."""

    name: str
    shift_uses_vy: bool
    load_store_increment_i: bool
    draw_wrap: bool
    logic_resets_flag: bool

    def describe(self) -> dict[str, object]:
        return asdict(self)


PROFILES = {
    "classic": QuirkProfile(
        name="classic",
        shift_uses_vy=True,
        load_store_increment_i=True,
        draw_wrap=True,
        logic_resets_flag=True,
    ),
    "modern": QuirkProfile(
        name="modern",
        shift_uses_vy=False,
        load_store_increment_i=False,
        draw_wrap=False,
        logic_resets_flag=False,
    ),
}


def get_quirks(name: str) -> QuirkProfile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        choices = ", ".join(sorted(PROFILES))
        raise ValueError(f"unknown quirk profile {name!r}; choose from: {choices}") from exc

