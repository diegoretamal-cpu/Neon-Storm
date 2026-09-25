"""Definición de armas y proyectiles del jugador."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import pygame

from . import config as C
from .fx import glow_dot, glow_line
from .utils import TAU, Color, clamp, scale_color, with_alpha


@dataclass(frozen=True)
class Weapon:
    name: str
    cd: float           # segundos entre disparos
    damage: float
    speed: float
    count: int = 1
    spread: float = 0.0  # abertura total en radianes
    size: float = 4.0
    life: float = 0.8
    pierce: int = 0
    color: Color = C.CYAN
    recoil: float = 60.0
    trail: bool = True
    pierce_walls: bool = False
    sound: str = "shoot"
    scale: float = 1.0   # multiplicador de daño del overdrive


WEAPONS: dict[str, Weapon] = {
    "pulse": Weapon(
        name="PULSO", cd=0.105, damage=9.0, speed=1150.0, size=4.2,
        life=0.85, color=C.CYAN, recoil=55.0, scale=1.0,
    ),
    "abanico": Weapon(
        name="ABANICO", cd=0.29, damage=7.0, speed=980.0, count=5, spread=0.44,
        size=4.0, life=0.75, color=C.LIME, recoil=110.0, sound="shoot",
        scale=1.0,
    ),
    "rafaga": Weapon(
        name="RÁFAGA", cd=0.40, damage=6.5, speed=1300.0, count=3, spread=0.13,
        size=3.6, life=0.7, color=C.AMBER, recoil=90.0, scale=1.0,
    ),
    "riel": Weapon(
        name="RIEL", cd=0.52, damage=27.0, speed=2100.0, size=6.5, life=0.62,
        pierce=99, color=C.MAGENTA, recoil=170.0, pierce_walls=True,
        sound="shoot_rail", scale=1.0,
    ),
    "lazo": Weapon(
        name="LAZO", cd=0.235, damage=8.0, speed=820.0, count=4, spread=1.15,
        size=3.8, life=1.05, pierce=1, color=C.VIOLET, recoil=70.0,
        scale=1.0,
    ),
}

PICKUP_POOL = ("abanico", "rafaga", "riel", "lazo")


def weapon_color_override(active: str) -> Color:
    return WEAPONS[active].color


# --- Proyectil del jugador --------------------------------------------------
class PlayerBullet:
    __slots__ = ("x", "y", "vx", "vy", "radius", "damage", "life", "ttl",
                 "color", "pierce", "hits", "pierce_walls", "trail", "width")

    def __init__(self, x, y, vx, vy, weapon: Weapon, damage: float) -> None:
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.radius = weapon.size
        self.damage = damage
        self.ttl = self.life = weapon.life
        self.color = weapon.color
        self.pierce = weapon.pierce
        self.hits: set[int] = set()
        self.pierce_walls = weapon.pierce_walls
        self.trail = weapon.trail
        self.width = 2.0

    @property
    def pos(self) -> pygame.Vector2:
        return pygame.Vector2(self.x, self.y)

    def update(self, dt: float) -> None:
        self.life -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt

    def draw(self, surf: pygame.Surface, glow: pygame.Surface) -> None:
        if self.trail:
            tail = 0.016
            tx = self.x - self.vx * tail
            ty = self.y - self.vy * tail
            pygame.draw.line(
                surf, with_alpha(scale_color(self.color, 0.45), 190),
                (int(tx), int(ty)), (int(self.x), int(self.y)),
                max(1, int(self.radius * 0.9)),
            )
        pygame.draw.circle(
            surf, self.color, (int(self.x), int(self.y)), int(self.radius)
        )
        pygame.draw.circle(
            surf, C.WHITE, (int(self.x), int(self.y)),
            max(1, int(self.radius * 0.45)),
        )
        glow_dot(glow, (self.x, self.y), self.radius * 1.9, self.color, 0.8)


def fire(weapon: Weapon, pos: pygame.Vector2, angle: float, damage_mul: float = 1.0) -> list[PlayerBullet]:
    """Genera los proyectiles de un disparo en la dirección `angle`."""
    bullets: list[PlayerBullet] = []
    dmg = weapon.damage * damage_mul
    n = max(1, weapon.count)
    base = angle - weapon.spread / 2
    step = weapon.spread / (n - 1) if n > 1 else 0.0
    for i in range(n):
        a = base + step * i if n > 1 else angle
        spd = weapon.speed * random.uniform(0.97, 1.03)
        offset = random.uniform(-2.0, 2.0)
        bullets.append(
            PlayerBullet(
                pos.x + math.cos(angle) * (weapon.size + 10) + math.cos(a + 1.57) * offset,
                pos.y + math.sin(angle) * (weapon.size + 10) + math.sin(a + 1.57) * offset,
                math.cos(a) * spd,
                math.sin(a) * spd,
                weapon,
                dmg,
            )
        )
    return bullets
