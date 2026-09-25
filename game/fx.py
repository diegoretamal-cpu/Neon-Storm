"""Sistema de efectos: partículas, ondas de choque, textos flotantes y cámara.

Todo se dibuja en dos superficies: la principal (nítida) y una pequeña
"glow" que luego se escala y se suma en aditivo para conseguir el bloom.
"""

from __future__ import annotations

import math
import random

import pygame

from . import config as C
from .render import blend_text
from .utils import (
    TAU,
    Color,
    RGBA,
    clamp,
    ease_out_cubic,
    lerp,
    mix_color,
    pick,
    rand_range,
    safe_normalize,
    scale_color,
    with_alpha,
)

GLOW_W = C.LOGICAL_W // C.GLOW_DIV
GLOW_H = C.LOGICAL_H // C.GLOW_DIV


def grect(rect: pygame.Rect) -> pygame.Rect:
    """Convierte un rect en coordenadas lógicas al buffer de bloom."""
    d = C.GLOW_DIV
    return pygame.Rect(rect.x // d, rect.y // d, max(1, rect.width // d), max(1, rect.height // d))


# --- Bloom -------------------------------------------------------------------
def glow_dot(
    glow: pygame.Surface,
    pos: tuple[float, float] | pygame.Vector2,
    radius: float,
    color: Color,
    intensity: float = 1.0,
) -> None:
    """Pinta un halo suave en el buffer de bloom (radio en px lógicos)."""
    if radius <= 0 or intensity <= 0.02:
        return
    gx = int(pos[0] / C.GLOW_DIV)
    gy = int(pos[1] / C.GLOW_DIV)
    if -8 <= gx <= GLOW_W + 8 and -8 <= gy <= GLOW_H + 8:
        core = max(1, int(radius / C.GLOW_DIV))
        halo = max(1, int(radius * 1.75 / C.GLOW_DIV))
        if halo > core:
            pygame.draw.circle(
                glow, scale_color(color, 0.20 * intensity), (gx, gy), halo
            )
        pygame.draw.circle(glow, scale_color(color, 0.62 * intensity), (gx, gy), core)


def glow_line(
    glow: pygame.Surface,
    a: tuple[float, float],
    b: tuple[float, float],
    color: Color,
    width: float,
    intensity: float = 1.0,
) -> None:
    p1 = (int(a[0] / C.GLOW_DIV), int(a[1] / C.GLOW_DIV))
    p2 = (int(b[0] / C.GLOW_DIV), int(b[1] / C.GLOW_DIV))
    w = max(1, int(width / C.GLOW_DIV))
    pygame.draw.line(glow, scale_color(color, 0.7 * intensity), p1, p2, w)


def glow_poly(
    glow: pygame.Surface,
    points: list[tuple[int, int]],
    color: Color,
    width: float = 3.0,
    intensity: float = 1.0,
) -> None:
    scaled = [(int(x / C.GLOW_DIV), int(y / C.GLOW_DIV)) for x, y in points]
    w = max(1, int(width / C.GLOW_DIV))
    try:
        pygame.draw.polygon(glow, scale_color(color, 0.8 * intensity), scaled, w)
    except ValueError:
        pass


# --- Partículas --------------------------------------------------------------
class Particle:
    __slots__ = (
        "x", "y", "vx", "vy", "ttl", "life", "size", "color", "drag",
        "kind", "glow", "rot", "spin", "grav",
    )

    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        ttl: float,
        size: float,
        color: Color,
        *,
        drag: float = 0.90,
        kind: str = "dot",
        glow: float = 0.0,
        rot: float = 0.0,
        spin: float = 0.0,
        grav: float = 0.0,
    ) -> None:
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.ttl = self.life = ttl
        self.size = size
        self.color = color
        self.drag = drag
        self.kind = kind
        self.glow = glow
        self.rot = rot
        self.spin = spin
        self.grav = grav

    @property
    def pos(self) -> pygame.Vector2:
        return pygame.Vector2(self.x, self.y)

    def update(self, dt: float) -> None:
        self.life -= dt
        decay = self.drag ** (dt * 60.0)
        self.vx *= decay
        self.vy *= decay
        self.vy += self.grav * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rot += self.spin * dt

    def draw(self, surf: pygame.Surface, glow: pygame.Surface) -> None:
        t = self.life / self.ttl if self.ttl > 0 else 0.0
        if t <= 0.0:
            return
        col = self.color
        kind = self.kind

        if kind == "spark":
            tail = 0.022
            x2 = self.x - self.vx * tail
            y2 = self.y - self.vy * tail
            fade = int(255 * ease_out_cubic(t))
            hot = mix_color(col, C.WHITE, 1.0 - t)
            w = max(1, int(self.size * (0.4 + t * 0.9)))
            pygame.draw.line(surf, with_alpha(hot, fade),
                             (int(self.x), int(self.y)), (int(x2), int(y2)), w)
            if self.glow:
                glow_line(glow, (self.x, self.y), (x2, y2), col, 6, self.glow * t)
            return

        if kind == "smoke":
            # Anillos concéntricos con caída suave: un solo círculo se ve
            # como un disco duro sobre el fondo oscuro.
            growth = 1.0 + (1.0 - t) * 1.9
            r = self.size * growth
            a = int(78 * t * t)
            for k in range(5):
                f = k / 4.0
                rr = r * (1.0 - f * 0.8)
                if rr < 1:
                    continue
                pygame.draw.circle(
                    surf, with_alpha(col, int(a * (1.0 - f) ** 1.4)),
                    (int(self.x), int(self.y)), int(rr),
                )
            return

        if kind == "shard":
            s = self.size * (0.35 + t * 0.65)
            c, sn = math.cos(self.rot), math.sin(self.rot)
            pts = []
            for dx, dy in ((0, -s), (s * 0.62, s * 0.8), (-s * 0.62, s * 0.8)):
                pts.append((int(self.x + dx * c - dy * sn),
                            int(self.y + dx * sn + dy * c)))
            pygame.draw.polygon(surf, with_alpha(col, int(255 * t)), pts)
            return

        if kind == "flash":
            a = int(255 * t * t)
            r = self.size * (1.6 - t * 0.6)
            pygame.draw.circle(surf, with_alpha(col, a), (int(self.x), int(self.y)), int(r))
            glow_dot(glow, (self.x, self.y), r * 2.4, col, t)
            return

        # kind == "dot"
        a = int(255 * clamp(t * 1.4, 0, 1))
        r = max(1, int(self.size * (0.4 + t * 0.6)))
        pygame.draw.circle(surf, with_alpha(col, a), (int(self.x), int(self.y)), r)
        if self.glow:
            glow_dot(glow, (self.x, self.y), self.size * 2.6, col, self.glow * t)


