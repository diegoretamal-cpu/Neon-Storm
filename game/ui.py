"""Interfaz: tipografías, fondo animado, HUD, menús y superposiciones."""

from __future__ import annotations

import math
import os
import random

import pygame

from . import config as C
from . import weapons as W
from .fx import glow_dot, glow_line, glow_poly, grect
from .render import blend_text, dim, tint
from .utils import (
    TAU,
    Color,
    clamp,
    ease_out_back,
    ease_out_cubic,
    lerp,
    mix_color,
    rand_range,
    scale_color,
    with_alpha,
)

# --- Tipografías ------------------------------------------------------------
_TITLE_FONTS = ("bahnschrift", "agencyfb", "framd", "segoeuiblack", "arialbd", "impact")
_HUD_FONTS = ("bahnschrift", "segoeui", "tahoma", "arial")
_MONO_FONTS = ("consolas", "cour", "lucon", "dejavusansmono")

FAMILIES = {
    "title": _TITLE_FONTS,
    "hud": _HUD_FONTS,
    "mono": _MONO_FONTS,
}

_PATHS: dict[str, str | None] = {}
_CACHE: dict[tuple[str, int], "GFont"] = {}


def _family_path(key: str) -> str | None:
    if key not in _PATHS:
        found = None
        for name in FAMILIES.get(key, ()):
            try:
                p = pygame.font.match_font(name)
            except Exception:
                p = None
            if p:
                found = p
                break
        _PATHS[key] = found
    return _PATHS[key]


class GFont:
    """Tipografía con caché y derivados de tamaño (pygame-ce no tiene copy())."""

    __slots__ = ("key", "size", "_font", "_path")

    def __init__(self, key: str, size: int) -> None:
        self.key = key
        self.size = int(size)
        self._path = _family_path(key)
        try:
            self._font = (pygame.font.Font(self._path, self.size) if self._path
                          else pygame.font.Font(None, self.size))
        except (pygame.error, TypeError):
            self._font = pygame.font.Font(None, self.size)

    def at(self, size: int) -> "GFont":
        size = max(6, int(size))
        key = (self.key, size)
        f = _CACHE.get(key)
        if f is None:
            f = GFont(self.key, size)
            _CACHE[key] = f
        return f

    def scaled(self, factor: float) -> "GFont":
        return self.at(int(self.size * factor))

    # -- delegación -----------------------------------------------------------
    def render(self, txt, antialias=True, color=(255, 255, 255), background=None):
        return self._font.render(txt, antialias, color, background)

    def get_height(self) -> int:
        return self._font.get_height()

    def get_width(self, txt) -> int:
        return self._font.size(txt)[0]

    def measure(self, txt) -> tuple[int, int]:
        return self._font.size(txt)

    def set_bold(self, v: bool) -> None:
        self._font.set_bold(v)

    def __repr__(self) -> str:  # pragma: no cover - depuración
        return f"GFont({self.key!r}, {self.size})"


def get_font(key: str, size: int) -> GFont:
    k = (key, int(size))
    f = _CACHE.get(k)
    if f is None:
        f = GFont(key, int(size))
        _CACHE[k] = f
    return f


