"""Generación de oleadas y director de combate."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import pygame

from . import config as C
from .entities import ENEMY_CLASSES, Boss
from .utils import TAU, chance, clamp, rand_range, safe_normalize

# Coste en "presupuesto" de cada tipo de enemigo.
COST = {
    "zancudo": 1.0,
    "escupidor": 2.0,
    "orbitador": 2.5,
    "mitosis": 3.5,
    "bruto": 5.0,
}

# Oleada mínima en la que aparece cada tipo.
UNLOCK = {
    "zancudo": 1,
    "escupidor": 2,
    "orbitador": 4,
    "mitosis": 6,
    "bruto": 7,
}

NAMES = {
    "zancudo": "zancudos",
    "escupidor": "escupidores",
    "orbitador": "orbitadores",
    "mitosis": "mitosis",
    "bruto": "brutos",
}


@dataclass
class Wave:
    number: int
    is_boss: bool
    queue: list[str] = field(default_factory=list)
    hp_mul: float = 1.0
    spd_mul: float = 1.0
    interval: float = 0.8
    boss_hp_mul: float = 1.0

    @property
    def total(self) -> int:
        return len(self.queue)

    def composition(self) -> str:
        if self.is_boss:
            return "centinela"
        counts: dict[str, int] = {}
        for k in self.queue:
            counts[k] = counts.get(k, 0) + 1
        return " · ".join(f"{counts[k]} {NAMES[k]}" for k in sorted(counts))


def build_wave(n: int) -> Wave:
    is_boss = n % C.BOSS_EVERY == 0
    budget = 5.0 + n * 2.15
    queue: list[str] = []

    available = [k for k, unlock in UNLOCK.items() if n >= unlock]
    # Garantiza algo de diversity desde la oleada 2.
    weights = {
        "zancudo": 4.0 if n < 4 else 2.6,
        "escupidor": 1.2 + n * 0.06,
        "orbitador": 0.8 + n * 0.08,
        "mitosis": 0.7 + n * 0.07,
        "bruto": 0.5 + n * 0.10,
    }
    pool = list(available)

    guard = 0
    while budget >= 1.0 and guard < 200:
        guard += 1
        kind = random.choices(pool, weights=[weights[k] for k in pool])[0]
        cost = COST[kind]
        if cost > budget:
            kind = "zancudo"
            cost = COST[kind]
        queue.append(kind)
        budget -= cost

    if is_boss:
        # Los jefes llegan con escolta.
        queue = ["zancudo", "zancudo", "zancudo", "escupidor"] + queue[: max(0, len(queue) // 2)]

    random.shuffle(queue)

    return Wave(
        number=n,
        is_boss=is_boss,
        queue=queue,
        hp_mul=1.0 + (n - 1) * 0.155,
        spd_mul=min(1.55, 1.0 + (n - 1) * 0.040),
        interval=max(0.30, 0.85 - n * 0.028),
        boss_hp_mul=1.0 + (n // C.BOSS_EVERY - 1) * 0.85,
    )


def spawn_point(world, min_dist: float = 280.0) -> pygame.Vector2:
    """Elige un punto de aparición lejos del jugador y fuera de los pilares."""
    a = world.arena
    for _ in range(48):
        ang = random.uniform(0, TAU)
        rad = random.uniform(0.35, 1.0)
        p = pygame.Vector2(
            a.centerx + math.cos(ang) * a.width * 0.46 * rad,
            a.centery + math.sin(ang) * a.height * 0.46 * rad,
        )
        p.x = clamp(p.x, a.left + 40, a.right - 40)
        p.y = clamp(p.y, a.top + 40, a.bottom - 40)
        if (p - world.player.pos).length() < min_dist:
            continue
        if world.obstacle_hit(p, 44.0):
            continue
        if world.enemy_near(p.x, p.y, 46.0):
            continue
        return p
    # Fallback: borde opuesto al jugador
    d = safe_normalize(world.player.pos - pygame.Vector2(a.center))
    return pygame.Vector2(
        clamp(a.centerx - d.x * a.width * 0.4, a.left + 40, a.right - 40),
        clamp(a.centery - d.y * a.height * 0.4, a.top + 40, a.bottom - 40),
    )


class WaveRunner:
    """Máquina de estados: intro -> spawn -> combate -> limpieza."""

    def __init__(self, world) -> None:
        self.world = world
        self.wave = 0
        self.state = "idle"
        self.timer = 0.0
        self.wave_obj: Wave | None = None
        self.spawned = 0
        self.spawn_cd = 0.0
        self.intro_done = False

    # -- control --------------------------------------------------------------
    def reset(self) -> None:
        self.wave = 0
        self.state = "idle"
        self.timer = 0.0
        self.wave_obj = None
        self.spawned = 0
        self.spawn_cd = 0.0

    def start_next(self) -> None:
        self.wave += 1
        self.wave_obj = build_wave(self.wave)
        self.spawned = 0
        self.spawn_cd = 0.0
        self.state = "intro"
        self.timer = 1.9 if self.wave_obj.is_boss else 1.35
        world = self.world
        if self.wave_obj.is_boss:
            world.announce(f"OLEADA {self.wave}", C.RED, 1.2, big=True)
            world.announce("CENTINELA", C.GOLD, 2.2, delay=0.35, sub=True)
            world.audio.play("boss", 0.9)
        else:
            world.announce(f"OLEADA {self.wave}", C.CYAN, 1.0, big=True)
            world.announce(self.wave_obj.composition(), C.ICE, 1.6, delay=0.18, sub=True)
            world.audio.play("wave", 0.7)

    # -- estado ---------------------------------------------------------------
    @property
    def pending(self) -> int:
        if self.wave_obj is None:
            return 0
        return self.wave_obj.total - self.spawned

    @property
    def alive(self) -> int:
        return sum(1 for e in self.world.enemies if not e.dead)

    def progress(self) -> float:
        total = (self.wave_obj.total if self.wave_obj else 1) + 1
        done = self.spawned + self.alive
        return clamp(done / total, 0.0, 1.0)

    # -- update ---------------------------------------------------------------
    def update(self, dt: float) -> None:
        world = self.world
        if self.state == "idle":
            self.state = "intro"
            self.timer = 1.2
            return

        if self.state == "intro":
            self.timer -= dt
            if self.timer <= 0.0:
                if self.wave_obj is None:
                    self.start_next()
                else:
                    self.state = "spawn"
            return

        if self.state == "spawn":
            self.spawn_cd -= dt
            if self.spawn_cd <= 0.0 and self.pending > 0:
                self.spawn_one()
                self.spawn_cd = self.wave_obj.interval * rand_range(0.75, 1.3)
            if self.pending <= 0:
                self.state = "fight"
            return

        if self.state == "fight":
            if self.alive == 0:
                self.state = "clear"
                self.timer = 1.5
                world.on_wave_cleared(self.wave)
            return

        if self.state == "clear":
            self.timer -= dt
            if self.timer <= 0.0:
                if self.wave >= C.TOTAL_WAVES:
                    self.state = "victory"
                else:
                    self.start_next()

    # -- spawn ----------------------------------------------------------------
    def spawn_one(self) -> None:
        world = self.world
        wv = self.wave_obj
        assert wv is not None
        kind = wv.queue[self.spawned]
        self.spawned += 1

        if wv.is_boss and self.spawned == 1:
            p = pygame.Vector2(world.arena.centerx, world.arena.top + 130)
            boss = Boss(world, p.x, p.y, wv.boss_hp_mul, wv.spd_mul)
            world.enemies.append(boss)
            world.audio.play("boss", 0.8)
            world.fx.ring(p.x, p.y, 20, 220, 0.7, C.GOLD, 5.0)
            return

        cls = ENEMY_CLASSES[kind]
        p = spawn_point(world)
        e = cls(world, p.x, p.y, wv.hp_mul, wv.spd_mul)
        e.vel = pygame.Vector2(
            (p.x - world.player.pos.x), (p.y - world.player.pos.y)
        ).normalize() * rand_range(90.0, 200.0)
        world.enemies.append(e)
        world.fx.ring(p.x, p.y, 4, 46, 0.35, e.color, 2.5)
        world.fx.particles.burst(p, 8, e.color, speed=(60, 200), size=(2, 4),
                                 ttl=(0.15, 0.35), glow=0.7)