class Particles:
    """Pool simple de partículas (no usa pymunk ni nada externo)."""

    def __init__(self, limit: int = 1600) -> None:
        self.items: list[Particle] = []
        self.limit = limit

    def clear(self) -> None:
        self.items.clear()

    def add(self, p: Particle) -> None:
        if len(self.items) >= self.limit:
            # Reemplaza la más vieja para no perder el efecto nuevo.
            self.items.pop(0)
        self.items.append(p)

    def update(self, dt: float) -> None:
        alive: list[Particle] = []
        for p in self.items:
            p.update(dt)
            if p.life > 0.0:
                alive.append(p)
        self.items = alive

    def draw(self, surf: pygame.Surface, glow: pygame.Surface) -> None:
        for p in self.items:
            p.draw(surf, glow)

    # -- emisores -------------------------------------------------------------
    def burst(
        self,
        pos,
        count: int,
        color: Color,
        *,
        speed: tuple[float, float] = (90.0, 320.0),
        size: tuple[float, float] = (2.0, 4.0),
        ttl: tuple[float, float] = (0.25, 0.6),
        drag: float = 0.90,
        kind: str = "dot",
        glow: float = 0.0,
        direction: float | None = None,
        cone: float = TAU,
    ) -> None:
        px, py = pos[0], pos[1]
        for _ in range(count):
            ang = (rand_range(0.0, TAU) if direction is None
                   else direction + rand_range(-cone / 2, cone / 2))
            sp = rand_range(*speed)
            self.add(
                Particle(
                    px, py,
                    math.cos(ang) * sp, math.sin(ang) * sp,
                    rand_range(*ttl), rand_range(*size), color,
                    drag=drag, kind=kind, glow=glow,
                    rot=ang, spin=rand_range(-9, 9),
                )
            )

    def sparks(
        self,
        pos: pygame.Vector2,
        count: int,
        color: Color,
        *,
        speed: tuple[float, float] = (200.0, 620.0),
        direction: float | None = None,
        cone: float = TAU,
    ) -> None:
        self.burst(
            pos, count, color, speed=speed, size=(1.5, 3.0),
            ttl=(0.18, 0.42), drag=0.86, kind="spark",
            glow=0.9, direction=direction, cone=cone,
        )

    def smoke(self, pos, count: int, color: Color = (70, 50, 100),
              scale: float = 1.0) -> None:
        px, py = pos[0], pos[1]
        # El tamaño del humo tiene tope: si no, una explosión grande pinta
        # un manchurrón del tamaño de media pantalla.
        base = min(9.0 * scale, 15.0)
        for _ in range(count):
            self.add(
                Particle(
                    px + rand_range(-8, 8), py + rand_range(-8, 8),
                    rand_range(-40, 40), rand_range(-60, -10),
                    rand_range(0.35, 0.7), rand_range(4.0, base), color,
                    drag=0.94, kind="smoke",
                )
            )

    def debris(
        self,
        pos,
        count: int,
        color: Color,
        *,
        speed: tuple[float, float] = (120.0, 420.0),
    ) -> None:
        px, py = pos[0], pos[1]
        for _ in range(count):
            ang = rand_range(0.0, TAU)
            sp = rand_range(*speed)
            self.add(
                Particle(
                    px, py,
                    math.cos(ang) * sp, math.sin(ang) * sp,
                    rand_range(0.4, 0.9), rand_range(3.0, 6.0), color,
                    drag=0.93, kind="shard", rot=ang, spin=rand_range(-14, 14),
                )
            )

    def flash(self, pos, color: Color, size: float = 26.0) -> None:
        self.add(Particle(pos[0], pos[1], 0, 0, 0.16, size, color, kind="flash"))


