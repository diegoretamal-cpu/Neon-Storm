"""Entidades: jugador, enemigos, proyectiles enemigos y recogidas."""

from __future__ import annotations

import math
import random

import pygame

from . import config as C
from . import weapons as W
from .fx import glow_dot, glow_line, glow_poly
from .utils import (
    TAU,
    Color,
    chance,
    clamp,
    ease_out_cubic,
    lerp,
    mix_color,
    push_out_of_rect,
    rand_range,
    rotate_towards,
    safe_normalize,
    scale_color,
    shift_towards_white,
    with_alpha,
)


# --- Utilidades de dibujo ---------------------------------------------------
def collide_world(pos: pygame.Vector2, radius: float, world) -> None:
    """Mantiene un círculo dentro de la arena y fuera de los pilares."""
    a = world.arena
    pos.x = clamp(pos.x, a.left + radius, a.right - radius)
    pos.y = clamp(pos.y, a.top + radius, a.bottom - radius)
    for rect in world.obstacles:
        new = push_out_of_rect(pos, radius, rect)
        pos.x, pos.y = new.x, new.y


def shape_polygon(center: pygame.Vector2, radius: float, sides: int, rot: float) -> list[tuple[int, int]]:
    pts = []
    for i in range(sides):
        a = rot + i * TAU / sides
        pts.append((int(center.x + math.cos(a) * radius), int(center.y + math.sin(a) * radius)))
    return pts


def draw_shape(
    surf: pygame.Surface,
    glow: pygame.Surface,
    center: pygame.Vector2,
    radius: float,
    sides: int,
    rot: float,
    color: Color,
    *,
    width: int = 2,
    fill: float = 0.16,
    glow_w: float = 3.0,
    intensity: float = 1.0,
) -> list[tuple[int, int]]:
    c = (int(center.x), int(center.y))
    if sides < 3:
        if fill > 0:
            pygame.draw.circle(surf, with_alpha(color, int(255 * fill)), c, int(radius))
        pygame.draw.circle(surf, color, c, int(radius), width)
        glow_dot(glow, center, radius * 1.2, color, intensity)
        return []
    pts = shape_polygon(center, radius, sides, rot)
    if fill > 0:
        pygame.draw.polygon(surf, with_alpha(color, int(255 * fill)), pts)
    pygame.draw.polygon(surf, color, pts, width)
    glow_poly(glow, pts, color, glow_w, intensity)
    return pts


_GLYPH_FONT: pygame.font.Font | None = None


def _glyph_font(size: int) -> pygame.font.Font:
    global _GLYPH_FONT
    if _GLYPH_FONT is None:
        _GLYPH_FONT = pygame.font.Font(None, 32)
    return _GLYPH_FONT



