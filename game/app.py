"""Bucle principal, ventana, estados y pipeline de render."""

from __future__ import annotations

import json
import math
import os
import sys
import types
from typing import Optional

import pygame

from . import config as C
from . import screens
from .audio import Audio
from .render import Layers
from .ui import UI, bar, draw_text, glow_text
from .utils import (
    TAU,
    clamp,
    mix_color,
    pulse,
    scale_color,
    with_alpha,
)
from .world import World

SAVE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), C.SAVE_PATH)

MENU, PLAYING, PAUSED, END = "menu", "playing", "paused", "end"


class Game:
    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        pygame.init()

        flags = 0 if headless else pygame.RESIZABLE
        self.screen = pygame.display.set_mode((C.LOGICAL_W, C.LOGICAL_H), flags)
        pygame.display.set_caption(C.CAPTION)
        pygame.display.set_icon(self._make_icon())

        self.canvas = pygame.Surface((C.LOGICAL_W, C.LOGICAL_H)).convert()
        self.layers = Layers(C.LOGICAL_W, C.LOGICAL_H)
        self.glow = pygame.Surface(
            (C.LOGICAL_W // C.GLOW_DIV, C.LOGICAL_H // C.GLOW_DIV)
        ).convert()
        self.glow_big = pygame.Surface((C.LOGICAL_W, C.LOGICAL_H)).convert()

        self.audio = Audio()
        self.audio.init()

        self.ui = UI()
        self.world = World(self.audio)
        self.clock = pygame.time.Clock()
        self.running = True
        self.state = MENU
        self.time = 0.0
        self.screen_time = 0.0
        self.win_size = (C.LOGICAL_W, C.LOGICAL_H)
        self.fullscreen = False

        self.mouse_pos = pygame.Vector2(C.LOGICAL_W / 2, C.LOGICAL_H / 2)
        self.mouse_moved_at = -99.0
        self.muzzle = 0.0

        self.best = self._load_best()
        self.pillars = C.pillars()
        self.fonts_float = {
            16: self.ui.f_float,
            18: self.ui.f_float,
            20: self.ui.f_float,
            22: self.ui.f_hud_b,
            24: self.ui.f_hud_b,
            28: self.ui.f_big,
        }
        self._state_ns = types.SimpleNamespace(time=0.0)

    # -- recursos -------------------------------------------------------------
    def _make_icon(self) -> pygame.Surface:
        s = pygame.Surface((32, 32), pygame.SRCALPHA)
        pygame.draw.polygon(s, C.CYAN, [(16, 3), (27, 27), (16, 21), (5, 27)])
        pygame.draw.polygon(s, C.WHITE, [(16, 10), (21, 24), (16, 20), (11, 24)])
        return s

    def _load_best(self) -> dict:
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {"score": int(data.get("score", 0)), "wave": int(data.get("wave", 0)),
                        "kills": int(data.get("kills", 0)), "plays": int(data.get("plays", 0))}
        except (OSError, ValueError):
            pass
        return {"score": 0, "wave": 0, "kills": 0, "plays": 0}

    def _save_best(self) -> None:
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.best, f, indent=2)
        except OSError:
            pass

    # -- bucle ----------------------------------------------------------------
    def run(self, auto_frames: int = 0, autoplay: bool = False) -> None:
        self._loading_screen()
        self.audio.build_music()

        self.autoplay = autoplay
        self.frame = 0
        self.fps = 60.0
        self.quality = 2
        self._fps_t = 0.0
        self._fps_n = 0
        frames = 0
        while self.running:
            dt = min(self.clock.tick(C.FPS) / 1000.0, 1 / 20.0)
            if auto_frames:
                dt = 1 / 60.0
            self.time += dt
            self.screen_time += dt
            self._state_ns.time = self.screen_time
            self._handle_events()
            self._autopilot(frames)
            self._update(dt)
            self._draw()
            frames += 1
            self.frame = frames
            if not auto_frames:
                self._adapt(dt)
            if auto_frames and frames >= auto_frames:
                break
        self._save_best()
        pygame.quit()

    def _adapt(self, dt: float) -> None:
        """Baja la calidad si el equipo no llega a 60 fps (y la sube si puede)."""
        self._fps_t += dt
        self._fps_n += 1
        if self._fps_t < 1.5:
            return
        self.fps = self._fps_n / self._fps_t
        self._fps_t = 0.0
        self._fps_n = 0
        if self.fps < 46.0 and self.quality > 0:
            self.quality -= 1
        elif self.fps > 57.0 and self.quality < 2:
            self.quality += 1

    def _autopilot(self, frames: int) -> None:
        """Pilotaje sintético para el modo de prueba: fuerza combate, jefe,
        victoria y muerte para poder inspeccionar todos los estados."""
        if not getattr(self, "autoplay", False):
            return
        import random as _rnd

        if frames == 2:
            self.start_game()
        if frames == 1700:  # segunda partida, para ver el final por derrota
            self.start_game()
        if frames == 700:
            self.toggle_pause()
        if frames == 780 and self.state == PAUSED:
            self.toggle_pause()
        if self.state != PLAYING:
            return

        w = self.world
        if frames == 240:  # fuerza el jefe
            for e in w.enemies:
                e.dead = True
            w.runner.wave = C.BOSS_EVERY - 1
            w.runner.state = "clear"
            w.runner.timer = 0.05
        if frames == 500:  # sobrevive para llegar a la oleada final
            w.player.max_hp = 100000.0
            w.player.hp = 100000.0
        if frames == 600:  # fuerza la última oleada (victoria)
            for e in w.enemies:
                e.dead = True
            w.runner.wave = C.TOTAL_WAVES - 1
            w.runner.state = "clear"
            w.runner.timer = 0.05
        if 1760 < frames <= 1790 and not w.player.dead:  # fuerza la derrota
            w.player.hp = 0.0
            w.player.dead = True
            w.on_player_death()
        if frames % 240 == 200:
            w.nuke()
        if frames % 300 == 150:
            w.player.give_weapon(_rnd.choice(("abanico", "rafaga", "riel", "lazo")), 12.0)
        if frames % 420 == 380 and w.player.max_hp < 1000.0:
            w.player.damage(30.0, w)

        inp = w.input
        a = frames * 0.021
        inp.move = pygame.Vector2(math.cos(a), math.sin(a * 0.63))
        inp.fire_held = True
        inp.using_mouse = False
        self.mouse_moved_at = -99.0
        if _rnd.random() < 0.03:
            inp.dash_pressed = True

    def _loading_screen(self) -> None:
        if self.headless:
            return
        surf = pygame.Surface((C.LOGICAL_W, C.LOGICAL_H))
        surf.fill(C.BLACK)
        draw_text(surf, self.ui.f_hud_b, C.TITLE, C.CYAN, (C.LOGICAL_W / 2, C.LOGICAL_H / 2 - 20))
        draw_text(surf, self.ui.f_hud, "generando audio…", C.ICE, (C.LOGICAL_W / 2, C.LOGICAL_H / 2 + 20))
        self.screen.blit(surf, (0, 0))
        pygame.display.flip()

    # -- estados --------------------------------------------------------------
    def start_game(self) -> None:
        self.world.reset()
        self.state = PLAYING
        self.screen_time = 0.0
        self.audio.start_music()
        self.world.announce("OLEADA 1", C.CYAN, 1.0, big=True)
        self.world.announce("zancudos", C.ICE, 1.5, delay=0.18, sub=True)

    def toggle_pause(self) -> None:
        if self.state == PLAYING:
            self.state = PAUSED
            self.audio.play("ui", 0.6)
        elif self.state == PAUSED:
            self.state = PLAYING
            self.screen_time = 0.0
            self.audio.play("ui", 0.6)

    def end_game(self) -> None:
        self.state = END
        self.screen_time = 0.0
        self.world.apply_record(self.best)
        self._save_best()
        self.audio.play("gameover", 0.8)

    # -- input ----------------------------------------------------------------
    def _handle_events(self) -> None:
        keys = pygame.key.get_pressed()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False

            elif ev.type == pygame.VIDEORESIZE:
                size = (max(640, ev.w), max(400, ev.h))
                self.screen = pygame.display.set_mode(size, pygame.RESIZABLE)
                self.win_size = size
                self.fullscreen = False

            elif ev.type == pygame.KEYDOWN:
                k = ev.key
                if k == pygame.K_m:
                    muted = self.audio.toggle_mute()
                    if not muted:
                        self.audio.start_music()
                elif k == pygame.K_F11:
                    self._toggle_fullscreen()
                elif self.state == MENU:
                    if k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        self.start_game()
                elif self.state == PLAYING:
                    if k in (pygame.K_ESCAPE, pygame.K_p):
                        self.toggle_pause()
                    elif k in (pygame.K_SPACE, pygame.K_LSHIFT, pygame.K_RSHIFT):
                        self.world.input.dash_pressed = True
                elif self.state == PAUSED:
                    if k in (pygame.K_ESCAPE, pygame.K_p, pygame.K_RETURN):
                        self.toggle_pause()
                    elif k == pygame.K_r:
                        self.start_game()
                    elif k == pygame.K_q:
                        self.state = MENU
                        self.screen_time = 0.0
                elif self.state == END:
                    if k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        self.start_game()
                    elif k in (pygame.K_ESCAPE, pygame.K_q):
                        self.state = MENU
                        self.screen_time = 0.0

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if ev.button == 1:
                    if self.state == MENU:
                        self.start_game()
                    elif self.state == END:
                        self.start_game()
                    elif self.state == PLAYING:
                        self.world.input.fire_held = True
                elif ev.button == 3 and self.state == PLAYING:
                    self.world.input.dash_pressed = True

            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                self.world.input.fire_held = False

            elif ev.type == pygame.MOUSEMOTION:
                sx = self.win_size[0] / C.LOGICAL_W
                sy = self.win_size[1] / C.LOGICAL_H
                self.mouse_pos = pygame.Vector2(ev.pos[0] / sx, ev.pos[1] / sy)
                self.world.input.aim_pos.update(self.mouse_pos)
                self.mouse_moved_at = self.time

        if self.state == PLAYING:
            self._poll_input(keys)

    def _poll_input(self, keys) -> None:
        inp = self.world.input
        mv = pygame.Vector2()
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            mv.y -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            mv.y += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            mv.x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            mv.x += 1
        if mv.length_squared() > 0:
            mv = mv.normalize()
        inp.move = mv
        if keys[pygame.K_j]:
            inp.fire_held = True
        inp.using_mouse = (self.time - self.mouse_moved_at) < 2.0

    def _resolve_aim(self) -> None:
        """Apunta al ratón si se mueve; si no, al enemigo más cercano."""
        inp = self.world.input
        p = self.world.player
        if inp.using_mouse or not self.world.enemies:
            dx = inp.aim_pos.x - p.pos.x
            dy = inp.aim_pos.y - p.pos.y
        else:
            best = None
            bd = 1e18
            for e in self.world.enemies:
                if e.dead:
                    continue
                d = (e.pos - p.pos).length_squared()
                if d < bd:
                    bd = d
                    best = e
            if best is None:
                dx, dy = 1.0, 0.0
            else:
                dx, dy = best.pos.x - p.pos.x, best.pos.y - p.pos.y
        inp.aim_angle = math.atan2(dy, dx)

    # -- update ---------------------------------------------------------------
    def _update(self, dt: float) -> None:
        self.audio.update(dt)
        if self.state == PLAYING:
            self._resolve_aim()
            self.world.update(dt)
            if self.world.over:
                self.end_game()
        elif self.state == MENU:
            self.world.fx.update(dt)
        elif self.state == END:
            self.world.fx.update(dt)

    # -- draw -----------------------------------------------------------------
    def _draw(self) -> None:
        cv = self.canvas
        g = self.glow
        g.fill((0, 0, 0))
        w = self.world
        in_game = self.state in (PLAYING, PAUSED, END)
        t = w.time if self.state in (PLAYING, PAUSED) else self.time

        L = self.layers
        L.clear()
        back, mid, hud = L.back, L.mid, L.hud

        # 0) El canvas se repinta desde cero: sin esto las capas translúcidas
        #    se irían acumulando frame a frame hasta saturar.
        cv.blit(self.ui.bg.base, (0, 0))

        # 1) Fondo (rejilla, estrellas, arena)
        self.ui.bg.draw(back, g, t, arena=in_game, base=False, level=self.quality)
        if in_game:
            self._draw_pillars(back, g, t)
        if self.quality > 0:
            self.ui.bg.draw_ground_overlay(back)

        # 2) Entidades y efectos
        if in_game:
            for pk in w.pickups:
                pk.draw(mid, g, w)
            for b in w.enemy_bullets:
                b.draw(mid, g)
            for b in w.player_bullets:
                b.draw(mid, g)
            for e in w.enemies:
                e.draw(mid, g, w)
            for e in w.enemies:
                e.draw_health(mid, g)
            if not w.player.dead:
                w.player.draw(mid, g, w)
                w.player.draw_health_ring(mid, g)
        w.fx.draw_world(mid, g, self.fonts_float)

        # 3) Interfaz
        if in_game:
            self.ui.draw_hud(hud, g, w, int(self.fps), self.quality)
            self.ui.draw_damage_vignette(hud, w)
            self.ui.draw_announcements(hud, g, w)
        if self.state == MENU:
            screens.draw_menu(self.ui, hud, g, self._state_ns, self.best)
        elif self.state == PAUSED:
            screens.draw_pause(self.ui, hud, g, self._state_ns, w, self.best)
        elif self.state == END:
            screens.draw_end(self.ui, hud, g, self._state_ns, w, self.best, w.victory)
        if in_game:
            self.ui.draw_flash(hud, w)

        L.present(cv)

        # 4) Bloom: se suma una sola vez, con todo ya compuesto
        if self.quality > 0:
            pygame.transform.smoothscale(g, (C.LOGICAL_W, C.LOGICAL_H), self.glow_big)
            cv.blit(self.glow_big, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        self._present()

    def _draw_pillars(self, surf: pygame.Surface, glow: pygame.Surface, t: float) -> None:
        for i, (rect, color) in enumerate(self.pillars):
            pygame.draw.rect(surf, with_alpha((8, 5, 20), 225), rect, border_radius=10)
            inner = rect.inflate(-12, -12)
            pygame.draw.rect(surf, with_alpha(color, 30), inner, border_radius=5)
            # Diagonales
            for k in range(-2, 6):
                x = rect.left + k * 30 - (t * 12) % 30
                if x + 30 < rect.left or x > rect.right:
                    continue
                pygame.draw.line(
                    surf, with_alpha(color, 22),
                    (max(rect.left + 2, x), rect.bottom - 2),
                    (min(rect.right - 2, x + rect.height), rect.top + 2), 2,
                )
            pygame.draw.rect(surf, with_alpha(color, 150), rect, 2, border_radius=10)
            # Esquinas pulsantes
            a = 0.5 + 0.5 * math.sin(t * 2.2 + i * 1.3)
            for cx, cy in ((rect.left, rect.top), (rect.right, rect.top),
                           (rect.left, rect.bottom), (rect.right, rect.bottom)):
                sx = 1 if cx == rect.left else -1
                sy = 1 if cy == rect.top else -1
                ln = 12
                pygame.draw.line(surf, with_alpha(C.WHITE, int(120 + 100 * a)),
                                 (cx, cy), (cx + sx * ln, cy), 2)
                pygame.draw.line(surf, with_alpha(C.WHITE, int(120 + 100 * a)),
                                 (cx, cy), (cx, cy + sy * ln), 2)
            r = rect.inflate(8, 8)
            pygame.draw.rect(glow, scale_color(color, 0.35), r, width=2, border_radius=13)

    def _toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        flags = pygame.FULLSCREEN if self.fullscreen else pygame.RESIZABLE
        size = (0, 0) if self.fullscreen else (C.LOGICAL_W, C.LOGICAL_H)
        self.screen = pygame.display.set_mode(size, flags)
        self.win_size = self.screen.get_size()

    def _present(self) -> None:
        sh = self.world.fx.shake if self.state in (PLAYING, PAUSED, END) else None
        ox = oy = 0
        if sh is not None:
            ox = int(clamp(sh.x, -18, 18))
            oy = int(clamp(sh.y, -18, 18))

        if self.win_size == (C.LOGICAL_W, C.LOGICAL_H):
            if ox or oy:
                self.screen.fill(C.BLACK)
            self.screen.blit(self.canvas, (ox, oy))
        else:
            scaled = pygame.transform.smoothscale(self.canvas, self.win_size)
            if ox or oy:
                self.screen.fill(C.BLACK)
            self.screen.blit(scaled, (ox, oy))
        pygame.display.flip()


def run(auto_frames: int = 0, headless: bool = False, autoplay: bool = False) -> None:
    Game(headless=headless).run(auto_frames=auto_frames, autoplay=autoplay)
