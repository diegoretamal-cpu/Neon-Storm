"""Utilidad de desarrollo: captura fotogramas del juego sin ventana real.

    python tools/shots.py
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from game.app import Game  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
WANT = {2, 430, 1050, 1560}


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        os.remove(os.path.join(OUT, f))

    game = Game(headless=True)
    original = game._draw
    taken: set[int] = set()
    state = {"n": 0}

    def patched() -> None:
        original()
        state["n"] += 1
        if state["n"] in WANT:
            path = os.path.join(OUT, f"f{state['n']:04d}_{game.state}.png")
            pygame.image.save(game.canvas, path)
            taken.add(state["n"])

    game._draw = patched  # type: ignore[method-assign]
    game.run(auto_frames=1950, autoplay=True)
    print("capturas:", len(taken), "->", OUT)


if __name__ == "__main__":
    main()