# --- Jugador ----------------------------------------------------------------
class Player:
    def __init__(self, world, x: float, y: float) -> None:
        self.pos = pygame.Vector2(x, y)
        self.vel = pygame.Vector2()
        self.radius = C.PLAYER_RADIUS
        self.max_hp = C.PLAYER_MAX_HP
        self.hp = self.max_hp
        self.angle = -math.pi / 2.0
        self.spin = 0.0

        self.invuln = C.PLAYER_I_FRAMES
        self.hit_flash = 0.0
        self.dead = False
        self.death_t = 0.0

        self.dash_cd = 0.0
        self.dash_t = 0.0
        self.dash_dir = pygame.Vector2(1.0, 0.0)

        self.weapon_id = "pulse"
        self.weapon_time = 0.0
        self.weapon_time_max = 0.0
        self.overdrive = 0.0
        self.shield = 0.0
        self.max_shield = 100.0

        self.fire_cd = 0.0
        self.recoil = 0.0
        self.ghosts: list[tuple[float, float, float]] = []
        self.kills = 0
        self.shots = 0

    # -- estado ---------------------------------------------------------------
    @property
    def weapon(self) -> W.Weapon:
        return W.WEAPONS[self.weapon_id]

    @property
    def alive(self) -> bool:
        return not self.dead

    def give_weapon(self, weapon_id: str, duration: float = 16.0) -> None:
        self.weapon_id = weapon_id
        self.weapon_time = duration
        self.weapon_time_max = duration
        self.fire_cd = 0.0

    # -- update ---------------------------------------------------------------
    def update(self, dt: float, world) -> None:
        inp = world.input

        self.invuln = max(0.0, self.invuln - dt)
        self.hit_flash = max(0.0, self.hit_flash - dt * 4.0)
        self.dash_cd = max(0.0, self.dash_cd - dt)
        self.recoil = max(0.0, self.recoil - self.recoil * 9.0 * dt)
        self.overdrive = max(0.0, self.overdrive - dt)
        if self.weapon_time > 0.0:
            self.weapon_time = max(0.0, self.weapon_time - dt)
            if self.weapon_time == 0.0:
                self.weapon_id = "pulse"

        if self.dead:
            self.death_t += dt
            return

        # Objetivo de apuntado
        self.angle = rotate_towards(self.angle, inp.aim_angle, 14.0 * dt)

        # Dash
        if self.dash_t > 0.0:
            self.dash_t -= dt
            self.vel = pygame.Vector2(self.dash_dir.x * C.DASH_SPEED, self.dash_dir.y * C.DASH_SPEED)
        else:
            if inp.dash_pressed and self.dash_cd <= 0.0:
                mv = inp.move
                self.dash_dir = pygame.Vector2(mv.x, mv.y)
                if self.dash_dir.length_squared() < 1e-4:
                    self.dash_dir = pygame.Vector2(math.cos(self.angle), math.sin(self.angle))
                self.dash_dir = self.dash_dir.normalize()
                self.dash_t = C.DASH_TIME
                self.dash_cd = C.DASH_COOLDOWN
                self.invuln = max(self.invuln, C.DASH_TIME + 0.10)
                world.fx.particles.burst(
                    self.pos, 12, C.CYAN, speed=(60, 220), size=(2, 4),
                    ttl=(0.2, 0.4), glow=0.8, direction=math.atan2(-self.dash_dir.y, -self.dash_dir.x), cone=1.4,
                )
                world.audio.play("dash", 0.8)
            else:
                target = pygame.Vector2(inp.move.x, inp.move.y)
                if target.length_squared() > 1e-6:
                    target = target.normalize() * C.PLAYER_SPEED
                accel = C.PLAYER_ACCEL
                self.vel.x = _approach(self.vel.x, target.x, accel * dt)
                self.vel.y = _approach(self.vel.y, target.y, accel * dt)
                if target.length_squared() < 1e-6:
                    damp = math.exp(-C.PLAYER_FRICTION * dt)
                    self.vel.x *= damp
                    self.vel.y *= damp

        self.pos += self.vel * dt
        collide_world(self.pos, self.radius, world)

        # Estela
        speed = self.vel.length()
        self.ghosts.append((self.pos.x, self.pos.y, self.angle))
        if len(self.ghosts) > 14:
            self.ghosts.pop(0)
        self.spin += dt * (2.0 + speed * 0.006)

        # Disparo
        self.fire_cd = max(0.0, self.fire_cd - dt)
        if inp.fire_held and self.fire_cd <= 0.0:
            self.shoot(world)

    def shoot(self, world) -> None:
        wpn = self.weapon
        mul = 1.6 if self.overdrive > 0.0 else 1.0
        bullets = W.fire(wpn, self.pos, self.angle, mul)
        world.player_bullets.extend(bullets)
        self.shots += len(bullets)
        self.fire_cd = wpn.cd * (0.62 if self.overdrive > 0.0 else 1.0)
        self.recoil = wpn.recoil
        # Retroceso
        self.vel -= pygame.Vector2(math.cos(self.angle), math.sin(self.angle)) * (wpn.recoil * 0.12)
        world.fx.particles.burst(
            self.pos, 4 if wpn.count < 4 else 8, wpn.color,
            speed=(120, 300), size=(1.5, 3.0), ttl=(0.08, 0.18), glow=1.0,
            direction=self.angle, cone=0.9,
        )
        world.fx.shake.add(0.9 if wpn.count < 4 else 2.0)
        world.audio.play(wpn.sound, 0.55, min_gap=0.03)

    # -- daño -----------------------------------------------------------------
    def damage(self, amount: float, world, color: Color = C.RED) -> bool:
        if self.dead or self.invuln > 0.0 or self.dash_t > 0.0:
            return False
        if self.shield > 0.0:
            absorbed = min(self.shield, amount)
            self.shield -= absorbed
            amount -= absorbed
            world.fx.ring(self.pos.x, self.pos.y, 18, 44, 0.28, C.ICE, 3.0)
            world.audio.play("shield", 0.7)
            if amount <= 0.0:
                world.fx.shake.add(3.0)
                return True
        self.hp -= amount
        self.invuln = C.PLAYER_I_FRAMES
        self.hit_flash = 1.0
        world.fx.particles.sparks(self.pos, 14, C.RED, speed=(160, 420))
        world.fx.particles.flash(self.pos, C.RED, 22.0)
        world.fx.shake.add(9.0)
        world.fx.hitstop = max(world.fx.hitstop, 0.07)
        world.fx.flash = max(world.fx.flash, 0.22)
        world.fx.flash_color = C.RED
        world.fx.vignette_pulse = 1.0
        world.audio.play("hurt", 0.8)
        world.combo_reset()
        if self.hp <= 0.0:
            self.hp = 0.0
            self.dead = True
            world.on_player_death()
        return True

    def heal(self, amount: float) -> float:
        before = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        return self.hp - before

    # -- draw -----------------------------------------------------------------
    def draw(self, surf: pygame.Surface, glow: pygame.Surface, world) -> None:
        blink = self.invuln > 0.0 and not self.dead and int(world.time * 22) % 2 == 0
        alpha = 90 if blink else 255
        col = shift_towards_white(C.PLAYER_MAIN, self.hit_flash * 0.9)
        if self.overdrive > 0.0:
            col = mix_color(col, C.GOLD, 0.35 + 0.25 * math.sin(world.time * 12))

        # Fantasmas de la estela
        for i, (gx, gy, ga) in enumerate(self.ghosts):
            t = (i + 1) / len(self.ghosts)
            if t < 0.55:
                continue
            fade = int(70 * (t - 0.55) / 0.45)
            pts = _ship_polygon(pygame.Vector2(gx, gy), ga, self.radius * 0.85)
            pygame.draw.polygon(surf, with_alpha(C.CYAN, fade // 2), pts)
            glow_dot(glow, (gx, gy), 8, C.CYAN, 0.12 * t)

        # Escudo
        if self.shield > 0.0:
            f = self.shield / self.max_shield
            a0 = -math.pi / 2
            pygame.draw.circle(surf, with_alpha(C.ICE, 40), (int(self.pos.x), int(self.pos.y)),
                               int(self.radius + 9), 2)
            rect = pygame.Rect(0, 0, int((self.radius + 9) * 2), int((self.radius + 9) * 2))
            rect.center = (int(self.pos.x), int(self.pos.y))
            pygame.draw.arc(surf, C.ICE, rect, a0, a0 + TAU * f, 3)
            glow_dot(glow, self.pos, self.radius + 13, C.ICE, 0.35 * f)

        # Llama del motor
        thrust = clamp(self.vel.length() / C.PLAYER_SPEED, 0.0, 1.0)
        flame = 8 + thrust * 16 + math.sin(world.time * 40) * 2.5
        fx_ = self.pos + pygame.Vector2(math.cos(self.angle + math.pi), math.sin(self.angle + math.pi)) * (self.radius + 4)
        fa = self.angle + math.pi
        flame_pts = [
            (int(fx_.x + math.cos(fa) * flame), int(fx_.y + math.sin(fa) * flame)),
            (int(fx_.x + math.cos(fa + 1.9) * 6), int(fx_.y + math.sin(fa + 1.9) * 6)),
            (int(fx_.x + math.cos(fa - 1.9) * 6), int(fx_.y + math.sin(fa - 1.9) * 6)),
        ]
        pygame.draw.polygon(surf, with_alpha(mix_color(C.CYAN, C.WHITE, 0.5), int(220 * (0.4 + thrust * 0.6))), flame_pts)
        glow_dot(glow, (fx_.x + math.cos(fa) * flame * 0.5, fx_.y + math.sin(fa) * flame * 0.5),
                 9, C.CYAN, 0.5 + thrust * 0.3)

        # Casco
        body = _ship_polygon(self.pos, self.angle, self.radius)
        pygame.draw.polygon(surf, with_alpha(C.NIGHT, alpha), body)
        pygame.draw.polygon(surf, with_alpha(col, alpha), body, 2)
        inner = _ship_polygon(self.pos, self.angle, self.radius * 0.45)
        pygame.draw.polygon(surf, with_alpha(mix_color(col, C.WHITE, 0.6), alpha), inner)
        glow_dot(glow, self.pos, self.radius * 1.35, col, 0.75 if not blink else 0.35)

        if self.dash_t > 0.0:
            glow_dot(glow, self.pos, self.radius * 2.6, C.WHITE, 0.45)

    def draw_health_ring(self, surf: pygame.Surface, glow: pygame.Surface) -> None:
        f = clamp(self.hp / self.max_hp, 0.0, 1.0)
        r = self.radius + 6
        rect = pygame.Rect(0, 0, r * 2, r * 2)
        rect.center = (int(self.pos.x), int(self.pos.y))
        pygame.draw.arc(surf, with_alpha(C.BLACK, 120), rect, 0, TAU, 3)
        col = C.LIME if f > 0.5 else (C.AMBER if f > 0.25 else C.RED)
        if f > 0.005:
            pygame.draw.arc(surf, col, rect, -math.pi / 2, -math.pi / 2 + TAU * f, 3)


def _ship_polygon(center: pygame.Vector2, angle: float, radius: float) -> list[tuple[int, int]]:
    nose = (center.x + math.cos(angle) * radius * 1.55,
            center.y + math.sin(angle) * radius * 1.55)
    left = (center.x + math.cos(angle + 2.5) * radius,
            center.y + math.sin(angle + 2.5) * radius)
    right = (center.x + math.cos(angle - 2.5) * radius,
            center.y + math.sin(angle - 2.5) * radius)
    return [(int(nose[0]), int(nose[1])), (int(left[0]), int(left[1])), (int(right[0]), int(right[1]))]


def _approach(cur: float, target: float, delta: float) -> float:
    if cur < target:
        return min(cur + delta, target)
    return max(cur - delta, target)


# --- Proyectil enemigo ------------------------------------------------------
class EnemyBullet:
    __slots__ = ("x", "y", "vx", "vy", "radius", "color", "life", "ttl",
                 "damage", "homing", "wobble", "wobble_phase", "spin")

    def __init__(self, x, y, vx, vy, radius, color, ttl=4.0, damage=9.0,
                 homing: float = 0.0, wobble: float = 0.0) -> None:
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.radius = radius
        self.color = color
        self.ttl = self.life = ttl
        self.damage = damage
        self.homing = homing
        self.wobble = wobble
        self.wobble_phase = random.uniform(0, TAU)
        self.spin = random.uniform(-6, 6)

    @property
    def pos(self) -> pygame.Vector2:
        return pygame.Vector2(self.x, self.y)

    def update(self, dt: float, world) -> None:
        self.life -= dt
        p = world.player
        if self.homing > 0.0 and not p.dead:
            target = math.atan2(p.pos.y - self.y, p.pos.x - self.x)
            cur = math.atan2(self.vy, self.vx)
            a = cur + clamp(math.atan2(math.sin(target - cur), math.cos(target - cur)),
                            -self.homing * dt, self.homing * dt)
            spd = math.hypot(self.vx, self.vy)
            self.vx, self.vy = math.cos(a) * spd, math.sin(a) * spd
        if self.wobble:
            spd = math.hypot(self.vx, self.vy)
            a = math.atan2(self.vy, self.vx) + math.sin(world.time * 8 + self.wobble_phase) * self.wobble * dt
            self.vx, self.vy = math.cos(a) * spd, math.sin(a) * spd
        self.x += self.vx * dt
        self.y += self.vy * dt

    def draw(self, surf: pygame.Surface, glow: pygame.Surface) -> None:
        col = self.color
        pygame.draw.circle(surf, with_alpha(col, 210), (int(self.x), int(self.y)), int(self.radius))
        pygame.draw.circle(surf, C.WHITE, (int(self.x), int(self.y)), max(1, int(self.radius * 0.45)))
        glow_dot(glow, (self.x, self.y), self.radius * 1.7, col, 0.6)


# --- Base de enemigos -------------------------------------------------------
class Enemy:
    kind = "enemigo"
    sides = 4
    radius = 16.0
    max_hp = 20.0
    speed = 150.0
    color: Color = C.RED
    contact = 8.0
    score = 10
    mass = 1.0
    xp_drop = 0.0

    def __init__(self, world, x: float, y: float, hp_mul: float = 1.0, spd_mul: float = 1.0) -> None:
        self.world = world
        self.pos = pygame.Vector2(x, y)
        self.vel = pygame.Vector2()
        self.max_hp = self.max_hp * hp_mul
        self.hp = self.max_hp
        self.base_speed = self.speed
        self.speed = self.speed * spd_mul
        self.spd_mul = spd_mul
        self.hp_mul = hp_mul
        self.flash = 0.0
        self.rot = random.uniform(0, TAU)
        self.spin = random.uniform(-1.6, 1.6)
        self.age = 0.0
        self.dead = False
        self.spawn_t = 0.30
        self.tint = random.uniform(-0.12, 0.12)
        self.is_boss = False

    # -- update ---------------------------------------------------------------
    def update(self, dt: float, world) -> None:
        self.age += dt
        self.flash = max(0.0, self.flash - dt * 5.0)
        self.spawn_t = max(0.0, self.spawn_t - dt)
        self.rot += self.spin * dt
        self.think(dt, world)

    def think(self, dt: float, world) -> None:  # pragma: no cover - abstracto
        pass

    def to_player(self, world) -> pygame.Vector2:
        return world.player.pos - self.pos

    def drift(self, dt: float, target: pygame.Vector2, accel: float = 900.0, drag: float = 0.90) -> None:
        self.vel += target * accel * dt
        self.pos += self.vel * dt
        d = drag ** (dt * 60)
        self.vel.x *= d
        self.vel.y *= d

    # -- daño / muerte --------------------------------------------------------
    def damage(self, amount: float, world, knock: pygame.Vector2 | None = None) -> bool:
        if self.dead or self.spawn_t > 0.0:
            return False
        self.hp -= amount
        self.flash = 1.0
        world.fx.particles.sparks(self.pos, 3, C.WHITE, speed=(120, 320))
        world.audio.play("hit", 0.35, min_gap=0.02)
        if knock is not None and self.mass > 0 and knock.length_squared() > 1e-6:
            self.vel += knock.normalize() * (170.0 / self.mass)
        if self.hp <= 0.0:
            self.kill(world)
            return True
        return False

    def kill(self, world) -> None:
        if self.dead:
            return
        self.dead = True
        self.on_death(world)

    def on_death(self, world) -> None:
        scale = clamp(self.radius / 16.0, 0.7, 3.0)
        world.fx.boom(self.pos, self.color, scale * 0.9)
        world.audio.play("boom", clamp(0.35 + self.radius * 0.012, 0.3, 1.0), min_gap=0.02)
        world.register_kill(self)

    # -- draw -----------------------------------------------------------------
    def draw(self, surf: pygame.Surface, glow: pygame.Surface, world) -> None:
        s = 1.0 + self.spawn_t * 1.4 if self.spawn_t > 0 else 1.0
        r = self.radius * s
        a = 255 if self.spawn_t <= 0 else int(255 * (1.0 - self.spawn_t / 0.30))
        col = shift_towards_white(self.color, self.flash * 0.95)
        col = _apply_tint(col, self.tint)

        if self.spawn_t > 0:
            pygame.draw.circle(surf, with_alpha(col, 40), (int(self.pos.x), int(self.pos.y)), int(r * 2.2))

        draw_shape(surf, glow, self.pos, r, self.sides, self.rot, col,
                   width=2, fill=0.20, glow_w=3.0, intensity=0.85)
        # Núcleo
        core = _apply_tint(shift_towards_white(col, 0.55), self.tint)
        pygame.draw.circle(surf, with_alpha(core, a), (int(self.pos.x), int(self.pos.y)),
                           max(2, int(r * 0.30)))
        glow_dot(glow, self.pos, r * 1.15, col, 0.6)

    def draw_health(self, surf: pygame.Surface, glow: pygame.Surface) -> None:
        if self.hp >= self.max_hp or self.dead:
            return
        w = int(self.radius * 2.2)
        x = int(self.pos.x - w / 2)
        y = int(self.pos.y - self.radius - 12)
        pygame.draw.rect(surf, with_alpha(C.BLACK, 160), (x, y, w, 4))
        f = clamp(self.hp / self.max_hp, 0.0, 1.0)
        col = C.AMBER if f > 0.4 else C.RED
        pygame.draw.rect(surf, col, (x, y, int(w * f), 4))


def _apply_tint(c: Color, t: float) -> Color:
    if abs(t) < 1e-4:
        return c
    f = 1.0 + t
    return (int(clamp(c[0] * f, 0, 255)), int(clamp(c[1] * f, 0, 255)), int(clamp(c[2] * f, 0, 255)))


# --- Tipos concretos --------------------------------------------------------
class Chaser(Enemy):
    kind = "zancudo"
    sides = 4
    radius = 15.0
    max_hp = 17.0
    speed = 172.0
    color = C.RED
    contact = 9.0
    score = 10

    def think(self, dt: float, world) -> None:
        d = self.to_player(world)
        ang = math.atan2(d.y, d.x) + math.sin(self.age * 5.0 + self.tint * 30) * 0.35
        target = pygame.Vector2(math.cos(ang), math.sin(ang)) * self.speed
        self.vel += (target - self.vel) * min(1.0, 5.0 * dt)
        self.pos += self.vel * dt
        collide_world(self.pos, self.radius, world)
        self.spin = 3.0


class Shooter(Enemy):
    kind = "escupidor"
    sides = 6
    radius = 17.0
    max_hp = 26.0
    speed = 128.0
    color = C.MAGENTA
    contact = 8.0
    score = 16

    def __init__(self, world, x, y, hp_mul=1.0, spd_mul=1.0) -> None:
        super().__init__(world, x, y, hp_mul, spd_mul)
        self.cd = rand_range(0.5, 1.4)
        self.orbit_dir = 1 if chance(0.5) else -1
        self.preferred = 300.0

    def think(self, dt: float, world) -> None:
        d = self.to_player(world)
        dist = max(1.0, d.length())
        n = d / dist
        tang = pygame.Vector2(-n.y, n.x) * self.orbit_dir
        radial = 0.0
        if dist > self.preferred + 40:
            radial = 1.0
        elif dist < self.preferred - 60:
            radial = -1.0
        target = (n * radial * 1.2 + tang * 0.9)
        target = target.normalize() * self.speed
        self.vel += (target - self.vel) * min(1.0, 3.5 * dt)
        self.pos += self.vel * dt
        collide_world(self.pos, self.radius, world)

        self.cd -= dt
        if self.cd <= 0.0 and dist < 620.0:
            self.cd = max(0.55, 1.55 - world.difficulty * 0.03)
            self.shoot(world, d)

    def shoot(self, world, d: pygame.Vector2) -> None:
        base = math.atan2(d.y, d.x)
        n = 3 if world.difficulty > 0.4 else 1
        for i in range(n):
            a = base + (i - (n - 1) / 2) * 0.20
            spd = 330.0
            world.enemy_bullets.append(
                EnemyBullet(self.pos.x, self.pos.y, math.cos(a) * spd, math.sin(a) * spd,
                            6.0, C.MAGENTA, ttl=3.4, damage=9.0, homing=0.8)
            )
        world.fx.particles.burst(self.pos, 5, C.MAGENTA, speed=(80, 200), size=(2, 3.5),
                                 ttl=(0.1, 0.25), glow=0.7, direction=base, cone=0.8)
        world.audio.play("shoot", 0.22, min_gap=0.05)


class Orbiter(Enemy):
    kind = "orbitador"
    sides = 0  # círculo
    radius = 19.0
    max_hp = 34.0
    speed = 150.0
    color = C.VIOLET
    contact = 10.0
    score = 22

    def __init__(self, world, x, y, hp_mul=1.0, spd_mul=1.0) -> None:
        super().__init__(world, x, y, hp_mul, spd_mul)
        self.orbit_r = 240.0
        self.angle = math.atan2(y - world.player.pos.y, x - world.player.pos.x)
        self.omega = 1.05 * spd_mul
        self.cd = rand_range(1.0, 2.2)

    def think(self, dt: float, world) -> None:
        p = world.player.pos
        self.angle += self.omega * dt
        self.pos.x = p.x + math.cos(self.angle) * self.orbit_r
        self.pos.y = p.y + math.sin(self.angle) * self.orbit_r
        self.spin = 2.4

        self.cd -= dt
        if self.cd <= 0.0:
            self.cd = max(1.1, 2.4 - world.difficulty * 0.06)
            self.burst(world)

    def burst(self, world) -> None:
        n = 9
        base = random.uniform(0, TAU)
        for i in range(n):
            a = base + i * TAU / n
            spd = 230.0
            world.enemy_bullets.append(
                EnemyBullet(self.pos.x, self.pos.y, math.cos(a) * spd, math.sin(a) * spd,
                            6.5, C.VIOLET, ttl=3.6, damage=10.0, wobble=0.8)
            )
        world.fx.ring(self.pos.x, self.pos.y, 10, 40, 0.3, C.VIOLET, 2.5)
        world.audio.play("hit", 0.3, min_gap=0.08)

    def draw(self, surf: pygame.Surface, glow: pygame.Surface, world) -> None:
        r = self.radius
        # Anillos giratorios
        for i, rr in enumerate((r * 1.7, r * 2.3)):
            a = self.rot * (1 if i == 0 else -1)
            w = 2 if i == 0 else 1
            pygame.draw.circle(surf, with_alpha(C.VIOLET, 90), (int(self.pos.x), int(self.pos.y)), int(rr), w)
            for k in range(3):
                aa = a + k * TAU / 3
                px = self.pos.x + math.cos(aa) * rr
                py = self.pos.y + math.sin(aa) * rr
                pygame.draw.circle(surf, C.ICE, (int(px), int(py)), 3)
                glow_dot(glow, (px, py), 7, C.ICE, 0.5)
        super().draw(surf, glow, world)


class Tank(Enemy):
    kind = "bruto"
    sides = 8
    radius = 28.0
    max_hp = 130.0
    speed = 82.0
    color = C.ORANGE
    contact = 22.0
    score = 45
    mass = 3.2

    def __init__(self, world, x, y, hp_mul=1.0, spd_mul=1.0) -> None:
        super().__init__(world, x, y, hp_mul, spd_mul)
        self.state = "roam"
        self.timer = rand_range(1.0, 2.4)
        self.charge_dir = pygame.Vector2(1, 0)

    def think(self, dt: float, world) -> None:
        self.timer -= dt
        d = self.to_player(world)
        dist = max(1.0, d.length())
        n = d / dist

        if self.state == "roam":
            self.vel += (n * self.speed - self.vel) * min(1.0, 2.2 * dt)
            self.pos += self.vel * dt
            if self.timer <= 0.0 and dist < 480.0:
                self.state = "warn"
                self.timer = 0.62
                self.charge_dir = n.copy()
        elif self.state == "warn":
            self.vel *= 0.88
            self.pos += self.vel * dt
            if self.timer <= 0.0:
                self.state = "charge"
                self.timer = 0.45
                self.vel = self.charge_dir * 700.0
                world.fx.shake.add(4.0)
                world.audio.play("dash", 0.5)
        elif self.state == "charge":
            self.vel *= 0.985
            self.pos += self.vel * dt
            if self.timer <= 0.0:
                self.state = "recover"
                self.timer = 0.75

        if self.state == "recover" and self.timer <= 0.0:
            self.state = "roam"
            self.timer = rand_range(1.6, 3.0)

        self.spin = 1.1
        collide_world(self.pos, self.radius, world)

    def draw(self, surf: pygame.Surface, glow: pygame.Surface, world) -> None:
        if self.state == "warn":
            f = 1.0 - clamp(self.timer / 0.62, 0, 1)
            a = self.angle_to_player()
            ex = self.pos.x + math.cos(a) * 300
            ey = self.pos.y + math.sin(a) * 300
            pygame.draw.line(surf, with_alpha(C.RED, int(60 + 90 * f)),
                             (int(self.pos.x), int(self.pos.y)), (int(ex), int(ey)), 3)
            glow_line(glow, self.pos, (ex, ey), C.RED, 10, 0.4 * f)
        if self.state == "charge":
            glow_dot(glow, self.pos, self.radius * 2.2, C.ORANGE, 0.45)
        super().draw(surf, glow, world)
        # Placas de armadura
        for i in range(4):
            a = self.rot * 0.6 + i * TAU / 4
            px = self.pos.x + math.cos(a) * self.radius * 0.72
            py = self.pos.y + math.sin(a) * self.radius * 0.72
            pygame.draw.circle(surf, with_alpha(C.GOLD, 190), (int(px), int(py)), 4)

    def angle_to_player(self) -> float:
        p = self.world.player.pos
        return math.atan2(p.y - self.pos.y, p.x - self.pos.x)


class Splitter(Enemy):
    kind = "mitosis"
    sides = 0
    radius = 22.0
    max_hp = 46.0
    speed = 112.0
    color = C.LIME
    contact = 12.0
    score = 30
    mass = 1.6

    def think(self, dt: float, world) -> None:
        d = self.to_player(world)
        n = safe_normalize(d)
        wob = pygame.Vector2(-n.y, n.x) * math.sin(self.age * 3.0) * 0.7
        target = (n + wob).normalize() * self.speed
        self.vel += (target - self.vel) * min(1.0, 3.0 * dt)
        self.pos += self.vel * dt
        collide_world(self.pos, self.radius, world)
        self.spin = 0.8

    def draw(self, surf: pygame.Surface, glow: pygame.Surface, world) -> None:
        pulse = 1.0 + 0.10 * math.sin(self.age * 8.0)
        r = self.radius * pulse
        col = shift_towards_white(self.color, self.flash * 0.9)
        pygame.draw.circle(surf, with_alpha(col, 40), (int(self.pos.x), int(self.pos.y)), int(r * 1.9))
        pygame.draw.circle(surf, with_alpha(col, 170), (int(self.pos.x), int(self.pos.y)), int(r), 2)
        # Dos lóbulos que laten
        for k in (-1, 1):
            a = self.rot * (1 if k > 0 else -1)
            px = self.pos.x + math.cos(a) * r * 0.55
            py = self.pos.y + math.sin(a) * r * 0.55
            pygame.draw.circle(surf, col, (int(px), int(py)), max(2, int(r * 0.42)))
            glow_dot(glow, (px, py), r * 1.3, col, 0.6)
        pygame.draw.circle(surf, C.WHITE, (int(self.pos.x), int(self.pos.y)), max(2, int(r * 0.2)))
        glow_dot(glow, self.pos, r * 1.2, col, 0.55)

    def on_death(self, world) -> None:
        super().on_death(world)
        for i in range(3):
            a = self.rot + i * TAU / 3
            px = self.pos.x + math.cos(a) * 24
            py = self.pos.y + math.sin(a) * 24
            shard = Shard(world, px, py, world.hp_mul, world.spd_mul)
            shard.vel = pygame.Vector2(math.cos(a), math.sin(a)) * 320
            world.enemies.append(shard)
            world.fx.particles.burst((px, py), 5, C.LIME, speed=(80, 240), size=(2, 3.5),
                                     ttl=(0.15, 0.3), glow=0.7)


class Shard(Enemy):
    kind = "esquirla"
    sides = 3
    radius = 9.0
    max_hp = 9.0
    speed = 260.0
    color = C.TEAL
    contact = 6.0
    score = 4
    mass = 0.5

    def think(self, dt: float, world) -> None:
        d = self.to_player(world)
        n = safe_normalize(d)
        target = n * self.speed
        self.vel += (target - self.vel) * min(1.0, 5.5 * dt)
        self.pos += self.vel * dt
        collide_world(self.pos, self.radius, world)
        self.rot = math.atan2(self.vel.y, self.vel.x)


# --- Jefe -------------------------------------------------------------------
class Boss(Enemy):
    kind = "centinela"
    sides = 6
    radius = 58.0
    max_hp = 780.0
    speed = 74.0
    color = C.GOLD
    contact = 30.0
    score = 400
    mass = 12.0

    omega_sign = 1
    state = "orbit"
    core_spin = 0.0

    def __init__(self, world, x, y, hp_mul=1.0, spd_mul=1.0) -> None:
        super().__init__(world, x, y, hp_mul, spd_mul)
        self.is_boss = True
        self.phase = 1
        self.pattern = "radial"
        self.timer = 2.4
        self.pattern_t = 0.0
        self.spiral_angle = 0.0
        self.spiral_cd = 0.0
        self.burst_cd = 0.0
        self.spawn_t = 0.9
        self.invuln_t = 0.0
        self.omega_sign = 1 if chance(0.5) else -1
        self.state = "orbit"
        self.core_spin = 0.0
        self.name = "centinela"

    # -- update ---------------------------------------------------------------
    def think(self, dt: float, world) -> None:
        self.timer -= dt
        self.invuln_t = max(0.0, self.invuln_t - dt)

        d = self.to_player(world)
        dist = max(1.0, d.length())
        n = d / dist

        # Movimiento: avanza lento orbitando a distancia media
        if self.state == "charge":
            self.vel *= 0.97
            self.pos += self.vel * dt
            if self.timer <= 0.0:
                self.state = "orbit"
                self.timer = rand_range(1.6, 2.4)
        else:
            tang = pygame.Vector2(-n.y, n.x) * self.omega_sign
            radial = clamp((dist - 300) / 300, -1.0, 1.0)
            target = (n * radial + tang * 0.85).normalize() * self.speed
            self.vel += (target - self.vel) * min(1.0, 1.8 * dt)
            self.pos += self.vel * dt
        self.pos.x = clamp(self.pos.x, self.world.arena.left + self.radius, self.world.arena.right - self.radius)
        self.pos.y = clamp(self.pos.y, self.world.arena.top + self.radius, self.world.arena.bottom - self.radius)

        self.rot += dt * (0.5 + 0.25 * self.phase)
        self.core_spin += dt * 2.2

        # Cambio de fase
        f = self.hp / self.max_hp
        if self.phase == 1 and f < 0.66:
            self.enter_phase(2, world)
        elif self.phase == 2 and f < 0.33:
            self.enter_phase(3, world)

        # Patrones
        if self.timer <= 0.0 and self.invuln_t <= 0.0:
            self.choose_pattern(world, dist)

    def enter_phase(self, phase: int, world) -> None:
        self.phase = phase
        self.invuln_t = 1.1
        self.color = [C.GOLD, C.ORANGE, C.RED][phase - 1]
        world.announce(f"FASE {phase}", C.RED, 1.1)
        world.fx.flash = 0.5
        world.fx.flash_color = C.RED
        world.fx.shake.add(16.0)
        world.audio.play("boss", 0.9)
        self.burst_pattern(world, count=20, speed=280)
        # Refuerzos
        for i in range(3 + phase):
            a = TAU * i / (3 + phase)
            e = Chaser(world, self.pos.x + math.cos(a) * 90, self.pos.y + math.sin(a) * 90,
                       world.hp_mul, world.spd_mul)
            e.vel = pygame.Vector2(math.cos(a), math.sin(a)) * 260
            world.enemies.append(e)
        self.timer = 1.4

    def choose_pattern(self, world, dist: float) -> None:
        options = ["radial", "aimed", "spiral"]
        if self.phase >= 2:
            options += ["spiral", "wobble"]
        if self.phase >= 3:
            options += ["summon", "charge"]
        if dist < 260.0:
            options.append("charge")
        self.pattern = random.choice(options)
        self.pattern_t = 0.0
        self.timer = {
            "radial": 2.2, "aimed": 1.5, "spiral": 1.9,
            "wobble": 2.4, "summon": 2.6, "charge": 2.4,
        }[self.pattern] / (1.0 + 0.08 * (self.phase - 1))
        self.state = "charge" if self.pattern == "charge" else "orbit"
        if self.pattern == "charge":
            d = self.to_player(world)
            self.vel = safe_normalize(d) * 620.0
            world.fx.shake.add(8.0)
            world.audio.play("dash", 0.7)

    def run_pattern(self, dt: float, world) -> None:
        self.pattern_t -= dt
        p = self.pattern

        if p == "spiral":
            self.spiral_angle += dt * 5.2
            self.burst_cd -= dt
            if self.burst_cd <= 0.0:
                self.burst_cd = 0.10
                arms = 1 + self.phase
                for i in range(arms):
                    a = self.spiral_angle + i * TAU / arms
                    self.spawn_bullet(world, a, 250.0, 7.0, C.AMBER)
            return

        self.burst_cd -= dt
        if self.burst_cd > 0.0:
            return

        if p == "radial":
            self.burst_cd = 0.55
            self.burst_pattern(world, count=14 + 4 * self.phase, speed=250.0)

        elif p == "aimed":
            self.burst_cd = 0.65
            d = self.to_player(world)
            base = math.atan2(d.y, d.x)
            for i in range(5):
                self.spawn_bullet(world, base + (i - 2) * 0.16, 400.0, 7.0, C.RED)

        elif p == "wobble":
            self.burst_cd = 0.70
            d = self.to_player(world)
            base = math.atan2(d.y, d.x)
            for i in range(10):
                a = base + (i - 5) * 0.24
                self.spawn_bullet(world, a, 250.0, 6.5, C.MAGENTA, wobble=2.6)

        elif p == "summon":
            self.burst_cd = 0.9
            for i in range(4):
                a = random.uniform(0, TAU)
                px = clamp(self.pos.x + math.cos(a) * 110, world.arena.left + 20, world.arena.right - 20)
                py = clamp(self.pos.y + math.sin(a) * 110, world.arena.top + 20, world.arena.bottom - 20)
                if world.enemy_near(px, py, 70):
                    continue
                world.enemies.append(Shard(world, px, py, 1.0, 1.4))

    def burst_pattern(self, world, count: int, speed: float) -> None:
        base = random.uniform(0, TAU)
        for i in range(count):
            self.spawn_bullet(world, base + i * TAU / count, speed, 7.0,
                              mix_color(C.AMBER, C.RED, 0.4))
        world.fx.ring(self.pos.x, self.pos.y, 30, 130, 0.4, C.AMBER, 4.0)
        world.audio.play("boom", 0.4, min_gap=0.1)

    def spawn_bullet(self, world, angle: float, speed: float, radius: float,
                     color: Color, wobble: float = 0.0) -> None:
        x = self.pos.x + math.cos(angle) * (self.radius * 0.8)
        y = self.pos.y + math.sin(angle) * (self.radius * 0.8)
        world.enemy_bullets.append(
            EnemyBullet(x, y, math.cos(angle) * speed, math.sin(angle) * speed,
                        radius, color, ttl=5.0, damage=11.0, wobble=wobble)
        )

    def update(self, dt: float, world) -> None:
        super().update(dt, world)
        if self.state != "charge":
            self.run_pattern(dt, world)

    # -- daño -----------------------------------------------------------------
    def damage(self, amount: float, world, knock=None) -> bool:
        if self.invuln_t > 0.0:
            world.fx.particles.burst(self.pos, 3, C.WHITE, speed=(60, 180), size=(1.5, 3),
                                     ttl=(0.1, 0.2), glow=0.8)
            return False
        return super().damage(amount, world, None)

    def on_death(self, world) -> None:
        world.fx.boom(self.pos, C.RED, 3.4, sparks=40, debris=22, smoke=14)
        world.fx.flash = 0.85
        world.fx.flash_color = C.WHITE
        world.fx.shake.add(30.0)
        world.fx.hitstop = max(world.fx.hitstop, 0.28)
        world.audio.play("boom_big", 1.0)
        # Lluvia de fragmentos
        for _ in range(10):
            a = random.uniform(0, TAU)
            d = random.uniform(0, 150)
            world.fx.particles.flash(
                pygame.Vector2(self.pos.x + math.cos(a) * d, self.pos.y + math.sin(a) * d),
                random.choice([C.GOLD, C.ORANGE, C.RED]), 30.0)
        world.register_kill(self, boss=True)

    # -- draw -----------------------------------------------------------------
    def draw(self, surf: pygame.Surface, glow: pygame.Surface, world) -> None:
        cx, cy = int(self.pos.x), int(self.pos.y)
        blink = self.invuln_t > 0.0 and int(self.invuln_t * 18) % 2 == 0
        base = C.WHITE if blink else self.color
        core = mix_color(base, C.RED, 0.3 + 0.2 * math.sin(world.time * 6))

        # Aura
        pygame.draw.circle(surf, with_alpha(base, 13), (cx, cy), int(self.radius * 1.5))
        glow_dot(glow, self.pos, self.radius * 1.9, base, 0.26)

        # Anillos contrarrotantes
        for i in range(3):
            rr = self.radius * (1.25 + i * 0.28)
            a = self.core_spin * (1 + i * 0.5) * (1 if i % 2 == 0 else -1)
            w = 3 if i == 1 else 2
            pts = [
                (int(cx + math.cos(a + k * TAU / 12) * rr), int(cy + math.sin(a + k * TAU / 12) * rr))
                for k in range(12)
            ]
            pygame.draw.polygon(surf, with_alpha(base, 150), pts, w)
            for k in range(0, 12, 4):
                kk = (k + int(a / (TAU / 12))) % 12
                px = cx + math.cos(a + kk * TAU / 12) * rr
                py = cy + math.sin(a + kk * TAU / 12) * rr
                pygame.draw.circle(surf, C.WHITE, (int(px), int(py)), 3)
                glow_dot(glow, (px, py), 9, base, 0.5)

        # Cuerpo hexagonal
        pts = shape_polygon(self.pos, self.radius * 0.82, 6, self.rot)
        pygame.draw.polygon(surf, with_alpha(C.NIGHT, 210), pts)
        pygame.draw.polygon(surf, base, pts, 3)
        glow_poly(glow, pts, base, 6.0, 1.0)

        # Núcleo pulsante
        pr = self.radius * (0.30 + 0.05 * math.sin(world.time * 8))
        pygame.draw.circle(surf, with_alpha(core, 90), (cx, cy), int(pr * 1.9))
        pygame.draw.circle(surf, base, (cx, cy), int(pr), 2)
        pygame.draw.circle(surf, C.WHITE, (cx, cy), max(2, int(pr * 0.45)))
        glow_dot(glow, self.pos, pr * 1.8, core, 0.7)


# --- Recogidas --------------------------------------------------------------
PICKUP_STYLE = {
    "vida": (C.LIME, "+"),
    "escudo": (C.ICE, "O"),
    "arma": (C.AMBER, "W"),
    "nuke": (C.MAGENTA, "X"),
    "overdrive": (C.GOLD, ">>"),
}


class Pickup:
    __slots__ = ("pos", "kind", "radius", "age", "ttl", "vel", "taken")

    def __init__(self, x: float, y: float, kind: str, vel: pygame.Vector2 | None = None) -> None:
        self.pos = pygame.Vector2(x, y)
        self.kind = kind
        self.radius = 13.0
        self.age = 0.0
        self.ttl = 11.0
        self.vel = vel if vel is not None else pygame.Vector2()
        self.taken = False

    def update(self, dt: float, world) -> None:
        self.age += dt
        self.ttl -= dt
        p = world.player
        if not p.dead:
            d = p.pos - self.pos
            dist = d.length()
            if dist < 150.0:
                self.vel += safe_normalize(d) * (900.0 * (1.0 - dist / 150.0)) * dt
            elif dist < 40.0:
                self.taken = True
        self.vel *= 0.94 ** (dt * 60)
        self.pos += self.vel * dt
        self.pos.x = clamp(self.pos.x, world.arena.left + 10, world.arena.right - 10)
        self.pos.y = clamp(self.pos.y, world.arena.top + 10, world.arena.bottom - 10)

    def draw(self, surf: pygame.Surface, glow: pygame.Surface, world) -> None:
        if self.ttl < 3.0 and int(self.ttl * 8) % 2 == 0:
            return
        color, glyph = PICKUP_STYLE[self.kind]
        bob = math.sin(self.age * 4.0) * 2.5
        c = pygame.Vector2(self.pos.x, self.pos.y + bob)
        r = self.radius

        pygame.draw.circle(surf, with_alpha(color, 45), (int(c.x), int(c.y)), int(r * 1.9))
        pygame.draw.circle(surf, with_alpha(color, 60), (int(c.x), int(c.y)), int(r * 1.25))
        pygame.draw.circle(surf, color, (int(c.x), int(c.y)), int(r), 2)
        glow_dot(glow, c, r * 1.7, color, 0.6)

        # Glifo
        rot = self.age * 1.6
        if self.kind == "nuke" or self.kind == "overdrive":
            pts = [
                (int(c.x + math.cos(rot + k * TAU / 6) * r * 0.55),
                 int(c.y + math.sin(rot + k * TAU / 6) * r * 0.55))
                for k in range(6)
            ]
            pygame.draw.polygon(surf, color, pts, 2)
        else:
            f = _glyph_font(int(r * 1.9))
            img = f.render(glyph, True, C.WHITE)
            surf.blit(img, img.get_rect(center=(int(c.x), int(c.y + 1))))

        # Barrita de tiempo restante
        f = clamp(self.ttl / 11.0, 0.0, 1.0)
        w = int(r * 2)
        x = int(c.x - w / 2)
        y = int(c.y + r + 5)
        pygame.draw.rect(surf, with_alpha(C.BLACK, 150), (x, y, w, 3))
        pygame.draw.rect(surf, color, (x, y, int(w * f), 3))


ENEMY_CLASSES = {
    "zancudo": Chaser,
    "escupidor": Shooter,
    "orbitador": Orbiter,
    "bruto": Tank,
    "mitosis": Splitter,
    "esquirla": Shard,
}
