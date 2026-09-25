"""Audio 100 % sintetizado en Python: efectos y un loop de synthwave.

No se carga ningún archivo externo. Todo se genera con la biblioteca estándar
(`array` + `math`) y se entrega a pygame como `pygame.mixer.Sound(buffer=...)`.
Si no hay dispositivo de sonido, el juego sigue funcionando en silencio.
"""

from __future__ import annotations

import array
import math
import random

import pygame

SAMPLE_RATE = 44100
MUSIC_RATE = 22050
BUFFER = 512


# --- Utilidades de síntesis --------------------------------------------------
def _saw(phase: float) -> float:
    p = phase % 1.0
    return 2.0 * p - 1.0


def _square(phase: float, duty: float = 0.5) -> float:
    return 1.0 if (phase % 1.0) < duty else -1.0


def _tri(phase: float) -> float:
    p = phase % 1.0
    return 4.0 * abs(p - 0.5) - 1.0


def _adsr(i: int, n: int, attack: float = 0.01, release: float = 0.6) -> float:
    t = i / max(1, n)
    if t < attack:
        return t / attack
    if t > 1.0 - release:
        return max(0.0, (1.0 - t) / release)
    return 1.0


def _to_sound(samples: list[float], volume: float = 0.7) -> pygame.mixer.Sound:
    peak = max(1e-6, max(abs(s) for s in samples))
    norm = volume / peak
    data = array.array("h", (int(max(-1.0, min(1.0, s * norm)) * 32000) for s in samples))
    return pygame.mixer.Sound(buffer=data.tobytes())


def _render(duration: float, rate: int, voice, volume: float = 0.7) -> pygame.mixer.Sound:
    n = int(duration * rate)
    out = [0.0] * n
    for i in range(n):
        t = i / rate
        out[i] = voice(t, i, n)
    return _to_sound(out, volume)


# --- Efectos ----------------------------------------------------------------
def _build_sfx() -> dict[str, pygame.mixer.Sound]:
    r = SAMPLE_RATE
    sfx: dict[str, pygame.mixer.Sound] = {}

    # Disparo: pulso cuadrado que cae de tono.
    sfx["shoot"] = _render(0.10, r, lambda t, i, n: (
        _square(760 * t * t * 0.9 + 620 * t, 0.25) * (1 - i / n) ** 2.2
    ), 0.42)

    # Disparo pesado (riel).
    sfx["shoot_rail"] = _render(0.28, r, lambda t, i, n: (
        (_saw(150 * t + 90 * t * t) * 0.5 + _square(300 * t, 0.15) * 0.5)
        * (1 - i / n) ** 1.6
    ), 0.55)

    # Impacto seco.
    sfx["hit"] = _render(0.07, r, lambda t, i, n: (
        (random.uniform(-1, 1) * 0.7 + _square(900 * t, 0.3) * 0.5) * (1 - i / n) ** 3
    ), 0.32)

    # Explosión: ruido filtrado + subgrave.
    sfx["boom"] = _render(0.55, r, lambda t, i, n: (
        (random.uniform(-1, 1) * math.exp(-9 * t) * 0.9
         + _saw(70 - 30 * t) * math.exp(-6 * t) * 0.6)
    ), 0.72)

    sfx["boom_big"] = _render(1.10, r, lambda t, i, n: (
        (random.uniform(-1, 1) * math.exp(-5.0 * t) * 1.0
         + _saw(58 - 24 * t) * math.exp(-3.4 * t) * 0.9
         + _square(150 * t, 0.4) * math.exp(-14 * t) * 0.25)
    ), 0.95)

    # Daño recibido.
    sfx["hurt"] = _render(0.32, r, lambda t, i, n: (
        (_saw(420 - 260 * t) * 0.6 + _square(210 - 130 * t, 0.2) * 0.4)
        * (1 - i / n) ** 1.4
    ), 0.6)

    # Recogida de objeto: arpegio ascendente brillante.
    def _pickup(t, i, n):
        notes = (880, 1174, 1568, 2093)
        step = min(int(t / 0.055), len(notes) - 1)
        f = notes[step]
        local = (t - step * 0.055)
        return _tri(f * local + f * 0.0) * math.exp(-24 * local) * 0.8
    sfx["pickup"] = _render(0.24, r, _pickup, 0.5)

    # Dash: barrido de ruido con tono descendente.
    sfx["dash"] = _render(0.22, r, lambda t, i, n: (
        random.uniform(-1, 1) * math.sin(math.pi * i / n) ** 2 * 0.9
        + math.sin(2 * math.pi * (900 - 500 * t) * t) * 0.25
    ), 0.4)

    # Escudo / armadura.
    sfx["shield"] = _render(0.35, r, lambda t, i, n: (
        _square(520 * t + 260 * t * t, 0.2) * math.exp(-7 * t) * 0.7
    ), 0.4)

    # Inicio de oleada: acorde brillante.
    def _wave(t, i, n):
        base = 330.0
        return sum(_tri(f * t) for f in (base, base * 1.26, base * 1.5, base * 2.0)) / 4 * math.exp(-2.6 * t)
    sfx["wave"] = _render(0.85, r, _wave, 0.6)

    # Game over: caída grave.
    def _over(t, i, n):
        f = 330 * (1 - 0.55 * t)
        return (_saw(f * t) * 0.5 + _tri(f * 0.5 * t) * 0.5) * math.exp(-1.9 * t)
    sfx["gameover"] = _render(1.5, r, _over, 0.65)

    # UI.
    sfx["ui"] = _render(0.07, r, lambda t, i, n: _square(1400 * t, 0.3) * (1 - i / n) ** 3, 0.25)
    sfx["nuke"] = _render(1.0, r, lambda t, i, n: (
        random.uniform(-1, 1) * math.exp(-3.2 * t) + _sine(110 - 70 * t) * math.exp(-4 * t)
    ), 0.85)

    # Alerta de jefe.
    def _boss(t, i, n):
        f = 90 + 25 * math.sin(2 * math.pi * 3.5 * t)
        return _saw(f * t) * 0.7 * (0.6 + 0.4 * math.sin(2 * math.pi * 6 * t))
    sfx["boss"] = _render(1.8, r, _boss, 0.7)

    return sfx


