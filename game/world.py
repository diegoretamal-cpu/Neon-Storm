"""Estado del mundo: entidades, colisiones, puntuación y oleadas."""

from __future__ import annotations

import math
import random

import pygame

from . import config as C
from . import weapons as W
from .entities import Pickup, Player
from .fx import FX
from .utils import (
    TAU,
    chance,
    circle_hits_rect,
    clamp,
    mix_color,
    safe_normalize,
)
from .waves import WaveRunner


class Input:
    __slots__ = ("move", "aim_pos", "aim_angle", "fire_held", "dash_pressed",
                 "using_mouse")

    def __init__(self) -> None:
        self.move = pygame.Vector2()
        self.aim_pos = pygame.Vector2()
        self.aim_angle = -math.pi / 2
        self.fire_held = False
        self.dash_pressed = False
        self.using_mouse = True

    def clear(self) -> None:
        self.dash_pressed = False


class Announcement:
    __slots__ = ("text", "color", "dur", "age", "delay", "big", "sub", "offset")

    def __init__(self, text, color, dur, delay=0.0, big=False, sub=False, offset=0.0):
        self.text = text
        self.color = color
        self.dur = dur
        self.age = 0.0
        self.delay = delay
        self.big = big
        self.sub = sub
        self.offset = offset


class World:
    def __init__(self, audio) -> None:
        self.audio = audio
        self.fx = FX()
        self.input = Input()
        self.arena = pygame.Rect(C.ARENA)
        self.obstacles: list[pygame.Rect] = [r for r, _ in C.pillars()]

        self.enemies: list = []
        self.player_bullets: list = []
        self.enemy_bullets: list = []
        self.pickups: list = []
        self.announcements: list[Announcement] = []

        self.time = 0.0
        self.run_time = 0.0
        self.score = 0
        self.kills = 0
        self.kills_by_player = 0
        self.combo = 1
        self.combo_timer = 0.0
        self.best_combo = 1
        self.new_record = False
        self.difficulty = 0.0
        self.hp_mul = 1.0
        self.spd_mul = 1.0
        self.over = False
        self.victory = False
        self.death_t = 0.0

        self.player = Player(self, self.arena.centerx, self.arena.centery)
        self.runner = WaveRunner(self)

    # -- ciclo de vida --------------------------------------------------------
    @property
    def boss(self):
        for e in self.enemies:
            if getattr(e, "is_boss", False) and not e.dead:
                return e
        return None

    def reset(self) -> None:
        self.enemies.clear()
        self.player_bullets.clear()
        self.enemy_bullets.clear()
        self.pickups.clear()
        self.announcements.clear()
        self.fx.clear()
        self.time = 0.0
        self.run_time = 0.0
        self.score = 0
        self.kills = 0
        self.kills_by_player = 0
        self.combo = 1
        self.combo_timer = 0.0
        self.best_combo = 1
        self.new_record = False
        self.over = False
        self.victory = False
        self.death_t = 0.0
        self.player = Player(self, self.arena.centerx, self.arena.centery)
        self.runner.reset()

    # -- utilidades -----------------------------------------------------------
    def announce(self, text, color=C.CYAN, dur=1.2, *, delay=0.0, big=False, sub=False, offset=0.0):
        self.announcements.append(Announcement(text, color, dur, delay, big, sub, offset))

    def obstacle_hit(self, pos, radius) -> bool:
        return any(circle_hits_rect(pos, radius, r) for r in self.obstacles)

    def enemy_near(self, x, y, radius) -> bool:
        r2 = radius * radius
        for e in self.enemies:
            if e.dead:
                continue
            dx = e.pos.x - x
            dy = e.pos.y - y
            if dx * dx + dy * dy < r2:
                return True
        return False

    def combo_reset(self) -> None:
        self.combo = 1
        self.combo_timer = 0.0

    # -- puntuación -----------------------------------------------------------
    def register_kill(self, enemy, boss: bool = False) -> None:
        self.kills += 1
        self.kills_by_player += 1
        if not boss:
            self.combo = min(C.COMBO_MAX, self.combo + 1)
            self.combo_timer = C.COMBO_WINDOW
            self.best_combo = max(self.best_combo, self.combo)

        base = enemy.max_hp * C.SCORE_CHUNK if boss else float(enemy.score)
        mult = 1.0 + (self.combo - 1) * 0.25 if not boss else 3.0
        gained = int(base * mult)
        self.score += gained

        pos = enemy.pos
        self.fx.text(pos.x, pos.y - enemy.radius - 6, f"+{gained}",
                     C.GOLD if boss else mix_color(C.WHITE, C.AMBER, 0.4),
                     ttl=0.9, size=24 if boss else 18)

        if boss:
            self.fx.text(pos.x, pos.y - 60, "¡CENTINELA ABATIDO!", C.LIME, ttl=1.6, size=28)
            for _ in range(3):
                self._drop(pos, forced="overdrive")
            return

        chance_p = 0.085 + (0.05 if enemy.radius > 20 else 0.0)
        if chance(chance_p):
            self._drop(pos)
        elif chance(0.03):
            self._drop(pos, forced="nuke")

    def _drop(self, pos, forced: str | None = None) -> None:
        kind = forced or random.choice(
            ["vida", "vida", "escudo", "arma", "overdrive", "nuke"]
        )
        a = random.uniform(0, TAU)
        p = pygame.Vector2(
            clamp(pos.x + math.cos(a) * 18, self.arena.left + 20, self.arena.right - 20),
            clamp(pos.y + math.sin(a) * 18, self.arena.top + 20, self.arena.bottom - 20),
        )
        if self.obstacle_hit(p, 16.0):
            p = pos.copy()
        pk = Pickup(p.x, p.y, kind, pygame.Vector2(math.cos(a), math.sin(a)) * 140)
        self.pickups.append(pk)

    def on_wave_cleared(self, n: int) -> None:
        bonus = 120 * n
        self.score += bonus
        self.fx.text(self.player.pos.x, self.player.pos.y - 40, f"oleada {n}  +{bonus}",
                     C.LIME, ttl=1.4, size=22)
        healed = self.player.heal(10.0)
        if healed > 0.5:
            self.fx.text(self.player.pos.x, self.player.pos.y - 62, f"+{int(healed)} integridad",
                         C.ICE, ttl=1.2, size=16)
        if n % 3 == 0:
            self._drop(self.player.pos, forced="arma")
        self.audio.play("wave", 0.5)

    def on_player_death(self) -> None:
        p = self.player
        self.fx.boom(p.pos, C.CYAN, 3.0, sparks=36, debris=20, smoke=12)
        self.fx.flash = 0.7
        self.fx.flash_color = C.WHITE
        self.fx.shake.add(28.0)
        self.audio.play("boom_big", 1.0)
        self.death_t = 0.0

    # -- update ---------------------------------------------------------------
    def update(self, dt: float) -> None:
        # Hit-stop: congela un instante el mundo tras un golpe fuerte.
        if self.fx.hitstop > 0.0:
            self.fx.hitstop = max(0.0, self.fx.hitstop - dt)
            self.fx.update(dt)
            self.input.clear()
            return

        self.time += dt
        if not self.over:
            self.run_time += dt

        # Anuncios
        alive_ann: list[Announcement] = []
        for a in self.announcements:
            if a.delay > 0.0:
                a.delay -= dt
            else:
                a.age += dt
            if a.age < a.dur and a.delay <= 0.0:
                alive_ann.append(a)
        self.announcements = alive_ann

        # Combo
        if self.combo > 1:
            self.combo_timer -= dt
            if self.combo_timer <= 0.0:
                self.combo_reset()

        wv = self.runner.wave_obj
        if wv is not None:
            self.hp_mul, self.spd_mul = wv.hp_mul, wv.spd_mul
        self.difficulty = clamp((self.runner.wave - 1) / 20.0, 0.0, 1.0)

        self.runner.update(dt)

        if not self.player.dead:
            self.player.update(dt, self)
        else:
            self.death_t += dt
            if self.death_t > 1.5:
                self.over = True

        if self.runner.state == "victory" and not self.over:
            self.over = True
            self.victory = True
            self.announce("¡ARENA DESPEJADA!", C.LIME, 3.0, big=True)

        # Enemigos
        for e in self.enemies:
            if not e.dead:
                e.update(dt, self)
        self._separate(dt)

        # Proyectiles del jugador
        alive_b: list = []
        for b in self.player_bullets:
            b.update(dt)
            if b.life <= 0.0 or not self._inside_arena(b.x, b.y, 40):
                continue
            if not b.pierce_walls and self.obstacle_hit(b.pos, b.radius):
                self.fx.particles.burst(b.pos, 4, b.color, speed=(60, 200), size=(1.5, 3),
                                        ttl=(0.1, 0.22), glow=0.7)
                continue
            if self._bullet_hits(b):
                continue
            alive_b.append(b)
        self.player_bullets = alive_b

        # Proyectiles enemigos
        alive_eb: list = []
        for b in self.enemy_bullets:
            b.update(dt, self)
            if b.life <= 0.0 or not self._inside_arena(b.x, b.y, 24):
                self.fx.particles.burst((b.x, b.y), 2, b.color, speed=(20, 70),
                                        size=(1, 2), ttl=(0.08, 0.16), glow=0.5)
                continue
            if self.obstacle_hit(b.pos, b.radius):
                self.fx.particles.burst(b.pos, 4, b.color, speed=(50, 180), size=(1.5, 3),
                                        ttl=(0.1, 0.22), glow=0.6)
                continue
            p = self.player
            if not p.dead and p.invuln <= 0.0 and p.dash_t <= 0.0:
                dx = p.pos.x - b.x
                dy = p.pos.y - b.y
                rr = p.radius + b.radius
                if dx * dx + dy * dy <= rr * rr:
                    if p.damage(b.damage, self, b.color):
                        pass
                    alive_eb = [x for x in alive_eb if x is not b]
                    continue
            alive_eb.append(b)
        self.enemy_bullets = alive_eb

        # Contacto con enemigos
        p = self.player
        if not p.dead and p.invuln <= 0.0 and p.dash_t <= 0.0:
            for e in self.enemies:
                if e.dead or e.spawn_t > 0:
                    continue
                dx = p.pos.x - e.pos.x
                dy = p.pos.y - e.pos.y
                rr = p.radius + e.radius
                if dx * dx + dy * dy <= rr * rr:
                    if p.damage(e.contact, self, e.color):
                        d = safe_normalize(p.pos - e.pos)
                        p.vel += d * 240.0
                        e.vel -= d * 90.0
                    break

        # Recogidas
        alive_pk: list[Pickup] = []
        for pk in self.pickups:
            pk.update(dt, self)
            if pk.taken or pk.ttl <= 0.0:
                if pk.taken:
                    self._collect(pk)
                continue
            alive_pk.append(pk)
        self.pickups = alive_pk

        # Enemigos muertos
        self.enemies = [e for e in self.enemies if not e.dead]

        self.fx.update(dt)
        self.input.clear()

    # -- colisiones auxiliares ------------------------------------------------
    def _inside_arena(self, x: float, y: float, margin: float) -> bool:
        a = self.arena
        return (a.left - margin) <= x <= (a.right + margin) and (a.top - margin) <= y <= (a.bottom + margin)

    def _bullet_hits(self, b) -> bool:
        p = self.player
        for e in self.enemies:
            if e.dead or id(e) in b.hits:
                continue
            dx = e.pos.x - b.x
            dy = e.pos.y - b.y
            rr = e.radius + b.radius
            if dx * dx + dy * dy <= rr * rr:
                knock = pygame.Vector2(b.vx, b.vy)
                before = e.hp
                e.damage(b.damage, self, knock)
                dealt = before - max(0.0, e.hp)
                if dealt > 0.0 and b.pierce <= 0:
                    return True
                if b.pierce > 0:
                    b.hits.add(id(e))
                    b.pierce -= 1
                    if b.pierce <= 0:
                        return True
        return False

    def _separate(self, dt: float) -> None:
        """Empuja los enemigos entre sí para que no se apilen."""
        n = len(self.enemies)
        if n < 2:
            return
        for i in range(n):
            a = self.enemies[i]
            if a.dead:
                continue
            for j in range(i + 1, n):
                b = self.enemies[j]
                if b.dead:
                    continue
                dx = b.pos.x - a.pos.x
                dy = b.pos.y - a.pos.y
                rr = a.radius + b.radius
                d2 = dx * dx + dy * dy
                if d2 >= rr * rr or d2 < 1e-6:
                    continue
                d = math.sqrt(d2)
                overlap = (rr - d) * 0.5
                nx, ny = dx / d, dy / d
                ma, mb = a.mass, b.mass
                total = ma + mb
                a.pos.x -= nx * overlap * (mb / total)
                a.pos.y -= ny * overlap * (mb / total)
                b.pos.x += nx * overlap * (ma / total)
                b.pos.y += ny * overlap * (ma / total)

    # -- recogidas ------------------------------------------------------------
    def _collect(self, pk: Pickup) -> None:
        p = self.player
        kind = pk.kind
        col, _glyph = {"vida": (C.LIME, ""), "escudo": (C.ICE, ""), "arma": (C.AMBER, ""),
                       "nuke": (C.MAGENTA, ""), "overdrive": (C.GOLD, "")}[kind]
        self.fx.ring(pk.pos.x, pk.pos.y, 8, 52, 0.32, col, 3.0)
        self.fx.particles.burst(pk.pos, 14, col, speed=(90, 300), size=(2, 4),
                                 ttl=(0.2, 0.45), glow=0.9)

        if kind == "vida":
            gained = p.heal(26.0)
            self.fx.text(p.pos.x, p.pos.y - 30, f"+{int(gained)}", C.LIME, ttl=0.9, size=20)
        elif kind == "escudo":
            p.shield = p.max_shield
            self.fx.text(p.pos.x, p.pos.y - 30, "ESCUDO", C.ICE, ttl=0.9, size=20)
        elif kind == "arma":
            wid = random.choice(W.PICKUP_POOL)
            p.give_weapon(wid, 16.0)
            self.fx.text(p.pos.x, p.pos.y - 30, W.WEAPONS[wid].name, W.WEAPONS[wid].color,
                         ttl=1.0, size=20)
        elif kind == "overdrive":
            p.overdrive = 8.0
            self.fx.text(p.pos.x, p.pos.y - 30, "OVERDRIVE", C.GOLD, ttl=1.0, size=20)
        elif kind == "nuke":
            self.fx.text(p.pos.x, p.pos.y - 30, "NOVA", C.MAGENTA, ttl=1.0, size=22)
            self.nuke()
        self.audio.play("pickup", 0.7)
        self.score += 25

    def nuke(self) -> None:
        """Limpia la pantalla: destruye proyectiles y daña a todo."""
        self.audio.play("nuke", 0.9)
        self.fx.flash = 0.75
        self.fx.flash_color = C.MAGENTA
        self.fx.shake.add(22.0)
        p = self.player.pos
        for b in self.enemy_bullets:
            self.fx.particles.burst((b.x, b.y), 2, b.color, speed=(20, 90),
                                    size=(1, 2.5), ttl=(0.1, 0.25), glow=0.6)
        self.enemy_bullets.clear()
        for e in list(self.enemies):
            if e.dead:
                continue
            dist = (e.pos - p).length()
            falloff = clamp(1.0 - dist / 900.0, 0.15, 1.0)
            dmg = e.max_hp * (0.55 + 0.35 * falloff) if getattr(e, "is_boss", False) else 9999.0
            e.damage(dmg, self, safe_normalize(e.pos - p))
        for r in range(4):
            self.fx.ring(p.x, p.y, 20 + r * 40, 420 + r * 120, 0.55, C.MAGENTA, 6.0 - r, 0.8)

    # -- récord ---------------------------------------------------------------
    def apply_record(self, best: dict) -> None:
        if self.score > best.get("score", 0):
            best["score"] = self.score
            best["wave"] = self.runner.wave
            best["kills"] = self.kills
            self.new_record = True
        best["plays"] = best.get("plays", 0) + 1
