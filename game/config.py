"""Constantes globales: resolución, paleta y datos de la arena."""

from __future__ import annotations

import pygame

# --- Render -----------------------------------------------------------------
LOGICAL_W, LOGICAL_H = 1280, 720
FPS = 60
GLOW_DIV = 4  # el buffer de bloom se dibuja a 1/GLOW_DIV de resolución

TITLE = "NEON STORM"
CAPTION = f"{TITLE}  ·  pygame-ce"

# --- Paleta synthwave --------------------------------------------------------
BLACK = (4, 3, 12)
NIGHT = (11, 7, 26)
NIGHT_TOP = (26, 12, 54)
GRID = (58, 32, 108)
FLOOR = (16, 11, 38)
FLOOR_EDGE = (86, 52, 158)

WHITE = (238, 250, 255)
ICE = (176, 236, 255)
CYAN = (0, 233, 255)
TEAL = (0, 176, 196)
MAGENTA = (255, 32, 168)
VIOLET = (150, 64, 255)
INDIGO = (86, 40, 180)
LIME = (122, 255, 140)
AMBER = (255, 196, 61)
ORANGE = (255, 122, 40)
RED = (255, 58, 92)
GOLD = (255, 224, 138)

PLAYER_MAIN = CYAN
PLAYER_ALT = VIOLET

# --- Arena ------------------------------------------------------------------
ARENA = pygame.Rect(48, 96, LOGICAL_W - 96, LOGICAL_H - 96 - 48)
HUD_H = 76

# Pilares simétricos: cobertura visual y rompen las líneas de tiro largas.
PILLARS = (
    (pygame.Rect(360, 178, 112, 112), VIOLET),
    (pygame.Rect(808, 178, 112, 112), VIOLET),
    (pygame.Rect(360, 430, 112, 112), VIOLET),
    (pygame.Rect(808, 430, 112, 112), VIOLET),
)


def pillars() -> list[tuple[pygame.Rect, tuple[int, int, int]]]:
    """Devuelve copias de los pilares (los Rect son mutables)."""
    return [(pygame.Rect(r), c) for r, c in PILLARS]


# --- Jugabilidad ------------------------------------------------------------
PLAYER_SPEED = 430.0
PLAYER_ACCEL = 4200.0
PLAYER_FRICTION = 9.0
PLAYER_RADIUS = 14.0
PLAYER_MAX_HP = 100.0
PLAYER_I_FRAMES = 0.9

DASH_SPEED = 1500.0
DASH_TIME = 0.17
DASH_COOLDOWN = 0.85

COMBO_WINDOW = 2.6  # segundos para mantener la racha
COMBO_MAX = 12

SCORE_CHUNK = 10  # puntos por unidad de vida de enemigo
PICKUP_CHANCE = 0.26

TOTAL_WAVES = 25
BOSS_EVERY = 5

SAVE_PATH = "neon_storm.save.json"
