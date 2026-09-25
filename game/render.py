"""Infraestructura de render: capas con alfa por píxel y texto con fundido.

Pygame ignora el canal alfa de los colores en superficies *sin* `SRCALPHA`,
y `set_alpha()` no hace nada en superficies *con* alfa por píxel. Por eso todo
lo translúcido se dibuja en estas capas y se compone una sola vez por frame.
"""

from __future__ import annotations

import pygame

from .utils import Color, clamp

# --- Capas ------------------------------------------------------------------
class Layers:
    """Tres superficies SRCALPHA reutilizadas (sin reasignar cada frame)."""

    __slots__ = ("w", "h", "back", "mid", "hud")

    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.back = pygame.Surface((w, h), pygame.SRCALPHA).convert_alpha()
        self.mid = pygame.Surface((w, h), pygame.SRCALPHA).convert_alpha()
        self.hud = pygame.Surface((w, h), pygame.SRCALPHA).convert_alpha()

    def clear(self) -> None:
        self.back.fill((0, 0, 0, 0))
        self.mid.fill((0, 0, 0, 0))
        self.hud.fill((0, 0, 0, 0))

    def present(self, canvas: pygame.Surface) -> None:
        canvas.blit(self.back, (0, 0))
        canvas.blit(self.mid, (0, 0))
        canvas.blit(self.hud, (0, 0))


# --- Fundido de imágenes (alfa real por píxel) -------------------------------
_SCRATCH: pygame.Surface | None = None


def _scratch(w: int, h: int) -> pygame.Surface:
    global _SCRATCH
    if _SCRATCH is None or _SCRATCH.get_width() < w or _SCRATCH.get_height() < h:
        _SCRATCH = pygame.Surface((max(w, 1024), max(h, 160)), pygame.SRCALPHA)
    return _SCRATCH


def dim(img: pygame.Surface, factor: float, tint: Color = (255, 255, 255)) -> pygame.Surface:
    """Devuelve `img` con el RGB multiplicado (alfa por píxel intacto).

    El resultado es una vista del buffer de trabajo: consúmelo antes de volver
    a llamar a `dim`, o el blit fallará por superbloqueo.
    """
    factor = clamp(factor, 0.0, 1.0)
    if factor >= 0.999 and tint == (255, 255, 255):
        return img
    if img.get_parent() is not None:  # evita realimentar el mismo buffer
        img = img.copy()
    w, h = img.get_size()
    area = pygame.Rect(0, 0, w, h)
    s = _scratch(w, h)
    s.fill((0, 0, 0, 0), area)
    s.blit(img, (0, 0))
    c = (int(clamp(tint[0] * factor, 0, 255)),
         int(clamp(tint[1] * factor, 0, 255)),
         int(clamp(tint[2] * factor, 0, 255)))
    s.fill((c[0], c[1], c[2], 255), area, special_flags=pygame.BLEND_RGBA_MULT)
    return s.subsurface(area)


def place(img: pygame.Surface, pos, align: str = "center") -> pygame.Rect:
    r = img.get_rect()
    if align == "center":
        r.center = (int(pos[0]), int(pos[1]))
    elif align == "topleft":
        r.topleft = (int(pos[0]), int(pos[1]))
    elif align == "topright":
        r.topright = (int(pos[0]), int(pos[1]))
    elif align == "midleft":
        r.midleft = (int(pos[0]), int(pos[1]))
    elif align == "midright":
        r.midright = (int(pos[0]), int(pos[1]))
    elif align == "bottomleft":
        r.bottomleft = (int(pos[0]), int(pos[1]))
    elif align == "bottomright":
        r.bottomright = (int(pos[0]), int(pos[1]))
    return r


# --- Fundido de rectángulos (mezcla real, sin crear superficies) -----------
_TINT: pygame.Surface | None = None


def tint(target: pygame.Surface, color: Color, alpha: int, area: pygame.Rect | None = None) -> None:
    """Cubre `target` con un color translúcido usando un buffer reutilizado."""
    global _TINT
    w = target.get_width() if area is None else area.width
    h = target.get_height() if area is None else area.height
    if _TINT is None or _TINT.get_width() < w or _TINT.get_height() < h:
        _TINT = pygame.Surface((max(w, 512), max(h, 512)), pygame.SRCALPHA)
    if alpha <= 0:
        return
    box = pygame.Rect(0, 0, w, h)
    _TINT.fill((0, 0, 0, 0), box)
    _TINT.fill((int(color[0]), int(color[1]), int(color[2]), int(clamp(alpha, 0, 255))), box)
    target.blit(_TINT, (area.x, area.y) if area else (0, 0))


# --- Texto ------------------------------------------------------------------
SHADOW_COLOR = (26, 20, 54)


def blend_text(
    target: pygame.Surface,
    font,
    txt: str,
    color: Color,
    pos,
    *,
    align: str = "center",
    alpha: int = 255,
    shadow: bool = True,
) -> pygame.Rect:
    """Escribe texto respetando el alfa (fundido real, no set_alpha)."""
    img = font.render(txt, True, color)
    rect = place(img, pos, align)
    # El buffer de trabajo se reutiliza: la sombra se compone antes que el texto.
    if shadow:
        target.blit(dim(img, 1.0, SHADOW_COLOR), (rect.x + 2, rect.y + 3))
    if alpha < 255:
        img = dim(img, alpha / 255.0)
    target.blit(img, rect)
    return rect
