#!/usr/bin/env python3
"""NEON STORM — punto de entrada.

Uso:
    python neon_storm.py
    python neon_storm.py --test      # 600 frames simulados, sin ventana
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.app import run  # noqa: E402


def main() -> int:
    args = set(sys.argv[1:])
    if args & {"-h", "--help"}:
        print(__doc__)
        return 0
    if args & {"--test", "--selftest"}:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        run(auto_frames=1950, headless=True, autoplay=True)
        print("OK: 1950 frames simulados (menú + combate + jefe + pausa + finales).")
        return 0
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