def glow_text(
    glow: pygame.Surface,
    font: GFont,
    txt: str,
    color: Color,
    center: tuple[int, int],
    intensity: float = 1.0,
) -> None:
    """Escribe el texto reducido en el buffer de bloom."""
    if intensity <= 0.02:
        return
    small = font.at(max(7, font.size // C.GLOW_DIV))
    img = small.render(txt, True, scale_color(color, intensity))
    glow.blit(img, img.get_rect(center=center))


def draw_text(
    surf: pygame.Surface,
    font: GFont,
    txt: str,
    color: Color,
    pos: tuple[float, float],
    *,
    align: str = "center",
    alpha: int = 255,
    glow: pygame.Surface | None = None,
    glow_amount: float = 0.0,
    shadow: bool = True,
) -> pygame.Rect:
    rect = blend_text(surf, font, txt, color, pos, align=align, alpha=alpha, shadow=shadow)
    if glow is not None and glow_amount > 0.0:
        glow_text(glow, font, txt, color, rect.center, glow_amount)
    return rect


def _place(img: pygame.Surface, pos, align: str) -> pygame.Rect:
    from .render import place
    return place(img, pos, align)


def panel(
    surf: pygame.Surface,
    rect: pygame.Rect,
    *,
    fill: Color = (9, 6, 24),
    fill_alpha: int = 205,
    border: Color = C.INDIGO,
    border_alpha: int = 170,
    border_w: int = 2,
    radius: int = 16,
    glow: pygame.Surface | None = None,
) -> None:
    pygame.draw.rect(surf, with_alpha(fill, fill_alpha), rect, border_radius=radius)
    pygame.draw.rect(surf, with_alpha(border, border_alpha), rect, width=border_w,
                     border_radius=radius)
    if glow is not None:
        r = grect(rect.inflate(6, 6))
        pygame.draw.rect(glow, scale_color(border, 0.30), r, width=1,
                         border_radius=max(1, (radius + 3) // C.GLOW_DIV))


def bar(
    surf: pygame.Surface,
    rect: pygame.Rect,
    fraction: float,
    color: Color,
    *,
    bg: Color = (24, 16, 48),
    segments: int = 0,
    radius: int = 5,
    glow: pygame.Surface | None = None,
) -> None:
    fraction = clamp(fraction, 0.0, 1.0)
    pygame.draw.rect(surf, bg, rect, border_radius=radius)
    inner = rect.inflate(-4, -4)
    fw = int(inner.width * fraction)
    if fw > 2:
        col = mix_color(color, C.WHITE, 0.25 * (1.0 - fraction))
        r = pygame.Rect(inner.x, inner.y, fw, inner.height)
        pygame.draw.rect(surf, col, r, border_radius=max(1, radius - 2))
        pygame.draw.rect(
            surf, with_alpha(C.WHITE, 70),
            pygame.Rect(r.x + 2, r.y + 1, max(1, r.width - 4), max(1, r.height // 3)),
            border_radius=2,
        )
        if glow is not None:
            gw = grect(rect.inflate(4, 4))
            pygame.draw.rect(glow, scale_color(col, 0.55), gw, width=1,
                             border_radius=max(1, (radius + 1) // C.GLOW_DIV))
    if segments > 1:
        for i in range(1, segments):
            x = inner.x + int(inner.width * i / segments)
            pygame.draw.line(surf, (6, 4, 16), (x, inner.y), (x, inner.bottom), 1)


# --- Fondo ------------------------------------------------------------------
class Background:
    """Cielo degradado + rejilla en movimiento + estrellas con parallax."""

    def __init__(self) -> None:
        w, h = C.LOGICAL_W, C.LOGICAL_H
        self.base = pygame.Surface((w, h)).convert()
        for y in range(h):
            t = y / (h - 1)
            if t < 0.55:
                c = mix_color(C.NIGHT_TOP, C.NIGHT, t / 0.55)
            else:
                c = mix_color(C.NIGHT, C.BLACK, (t - 0.55) / 0.45)
            pygame.draw.line(self.base, c, (0, y), (w, y))

        # Halos de color en las esquinas superiores
        for cx, cy, col, rad in (
            (160, 40, C.MAGENTA, 420),
            (1130, 20, C.CYAN, 460),
            (640, 760, C.VIOLET, 520),
        ):
            layer = pygame.Surface((w, h), pygame.SRCALPHA)
            for i in range(22, 0, -1):
                t = i / 22.0
                r = int(rad * t)
                a = int(30 * (1.0 - t) ** 1.5)
                pygame.draw.circle(layer, with_alpha(col, a), (cx, cy), r)
            self.base.blit(layer, (0, 0))

        self.stars: list[tuple[float, float, float, float, float]] = []
        for _ in range(110):
            self.stars.append((
                random.uniform(0, w), random.uniform(0, h),
                random.uniform(0.6, 2.1), random.uniform(4.0, 26.0),
                random.uniform(0, TAU),
            ))

        # Vineta radial real (se calcula pequeña y se escala sin serrilhado)
        vw, vh = 160, 90
        small = pygame.Surface((vw, vh), pygame.SRCALPHA)
        cx, cy = (vw - 1) / 2.0, (vh - 1) / 2.0
        diag = math.hypot(cx, cy)
        for y in range(vh):
            for x in range(vw):
                d = math.hypot(x - cx, y - cy) / diag
                t = clamp((d - 0.34) / 0.66, 0.0, 1.0)
                a = int(196 * t * t * t)
                if a:
                    small.set_at((x, y), (3, 2, 10, a))
        self.vignette = pygame.transform.smoothscale(small, (w, h))
        self.vignette = self.vignette.convert_alpha()

        # Scanlines muy suaves, pre-compuestas con la viñeta en una sola capa
        self.scanlines = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(0, h, 3):
            pygame.draw.line(self.scanlines, (0, 0, 0, 14), (0, y), (w, y))
        self.ground = self.vignette.copy()
        self.ground.blit(self.scanlines, (0, 0))
        del self.scanlines

    def draw(self, surf: pygame.Surface, glow: pygame.Surface, time: float,
             arena: bool = True, base: bool = True, level: int = 2) -> None:
        if base:
            surf.blit(self.base, (0, 0))

        # Rejilla en perspectiva falsa (líneas que se deslizan)
        step = 64
        off = (time * 26.0) % step
        alpha = 34
        for x in range(-step, C.LOGICAL_W + step, step):
            a = alpha + 12 * (0.5 + 0.5 * math.sin(time * 0.8 + x * 0.01))
            pygame.draw.line(surf, with_alpha(C.GRID, int(a)),
                             (x - off, 0), (x - off, C.LOGICAL_H), 1)
        for y in range(-step, C.LOGICAL_H + step, step):
            oy = y + off * 0.35
            a = alpha + 10 * (0.5 + 0.5 * math.cos(time * 0.6 + y * 0.013))
            pygame.draw.line(surf, with_alpha(C.GRID, int(a)),
                             (0, oy), (C.LOGICAL_W, oy), 1)

        # Estrellas (menos cantidad cuanto menor sea la calidad)
        stars = self.stars if level >= 2 else self.stars[:(110 if level == 1 else 45)]
        for sx, sy, sr, sp, ph in stars:
            tw = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(time * 2.0 + ph))
            py = (sy - time * sp) % (C.LOGICAL_H + 20) - 10
            col = mix_color(C.ICE, C.WHITE, tw)
            pygame.draw.circle(surf, with_alpha(col, int(70 + 130 * tw)),
                               (int(sx), int(py)), max(1, int(sr)))
            if sr > 1.5 and level > 0:
                glow_dot(glow, (sx, py), sr * 4, col, 0.16 * tw)

        if arena:
            self.draw_arena(surf, glow, time)

    def draw_ground_overlay(self, surf: pygame.Surface) -> None:
        """Viñeta + scanlines, aplicadas bajo las entidades y la HUD."""
        surf.blit(self.ground, (0, 0))

    def draw_arena(self, surf: pygame.Surface, glow: pygame.Surface, time: float) -> None:
        a = C.ARENA
        pulse = 0.5 + 0.5 * math.sin(time * 1.6)

        pygame.draw.rect(surf, with_alpha(C.FLOOR, 190), a, border_radius=18)

        # Rejilla interior
        clip = a.inflate(-10, -10)
        step = 48
        off = (time * 10.0) % step
        for x in range(clip.left, clip.right + 1, step):
            pygame.draw.line(surf, with_alpha(C.GRID, 26), (x, clip.top), (x, clip.bottom), 1)
        for y in range(clip.top, clip.bottom + 1, step):
            pygame.draw.line(surf, with_alpha(C.GRID, 26), (clip.left, y), (clip.right, y), 1)
        # Marca central
        cc = (a.centerx, a.centery)
        for rr, al in ((70, 30), (110, 18)):
            pygame.draw.circle(surf, with_alpha(C.INDIGO, al), cc, rr, 1)
        for i in range(4):
            ang = i * TAU / 4 + time * 0.15
            pygame.draw.line(
                surf, with_alpha(C.INDIGO, 40),
                (cc[0] + math.cos(ang) * 60, cc[1] + math.sin(ang) * 60),
                (cc[0] + math.cos(ang) * 120, cc[1] + math.sin(ang) * 120), 2)

        # Borde
        pygame.draw.rect(surf, with_alpha(C.FLOOR_EDGE, 150 + int(70 * pulse)), a, 2, border_radius=18)
        glow_line(glow, (a.left + 18, a.top), (a.right - 18, a.top), C.VIOLET, 6, 0.30 + 0.1 * pulse)
        glow_line(glow, (a.left + 18, a.bottom), (a.right - 18, a.bottom), C.CYAN, 6, 0.22)

    def draw_overlay(self, surf: pygame.Surface) -> None:
        surf.blit(self.vignette, (0, 0))
        surf.blit(self.scanlines, (0, 0))


# --- HUD --------------------------------------------------------------------
class UI:
    def __init__(self) -> None:
        self.f_title = get_font("title", 84)
        self.f_sub = get_font("title", 30)
        self.f_hud = get_font("hud", 20)
        self.f_hud_b = get_font("title", 30)
        self.f_mono = get_font("mono", 18)
        self.f_mono_b = get_font("mono", 26)
        self.f_big = get_font("title", 62)
        self.f_small = get_font("hud", 16)
        self.f_float = get_font("title", 20)
        self.bg = Background()
        self._red_vignette = self._make_vignette((255, 26, 66), 150)
        self._dv_cache: tuple[int, pygame.Surface] | None = None

    # -- utilidades -----------------------------------------------------------
    @staticmethod
    def _make_vignette(color: Color, peak: int) -> pygame.Surface:
        """Viñeta radial pre-renderizada (se atenúa con `dim`, sin coste extra)."""
        w, h = 160, 90
        small = pygame.Surface((w, h), pygame.SRCALPHA)
        cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
        diag = math.hypot(cx, cy)
        for y in range(h):
            for x in range(w):
                d = math.hypot(x - cx, y - cy) / diag
                t = clamp((d - 0.42) / 0.58, 0.0, 1.0)
                a = int(peak * t * t)
                if a:
                    small.set_at((x, y), (color[0], color[1], color[2], a))
        return pygame.transform.smoothscale(small, (C.LOGICAL_W, C.LOGICAL_H)).convert_alpha()

    # -- HUD de juego ---------------------------------------------------------
    def draw_hud(
        self,
        surf: pygame.Surface,
        glow: pygame.Surface,
        world,
        fps: int = 0,
        quality: int = 2,
    ) -> None:
        p = world.player
        t = world.time

        # --- barra superior
        top = pygame.Rect(0, 0, C.LOGICAL_W, C.HUD_H)
        pygame.draw.rect(surf, with_alpha((7, 5, 20), 220), top)
        pygame.draw.line(surf, with_alpha(C.INDIGO, 120), (0, C.HUD_H - 1),
                         (C.LOGICAL_W, C.HUD_H - 1), 1)
        # Acento animado
        sweep = (t * 190.0) % (C.LOGICAL_W + 260) - 130
        pygame.draw.line(surf, with_alpha(C.CYAN, 150), (sweep, C.HUD_H - 2),
                         (sweep + 130, C.HUD_H - 2), 2)

        # --- vida
        hp_rect = pygame.Rect(22, 26, 296, 18)
        hf = clamp(p.hp / p.max_hp, 0, 1)
        col = C.LIME if hf > 0.5 else (C.AMBER if hf > 0.25 else C.RED)
        draw_text(surf, self.f_small, "INTEGRIDAD", C.ICE, (22, 7), align="topleft")
        bar(surf, hp_rect, hf, col, segments=10, glow=glow)
        draw_text(surf, self.f_hud_b, f"{int(p.hp)}", col, (326, 35), align="midleft")

        # --- escudo
        if p.shield > 0.0:
            sf = clamp(p.shield / p.max_shield, 0, 1)
            bar(surf, pygame.Rect(22, 50, 296, 8), sf, C.ICE, glow=glow)
            draw_text(surf, self.f_small, f"ESCUDO {int(p.shield)}", C.ICE, (326, 54),
                      align="midleft")

        # --- oleada
        runner = world.runner
        wv = runner.wave_obj
        center_x = C.LOGICAL_W // 2
        label = f"OLEADA {max(1, runner.wave)}"
        draw_text(surf, self.f_hud_b, label, C.WHITE, (center_x, 18), glow=glow, glow_amount=0.5)
        if runner.state == "intro":
            sub = "PREPÁRATE"
            colw = C.GOLD
        elif runner.state == "fight":
            left = runner.alive
            sub = f"{left} {'ENEMIGO' if left == 1 else 'ENEMIGOS'}"
            colw = C.CYAN
        elif runner.state == "clear":
            sub = "OLEADA COMPLETADA"
            colw = C.LIME
        else:
            sub = wv.composition() if wv else ""
            colw = C.ICE
        draw_text(surf, self.f_small, sub, colw, (center_x, 40), glow=glow, glow_amount=0.25)
        pr = runner.progress()
        if runner.state in ("spawn", "fight"):
            bar(surf, pygame.Rect(center_x - 110, 58, 220, 6), pr, C.CYAN, radius=3)

        # --- marcador y combo
        sx = C.LOGICAL_W - 22
        draw_text(surf, self.f_small, "PUNTOS", C.ICE, (sx, 8), align="topright")
        draw_text(surf, self.f_mono_b, f"{world.score:07d}", C.WHITE, (sx, 24),
                  align="topright", glow=glow, glow_amount=0.35)
        fps_col = C.LIME if fps >= 55 else (C.AMBER if fps >= 40 else C.RED)
        stars = "·" * quality
        draw_text(surf, self.f_small, f"{fps:3d} FPS {stars}", fps_col,
                  (sx, 52), align="topright")

        combo = world.combo
        if combo > 1:
            ccol = [C.WHITE, C.LIME, C.AMBER, C.ORANGE, C.MAGENTA][min(4, combo // 3)]
            bob = 1.0 + 0.06 * math.sin(t * 9)
            f = self.f_big.at(int(self.f_big.size * bob))
            draw_text(surf, f, f"x{combo}", ccol, (sx, 66), align="topright",
                      glow=glow, glow_amount=0.6)
            cf = clamp(world.combo_timer / C.COMBO_WINDOW, 0, 1)
            bar(surf, pygame.Rect(sx - 90, 60, 90, 3), cf, ccol, radius=2)

        # --- arma
        wpn = p.weapon
        wy = C.LOGICAL_H - 34
        draw_text(surf, self.f_small, "ARMA", C.ICE, (22, wy - 18), align="topleft")
        draw_text(surf, self.f_hud_b, wpn.name, wpn.color, (22, wy),
                  align="topleft", glow=glow, glow_amount=0.4)
        if p.weapon_time > 0.0:
            bar(surf, pygame.Rect(22, wy + 4, 160, 5),
                p.weapon_time / max(1e-6, p.weapon_time_max), wpn.color, radius=2)
        if p.overdrive > 0.0:
            draw_text(surf, self.f_hud_b, "OVERDRIVE", C.GOLD, (22, wy - 46),
                      align="topleft", glow=glow, glow_amount=0.5)

        # --- rack de recarga del dash
        dw = p.dash_cd / C.DASH_COOLDOWN
        for i in range(6):
            on = i < int((1 - dw) * 6)
            pygame.draw.rect(surf, with_alpha(C.CYAN if on else C.INDIGO, 220 if on else 80),
                             (22 + i * 11, wy - 42, 8, 5), border_radius=2)

        # --- pista de enemigos restantes / aviso de jefe
        boss = world.boss
        if boss is not None and not boss.dead:
            self._boss_bar(surf, glow, boss, t)

        # --- avisos de estado
        if p.hp / p.max_hp < 0.3 and not p.dead:
            a = 60 + 50 * (0.5 + 0.5 * math.sin(t * 7))
            layer = pygame.Surface((C.LOGICAL_W, C.LOGICAL_H), pygame.SRCALPHA)
            pygame.draw.rect(layer, (255, 40, 70, int(a * 0.5)),
                             pygame.Rect(0, 0, C.LOGICAL_W, C.LOGICAL_H), 60)
            surf.blit(layer, (0, 0))

    def _boss_bar(self, surf, glow, boss, t: float) -> None:
        r = pygame.Rect(C.LOGICAL_W // 2 - 300, C.HUD_H + 10, 600, 16)
        f = clamp(boss.hp / boss.max_hp, 0, 1)
        pygame.draw.rect(surf, with_alpha((7, 5, 20), 210), r.inflate(8, 8), border_radius=7)
        bar(surf, r, f, mix_color(boss.color, C.RED, 0.35), radius=4, glow=glow)
        # Marcas de fase
        for phase_m in (0.33, 0.66):
            x = r.x + int(r.width * phase_m)
            pygame.draw.line(surf, with_alpha(C.WHITE, 170), (x, r.y - 3), (x, r.bottom + 3), 2)
        name = f"CENTINELA · FASE {boss.phase}"
        draw_text(surf, self.f_small, name, boss.color, (r.centerx, r.y - 10), glow=glow,
                  glow_amount=0.4)

    # -- anuncios -------------------------------------------------------------
    def draw_announcements(self, surf, glow, world) -> None:
        t = world.time
        for ann in world.announcements:
            if ann.delay > 0.0:
                continue
            k = ann.age / ann.dur
            if ann.big:
                # escala con rebote
                s = ease_out_back(clamp(k / 0.28, 0, 1))
                f = self.f_big.at(int(self.f_big.size * lerp(0.55, 1.0, s)))
                a = int(255 * clamp(min(k / 0.12, (1 - k) / 0.22), 0, 1))
                y = C.LOGICAL_H * 0.34 + ann.offset
                draw_text(surf, f, ann.text, ann.color, (C.LOGICAL_W / 2, y), alpha=a,
                          glow=glow, glow_amount=0.75 * (a / 255))
                w = int(f.measure(ann.text)[0] * s)
                pygame.draw.line(surf, with_alpha(ann.color, int(a * 0.7)),
                                 (C.LOGICAL_W / 2 - w / 2, y + 24), (C.LOGICAL_W / 2 + w / 2, y + 24), 2)
            else:
                a = int(255 * clamp(min(k / 0.15, (1 - k) / 0.25), 0, 1))
                y = C.LOGICAL_H * 0.34 + 58 + ann.offset
                draw_text(surf, self.f_hud, ann.text, ann.color,
                          (C.LOGICAL_W / 2, y), alpha=a, glow=glow, glow_amount=0.3 * (a / 255))

    # -- superposiciones ------------------------------------------------------
    def draw_damage_vignette(self, surf, world) -> None:
        p = world.player
        low = 1.0 - clamp(p.hp / p.max_hp, 0, 1)
        amount = max(world.fx.vignette_pulse, (low - 0.45) * 1.1 if low > 0.45 else 0.0)
        if amount <= 0.015:
            return
        # `dim()` cuesta ~3 operaciones a pantalla completa: se cachea por
        # tramos de intensidad para no repetirlo cada frame.
        key = int(clamp(amount, 0, 1) * 10)
        cache = self._dv_cache
        if cache is None or cache[0] != key:
            self._dv_cache = (key, dim(self._red_vignette, key / 10.0))
        surf.blit(self._dv_cache[1], (0, 0))

    def draw_flash(self, surf, world) -> None:
        if world.fx.flash <= 0.01:
            return
        tint(surf, world.fx.flash_color, int(clamp(world.fx.flash, 0, 1) * 120))
