"""Pantallas: menú, pausa, fin de partida y victoria."""

from __future__ import annotations

import math
import time as _time

import pygame

from . import config as C
from . import weapons as W
from .render import tint
from .ui import bar, draw_text, glow_text, panel
from .utils import (
    TAU,
    clamp,
    ease_out_back,
    ease_out_cubic,
    lerp,
    mix_color,
    pulse,
    with_alpha,
)

CONTROLS = (
    ("WASD / FLECHAS", "moverse"),
    ("RATÓN", "apuntar"),
    ("CLIC IZQ. / J", "disparar"),
    ("ESPACIO / SHIFT", "dash"),
    ("P / ESC", "pausa"),
    ("M", "silenciar"),
)


def _chrome_title(surf, glow, font, text: str, center, time: float, scale: float = 1.0):
    """Titular con desplazamiento cromático y pulso."""
    cx, cy = center
    size = font.get_height()
    off = max(1, int(3 * scale * pulse(time, 2.0)))
    for dx, col, i in ((-off, C.MAGENTA, 0.55), (off, C.CYAN, 0.55)):
        draw_text(surf, font, text, col, (cx + dx, cy), shadow=False,
                  glow=glow, glow_amount=0.35 * i)
    draw_text(surf, font, text, C.WHITE, (cx, cy), glow=glow, glow_amount=0.8)