# --- Ondas de choque --------------------------------------------------------
class Ring:
    __slots__ = ("x", "y", "r0", "r1", "ttl", "life", "color", "width", "glow")

    def __init__(
        self, x: float, y: float, r0: float, r1: float, ttl: float,
        color: Color, width: float = 3.0, glow: float = 1.0,
    ) -> None:
        self.x, self.y = x, y
        self.r0, self.r1 = r0, r1
        self.ttl = self.life = ttl
        self.color = color
        self.width = width
        self.glow = glow

    def update(self, dt: float) -> None:
        self.life -= dt

    def draw(self, surf: pygame.Surface, glow: pygame.Surface) -> None:
        t = 1.0 - clamp(self.life / self.ttl, 0.0, 1.0)
        r = lerp(self.r0, self.r1, ease_out_cubic(t))
        a = int(255 * (1.0 - t) ** 1.6)
        if a <= 2 or r < 1:
            return
        pos = (int(self.x), int(self.y))
        pygame.draw.circle(surf, with_alpha(self.color, a), pos, int(r),
                           max(1, int(self.width * (1.0 - t * 0.6))))
        glow_dot(glow, (self.x, self.y), r * 1.1, self.color, (1.0 - t) * self.glow)


# --- Textos flotantes --------------------------------------------------------
class Floater:
    __slots__ = ("x", "y", "vy", "text", "color", "ttl", "life", "size")

    def __init__(self, x, y, text, color, ttl=0.8, size=18, vy=-90.0):
        self.x, self.y = x, y
        self.vy = vy
        self.text = text
        self.color = color
        self.ttl = self.life = ttl
        self.size = size

    def update(self, dt: float) -> None:
        self.life -= dt
        self.y += self.vy * dt
        self.vy *= 0.90 ** (dt * 60)

    def draw(self, surf, fonts, glow) -> None:
        t = clamp(self.life / self.ttl, 0.0, 1.0)
        font = fonts.get(self.size) or next(iter(fonts.values()))
        a = int(255 * ease_out_cubic(t))
        blend_text(surf, font, self.text, self.color, (self.x, self.y),
                   align="midbottom", alpha=a, shadow=True)
        glow_dot(glow, (self.x, self.y - 8), font.get_width(self.text) * 0.5,
                 self.color, 0.35 * t)


