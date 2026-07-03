"""CHIP-8 emulator package."""

from .cpu import CPU
from .machine import Machine
from .quirks import QuirkProfile, get_quirks

__all__ = ["CPU", "Machine", "QuirkProfile", "get_quirks"]
__version__ = "1.0.2"

