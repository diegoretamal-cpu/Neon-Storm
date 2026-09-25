"""Pequeñas utilidades matemáticas y de color."""

from __future__ import annotations

import math
import random
from typing import Sequence

import pygame

TAU = math.tau

Color = tuple[int, int, int]
RGBA = tuple[int, int, int, int]

WHITE: Color = (238, 250, 255)


# --- Números -----------------------------------------------------------------
def clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def inv_lerp(a: float, b: float, v: float) -> float:
    return 0.0 if b == a else clamp((v - a) / (b - a), 0.0, 1.0)


def rand_range(a: float, b: float) -> float:
    return random.uniform(a, b)


def rand_int(a: int, b: int) -> int:
    return random.randint(a, b)


def chance(p: float) -> bool:
    return random.random() < p


def pick(seq: Sequence):
    return random.choice(seq)


def sign(v: float) -> float:
    return 1.0 if v > 0 else (-1.0 if v < 0 else 0.0)


def approach(current: float, target: float, delta: float) -> float:
    if current < target:
        return min(current + delta, target)
    return max(current - delta, target)


def damp(current: float, target: float, rate: float, dt: float) -> float:
    """Interpolación independiente del framerate."""
    return lerp(current, target, 1.0 - math.exp(-rate * dt))


# --- Ángulos ----------------------------------------------------------------
def angle_to(a: pygame.Vector2, b: pygame.Vector2) -> float:
    return math.atan2(b.y - a.y, b.x - a.x)


def angle_diff(a: float, b: float) -> float:
    """Diferencia mínima entre dos ángulos, en (-pi, pi]."""
    d = (b - a + math.pi) % TAU - math.pi
    return d


def rotate_towards(current: float, target: float, max_step: float) -> float:
    d = angle_diff(current, target)
    if abs(d) <= max_step:
        return target
    return current + max_step * sign(d)


# --- Curvas -----------------------------------------------------------------
def ease_out_cubic(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return 1.0 - (1.0 - t) ** 3


def ease_in_cubic(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return t * t * t


def ease_out_back(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    c1, c3 = 1.70158, 2.70158
    return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2


def ease_out_elastic(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    if t in (0.0, 1.0):
        return t
    c4 = TAU / 3.0
    return 2.0 ** (-9.0 * t) * math.sin((t * 10.0 - 0.75) * c4) + 1.0


def pulse(t: float, speed: float = 3.0) -> float:
    """0..1 oscilación senoidal suave."""
    return 0.5 + 0.5 * math.sin(t * speed)


# --- Color ------------------------------------------------------------------
def scale_color(c: Color, f: float) -> Color:
    return (
        int(clamp(c[0] * f, 0, 255)),
        int(clamp(c[1] * f, 0, 255)),
        int(clamp(c[2] * f, 0, 255)),
    )


def mix_color(a: Color, b: Color, t: float) -> Color:
    t = clamp(t, 0.0, 1.0)
    return (
        int(lerp(a[0], b[0], t)),
        int(lerp(a[1], b[1], t)),
        int(lerp(a[2], b[2], t)),
    )


def with_alpha(c: Color, a: int) -> RGBA:
    return (c[0], c[1], c[2], int(clamp(a, 0, 255)))


def shift_towards_white(c: Color, t: float) -> Color:
    return mix_color(c, WHITE, t)


# --- Geometría --------------------------------------------------------------
def circle_hits_rect(pos: pygame.Vector2, radius: float, rect: pygame.Rect) -> bool:
    closest_x = clamp(pos.x, rect.left, rect.right)
    closest_y = clamp(pos.y, rect.top, rect.bottom)
    dx = pos.x - closest_x
    dy = pos.y - closest_y
    return dx * dx + dy * dy <= radius * radius


def push_out_of_rect(pos: pygame.Vector2, radius: float, rect: pygame.Rect) -> pygame.Vector2:
    """Devuelve la posición corregida para que el círculo no solape el rect."""
    closest_x = clamp(pos.x, rect.left, rect.right)
    closest_y = clamp(pos.y, rect.top, rect.bottom)
    dx = pos.x - closest_x
    dy = pos.y - closest_y
    dist_sq = dx * dx + dy * dy
    if dist_sq >= radius * radius:
        return pos

    if dist_sq > 1e-6:
        dist = math.sqrt(dist_sq)
        nx, ny = dx / dist, dy / dist
    else:
        # Centro dentro del rect: empuja por el lado más cercano.
        left = abs(pos.x - rect.left)
        right = abs(rect.right - pos.x)
        top = abs(pos.y - rect.top)
        bottom = abs(rect.bottom - pos.y)
        m = min(left, right, top, bottom)
        if m == left:
            nx, ny = -1.0, 0.0
        elif m == right:
            nx, ny = 1.0, 0.0
        elif m == top:
            nx, ny = 0.0, -1.0
        else:
            nx, ny = 0.0, 1.0

    target = pygame.Vector2(closest_x + nx * radius, closest_y + ny * radius)
    return target


def random_point_in(rect: pygame.Rect, margin: int = 24) -> pygame.Vector2:
    return pygame.Vector2(
        rand_range(rect.left + margin, rect.right - margin),
        rand_range(rect.top + margin, rect.bottom - margin),
    )


def random_dir(angle: float = None, spread: float = TAU) -> pygame.Vector2:
    if angle is None:
        angle = rand_range(0.0, TAU)
    a = angle + rand_range(-spread / 2, spread / 2)
    return pygame.Vector2(math.cos(a), math.sin(a))


def length_dir(v: pygame.Vector2, max_len: float) -> pygame.Vector2:
    """Limita la longitud del vector sin alterar la dirección."""
    if v.length_squared() <= max_len * max_len or v.length_squared() == 0:
        return v
    return v.normalize() * max_len


def safe_normalize(v: pygame.Vector2) -> pygame.Vector2:
    if v.length_squared() < 1e-9:
        return pygame.Vector2(0.0, 0.0)
    return v.normalize()