# --- Música -----------------------------------------------------------------
# Progresión synthwave: Am - F - C - G, 2 compases cada uno.
_CHORDS = (
    (55.00, (440.00, 523.25, 659.25)),   # Am
    (43.65, (349.23, 440.00, 523.25)),   # F
    (65.41, (523.25, 659.25, 783.99)),   # C
    (49.00, (392.00, 493.88, 587.33)),   # G
)


def _build_music() -> pygame.mixer.Sound:
    rate = MUSIC_RATE
    bpm = 122.0
    beat = 60.0 / bpm
    step = beat / 4.0            # semicorchea
    bars = 8
    total_steps = bars * 16
    n = int(total_steps * step * rate)
    out = [0.0] * n

    for s in range(total_steps):
        chord = _CHORDS[(s // 32) % len(_CHORDS)]
        bass_f, arp_notes = chord
        start = int(s * step * rate)
        end = min(n, int((s + 1) * step * rate))
        length = end - start
        if length <= 0:
            continue

        # -- Bajo: nota redondeada a corchea con envolvente corta.
        if s % 4 == 0:
            note = bass_f if s % 8 == 0 else bass_f * 1.5
            for i in range(length):
                t = i / rate
                env = math.exp(-7.0 * t) * _adsr(i, length, 0.005, 0.25)
                out[start + i] += _saw(note * t) * 0.30 * env

        # -- Arpegio: 16avos, la nota se abrevia para que suene "punteado".
        note = arp_notes[s % 3]
        for i in range(length):
            t = i / rate
            env = math.exp(-22.0 * t)
            out[start + i] += _square(note * t, 0.28) * 0.11 * env

        # -- Pad suave de acorde (solo al inicio de cada compás).
        if s % 16 == 0:
            for f in arp_notes:
                for i in range(length * 8):
                    idx = start + i
                    if idx >= n:
                        break
                    t = i / rate
                    env = min(1.0, t / 0.4) * math.exp(-1.1 * t)
                    out[idx] += _tri(f * t) * 0.045 * env

    # -- Percusión.
    for s in range(total_steps):
        start = int(s * step * rate)
        if start >= n:
            break
        length = min(int(0.14 * rate), n - start)

        if s % 8 == 0:  # bombo
            for i in range(length):
                t = i / rate
                f = 140 * math.exp(-24 * t) + 46
                out[start + i] += math.sin(2 * math.pi * f * t) * 0.55 * math.exp(-11 * t)
        if s % 8 == 4:  # caja
            for i in range(length):
                t = i / rate
                noise = random.uniform(-1, 1)
                out[start + i] += (noise * 0.30 + _square(190 * t, 0.5) * 0.12) * math.exp(-26 * t)
        if s % 2 == 1:  # charles
            length_h = min(int(0.045 * rate), n - start)
            for i in range(length_h):
                t = i / rate
                out[start + i] += random.uniform(-1, 1) * 0.10 * math.exp(-70 * t)

    # Normalización suave y limitador.
    peak = max(1e-6, max(abs(v) for v in out))
    out = [v * 0.82 / peak for v in out]
    data = array.array("h", (int(max(-1.0, min(1.0, v)) * 30000) for v in out))
    return pygame.mixer.Sound(buffer=data.tobytes())


# --- Fachada -----------------------------------------------------------------
class Audio:
    """Envoltorio con control de volumen y degradación elegante."""

    def __init__(self) -> None:
        self.enabled = False
        self.sfx: dict[str, pygame.mixer.Sound] = {}
        self.music: pygame.mixer.Sound | None = None
        self.music_volume = 0.35
        self.sfx_volume = 0.55
        self._muted = False
        self._music_channel: pygame.mixer.Channel | None = None
        self._last: dict[str, int] = {}
        self._clock = 0.0

    def init(self) -> None:
        try:
            pygame.mixer.pre_init(SAMPLE_RATE, -16, 2, BUFFER)
            pygame.mixer.init(SAMPLE_RATE, -16, 2, BUFFER)
            pygame.mixer.set_num_channels(24)
            self.enabled = True
        except pygame.error:
            self.enabled = False
            return

        try:
            self.sfx = _build_sfx()
        except Exception:
            self.sfx = {}
        try:
            self.music = _build_music()
        except Exception:
            self.music = None

    def build_music(self) -> None:
        """Genera la música (lento, se llama tras mostrar la ventana)."""
        if self.enabled and self.music is None:
            try:
                self.music = _build_music()
            except Exception:
                self.music = None

    # -- reproducción ---------------------------------------------------------
    def play(self, name: str, volume: float = 1.0, min_gap: float = 0.0) -> None:
        if not self.enabled or self._muted or name not in self.sfx:
            return
        if min_gap > 0.0:
            if self._clock - self._last.get(name, -99.0) < min_gap:
                return
            self._last[name] = self._clock
        try:
            self.sfx[name].set_volume(clamp01(volume * self.sfx_volume))
            self.sfx[name].play()
        except pygame.error:
            pass

    def start_music(self) -> None:
        if not self.enabled or self._muted or self.music is None:
            return
        if self._music_channel is not None and self._music_channel.get_busy():
            return
        try:
            self.music.set_volume(self.music_volume)
            self._music_channel = self.music.play(loops=-1)
        except pygame.error:
            pass

    def stop_music(self) -> None:
        if self._music_channel is not None:
            try:
                self._music_channel.stop()
            except pygame.error:
                pass
            self._music_channel = None

    def set_music_volume(self, v: float) -> None:
        self.music_volume = clamp01(v)
        if self._music_channel is not None:
            try:
                self._music_channel.set_volume(self.music_volume)
            except pygame.error:
                pass

    def toggle_mute(self) -> bool:
        self._muted = not self._muted
        if self._muted:
            self.stop_music()
        else:
            self.start_music()
        return self._muted

    @property
    def muted(self) -> bool:
        return self._muted

    def update(self, dt: float) -> None:
        self._clock += dt


def clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
