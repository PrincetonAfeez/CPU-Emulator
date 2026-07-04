"""64x32 monochrome framebuffer and its terminal half-block renderer."""

from __future__ import annotations

from dataclasses import dataclass, field

WIDTH = 64
HEIGHT = 32


@dataclass(slots=True)
class FrameBuffer:
    """Headless framebuffer; terminal rendering is just a view of this state."""

    pixels: list[list[int]] = field(
        default_factory=lambda: [[0 for _ in range(WIDTH)] for _ in range(HEIGHT)]
    )
    dirty: bool = True

    def clear(self) -> None:
        for row in self.pixels:
            row[:] = [0] * WIDTH
        self.dirty = True

    def draw_sprite(self, x: int, y: int, sprite: bytes, *, wrap: bool) -> bool:
        collision = False
        # The draw origin always reduces modulo the screen, even in clip mode;
        # only the sprite body past that origin clips (or wraps) at the edges.
        x %= WIDTH
        y %= HEIGHT
        for row_offset, sprite_byte in enumerate(sprite):
            py = y + row_offset
            if wrap:
                py %= HEIGHT
            elif py >= HEIGHT:
                continue
            for bit in range(8):
                if not sprite_byte & (0x80 >> bit):
                    continue
                px = x + bit
                if wrap:
                    px %= WIDTH
                elif px >= WIDTH:
                    continue
                if self.pixels[py][px]:
                    collision = True
                self.pixels[py][px] ^= 1
        self.dirty = True
        return collision

    def render(self) -> str:
        """Pack two CHIP-8 rows into one terminal row with half-block glyphs.

        The index is ``(top << 1) | bottom``: a lit top pixel must show the
        UPPER half block (▀) and a lit bottom pixel the LOWER half block (▄).
        """
        lines: list[str] = []
        for y in range(0, HEIGHT, 2):
            chars = []
            for x in range(WIDTH):
                top = self.pixels[y][x]
                bottom = self.pixels[y + 1][x]
                chars.append((" ", "▄", "▀", "█")[(top << 1) | bottom])
            lines.append("".join(chars))
        self.dirty = False
        return "\n".join(lines)

    def lit_pixels(self) -> int:
        return sum(sum(row) for row in self.pixels)