# --- Cámara -----------------------------------------------------------------
class Shake:
    """Sacudida de cámara con decaimiento exponencial."""

    def __init__(self) -> None:
        self.amount = 0.0
        self.x = 0.0
        self.y = 0.0
        self._t = 0.0

    def add(self, amount: float) -> None:
        self.amount = min(self.amount + amount, 34.0)

    def update(self, dt: float) -> None:
        self._t += dt
        self.amount = max(0.0, self.amount - self.amount * 7.0 * dt - 4.0 * dt)
        if self.amount > 0.05:
            a = rand_range(0.0, TAU)
            self.x = math.cos(a) * self.amount
            self.y = math.sin(a) * self.amount
        else:
            self.x = self.y = 0.0


# --- Contenedor -------------------------------------------------------------
class FX:
    def __init__(self) -> None:
        self.particles = Particles()
        self.rings: list[Ring] = []
        self.floaters: list[Floater] = []
        self.shake = Shake()
        self.hitstop = 0.0
        self.flash = 0.0
        self.flash_color: Color = C.WHITE
        self.vignette_pulse = 0.0

    def clear(self) -> None:
        self.particles.clear()
        self.rings.clear()
        self.floaters.clear()
        self.shake.amount = 0.0
        self.hitstop = 0.0
        self.flash = 0.0

    # -- creations ------------------------------------------------------------
    def ring(self, x, y, r0, r1, ttl, color, width=3.0, glow=1.0) -> None:
        self.rings.append(Ring(x, y, r0, r1, ttl, color, width, glow))

    def text(self, x, y, text, color=C.WHITE, ttl=0.8, size=18) -> None:
        self.floaters.append(Floater(x, y, text, color, ttl, size))

    def boom(
        self,
        pos: pygame.Vector2,
        color: Color,
        scale: float = 1.0,
        *,
        sparks: int = 18,
        debris: int = 8,
        smoke: int = 5,
        sound: str | None = None,
        screen: bool = True,
    ) -> None:
        self.particles.flash(pos, color, 30.0 * scale)
        self.particles.burst(
            pos, int(sparks * scale), color,
            speed=(70 * scale, 380 * scale), size=(2, 5),
            ttl=(0.22, 0.55), glow=0.9,
        )
        self.particles.sparks(pos, int(sparks * 0.8 * scale), C.GOLD, speed=(260, 720 * scale))
        self.particles.debris(pos, int(debris * scale), scale_color(color, 0.8),
                              speed=(110 * scale, 400 * scale))
        if smoke:
            # El humo toma el tinte de la explosión: si no, sobre un fondo
            # oscuro parece un agujero en vez de una nube.
            self.particles.smoke(pos, int(smoke * scale), scale_color(color, 0.45), scale)
        self.ring(pos.x, pos.y, 6 * scale, 74 * scale, 0.36, color, 4.0 * scale)
        self.ring(pos.x, pos.y, 2 * scale, 42 * scale, 0.22, C.WHITE, 2.0)
        if screen:
            self.shake.add(5.0 * scale)
        self.flash = max(self.flash, 0.10 * min(scale, 1.6))
        self.flash_color = color

    # -- update / draw --------------------------------------------------------
    def update(self, dt: float) -> None:
        self.particles.update(dt)
        for r in self.rings:
            r.update(dt)
        self.rings = [r for r in self.rings if r.life > 0]
        for f in self.floaters:
            f.update(dt)
        self.floaters = [f for f in self.floaters if f.life > 0]
        self.shake.update(dt)
        self.flash = max(0.0, self.flash - dt * 2.6)
        self.vignette_pulse = max(0.0, self.vignette_pulse - dt * 2.0)

    def draw_world(self, surf: pygame.Surface, glow: pygame.Surface, fonts: dict) -> None:
        for r in self.rings:
            r.draw(surf, glow)
        self.particles.draw(surf, glow)
        for f in self.floaters:
            f.draw(surf, fonts, glow)