def draw_menu(ui, surf: pygame.Surface, glow: pygame.Surface, state, best: dict) -> None:
    t = state.time
    W_, H_ = C.LOGICAL_W, C.LOGICAL_H

    # Marco decorativo
    cx, cy = W_ // 2, 168
    for i, (rr, spd, col) in enumerate(((190, 0.22, C.INDIGO), (140, -0.35, C.VIOLET), (96, 0.5, C.MAGENTA))):
        a = t * spd
        pts = [
            (int(cx + math.cos(a + k * TAU / 64) * rr), int(cy + math.sin(a + k * TAU / 64) * rr * 0.42))
            for k in range(64)
        ]
        pygame.draw.polygon(surf, with_alpha(col, 60), pts, 1)
        pygame.draw.circle(surf, with_alpha(col, 45), (cx, cy), int(rr * 0.42), 1)

    _chrome_title(surf, glow, ui.f_title, C.TITLE, (W_ // 2, 150), t)

    sub = "SHOOTER DE ARENA  ·  25 OLEADAS  ·  1 JUGADOR"
    draw_text(surf, ui.f_hud, sub, C.ICE, (W_ // 2, 205), glow=glow, glow_amount=0.3)
    pygame.draw.line(surf, with_alpha(C.CYAN, 120), (W_ // 2 - 300, 226), (W_ // 2 + 300, 226), 1)

    # --- Panel de controles
    pw, ph = 560, 226
    pr = pygame.Rect(0, 0, pw, ph)
    pr.center = (W_ // 2, 366)
    panel(surf, pr, fill=(8, 5, 22), fill_alpha=190, border=C.INDIGO, glow=glow)
    draw_text(surf, ui.f_hud_b, "CONTROLES", C.CYAN, (pr.centerx, pr.y + 24), glow=glow, glow_amount=0.35)
    pygame.draw.line(surf, with_alpha(C.INDIGO, 160), (pr.x + 30, pr.y + 42), (pr.right - 30, pr.y + 42))
    y = pr.y + 66
    for key, desc in CONTROLS:
        draw_text(surf, ui.f_mono, key, C.GOLD, (pr.x + 34, y), align="midleft")
        draw_text(surf, ui.f_hud, desc, C.ICE, (pr.right - 34, y), align="midright")
        y += 28

    # --- Mejor puntuación (u objetivo si es la primera partida)
    if best.get("score", 0) > 0:
        br = pygame.Rect(0, 0, 560, 60)
        br.center = (W_ // 2, 522)
        panel(surf, br, fill=(8, 5, 22), fill_alpha=170, border=C.VIOLET, glow=glow)
        draw_text(surf, ui.f_small, "MEJOR MARCADOR", C.ICE, (br.centerx, br.y + 16))
        draw_text(surf, ui.f_mono_b, f"{best['score']:07d}", C.GOLD,
                  (br.centerx, br.y + 40), glow=glow, glow_amount=0.4)
        draw_text(surf, ui.f_small, f"oleada {best.get('wave', 0)}", C.VIOLET,
                  (br.right - 20, br.y + 40), align="midright")
    else:
        br = pygame.Rect(0, 0, 560, 60)
        br.center = (W_ // 2, 522)
        panel(surf, br, fill=(8, 5, 22), fill_alpha=150, border=C.TEAL, glow=glow)
        draw_text(surf, ui.f_small, "OBJETIVO", C.ICE, (br.centerx, br.y + 16))
        draw_text(surf, ui.f_hud, "despeja las 25 oleadas y abate a los 5 centinelas",
                  C.CYAN, (br.centerx, br.y + 40))

    # --- Llamada a la acción
    blink = 0.55 + 0.45 * math.sin(t * 3.4)
    y = 600
    draw_text(surf, ui.f_hud_b, "PULSA  ENTER  PARA JUGAR", C.WHITE,
              (W_ // 2, y), glow=glow, glow_amount=0.6 * blink)
    draw_text(surf, ui.f_small,
              "o haz clic para empezar  ·  hecho en python + pygame-ce",
              mix_color(C.INDIGO, C.ICE, 0.4),
              (W_ // 2, y + 32))

    # Logo de armas
    xs = W_ // 2 - (len(W.WEAPONS) * 52) // 2
    for i, (wid, wpn) in enumerate(W.WEAPONS.items()):
        active = wid == "pulse"
        col = wpn.color
        bx = xs + i * 52
        r = pygame.Rect(0, 0, 44, 26)
        r.center = (bx + 22, 666)
        pygame.draw.rect(surf, with_alpha(col, 60 if not active else 110), r, 1, border_radius=6)
        draw_text(surf, ui.f_small, wpn.name[:3], col, r.center, glow=glow,
                  glow_amount=0.3 if active else 0.1)


def draw_pause(ui, surf, glow, state, world, best) -> None:
    tint(surf, (4, 2, 12), 190)

    r = pygame.Rect(0, 0, 480, 300)
    r.center = (C.LOGICAL_W // 2, C.LOGICAL_H // 2)
    panel(surf, r, fill=(9, 6, 26), fill_alpha=240, border=C.CYAN, glow=glow)
    draw_text(surf, ui.f_big, "PAUSA", C.WHITE, (r.centerx, r.y + 54), glow=glow, glow_amount=0.7)
    pygame.draw.line(surf, with_alpha(C.CYAN, 150), (r.x + 40, r.y + 84), (r.right - 40, r.y + 84))

    items = ("ENTER / ESC   continuar", "R   reiniciar partida", "M   silenciar audio", "Q   salir al menú")
    y = r.y + 116
    for i, txt in enumerate(items):
        col = C.WHITE if i == 0 else C.ICE
        draw_text(surf, ui.f_hud, txt, col, (r.centerx, y), align="center")
        y += 30

    p = world.player
    draw_text(surf, ui.f_small,
              f"oleada {world.runner.wave}  ·  {world.score} pts  ·  {int(p.hp)} integridad",
              C.VIOLET, (r.centerx, r.bottom - 26))


def _stat_row(surf, ui, x, y, label, value, color, w=460):
    draw_text(surf, ui.f_hud, label, C.ICE, (x, y), align="midleft")
    draw_text(surf, ui.f_mono_b, value, color, (x + w, y), align="midright")


def draw_end(ui, surf, glow, state, world, best, victory: bool) -> None:
    t = state.time
    tint(surf, (4, 2, 12), int(clamp(t * 0.9, 0, 1) * 205))

    k = ease_out_back(clamp((t - 0.15) / 0.5, 0, 1))
    title = "VICTORIA" if victory else "FIN DE LA PARTIDA"
    col = C.LIME if victory else C.RED
    w, h = 640, 452
    r = pygame.Rect(0, 0, int(w * lerp(0.88, 1.0, k)), int(h * lerp(0.88, 1.0, k)))
    r.center = (C.LOGICAL_W // 2, C.LOGICAL_H // 2)
    panel(surf, r, fill=(8, 5, 22), fill_alpha=240, border=col, glow=glow)

    scale = r.height / h
    f = ui.f_big.at(int(ui.f_big.size * lerp(0.7, 1.0, k)))
    draw_text(surf, f, title, col, (r.centerx, r.y + int(48 * scale)),
              glow=glow, glow_amount=0.8)
    y = r.y + int(94 * scale)
    pygame.draw.line(surf, with_alpha(col, 150), (r.x + int(48 * scale), y),
                     (r.right - int(48 * scale), y), 1)

    p = world.player
    acc = 0.0
    if p.shots:
        acc = clamp(world.kills_by_player / p.shots * 100.0, 0, 100)
    mins = int(world.run_time // 60)
    secs = int(world.run_time % 60)

    rows = (
        ("Oleada alcanzada", f"{world.runner.wave} / {C.TOTAL_WAVES}", C.CYAN),
        ("Puntuación", f"{world.score}", C.WHITE),
        ("Bajas", f"{world.kills}", C.LIME),
        ("Precisión", f"{acc:.0f}%", C.AMBER),
        ("Mejor racha", f"x{world.best_combo}", C.MAGENTA),
        ("Tiempo", f"{mins}:{secs:02d}", C.ICE),
    )
    y += int(36 * scale)
    left = r.x + int(56 * scale)
    width = r.width - int(112 * scale)
    for label, value, cl in rows:
        _stat_row(surf, ui, left, y, label, value, cl, w=width)
        y += int(36 * scale)

    if world.new_record:
        blink = 0.5 + 0.5 * math.sin(t * 6)
        draw_text(surf, ui.f_hud_b, "¡NUEVO RÉCORD!", C.GOLD, (r.centerx, y),
                  glow=glow, glow_amount=0.7 * blink)

    blink = 0.5 + 0.5 * math.sin(t * 3.4)
    draw_text(surf, ui.f_hud_b, "ENTER  para reintentar", C.WHITE,
              (r.centerx, r.bottom - int(44 * scale)), glow=glow, glow_amount=0.5 * blink)
    draw_text(surf, ui.f_small, "ESC  menú principal", C.ICE,
              (r.centerx, r.bottom - int(20 * scale)))
