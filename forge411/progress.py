"""
Suivi d'une opération longue (hachage du torrent, vérification par le client) : débit lissé, temps écoulé,
temps restant. Aucune dépendance à Tk : l'interface ne fait qu'afficher le relevé.
"""

import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

from .model import fmt_clock, fmt_size


@dataclass
class Reading:
    done: int               # octets traités
    total: int
    elapsed: float          # secondes depuis le début du suivi
    speed: float            # octets par seconde sur les dernières secondes, 0 tant qu'inconnu
    average: float          # octets par seconde depuis le début du suivi
    eta: Optional[float]    # secondes restantes, None tant qu'inconnu

    @property
    def fraction(self) -> float:
        return min(1.0, self.done / self.total) if self.total else 1.0


class RateMeter:
    """Débit calculé sur une fenêtre glissante : un disque qui ralentit se voit vite, sans que la valeur saute
    à chaque relevé. `done` : octets déjà traités au début du suivi (client qui a commencé sans nous)."""

    def __init__(self, total: int, done: int = 0, window: float = 5.0, start: Optional[float] = None):
        self.total = max(int(total), 0)
        self.window = window
        self.start = time.monotonic() if start is None else start
        self.base = self._clamp(done)
        self.samples: deque = deque([(self.start, self.base)])

    def _clamp(self, done) -> int:
        return max(0, min(int(done), self.total))

    def update(self, done: int, now: Optional[float] = None) -> Reading:
        now = time.monotonic() if now is None else now
        done = self._clamp(done)
        if done < self.samples[-1][1]:          # le client recommence (nouvelle vérification) : on repart de là
            self.samples.clear()
            self.start, self.base = now, done
        self.samples.append((now, done))
        while len(self.samples) > 2 and now - self.samples[1][0] >= self.window:
            self.samples.popleft()
        t0, d0 = self.samples[0]
        speed = (done - d0) / (now - t0) if now - t0 >= 0.5 else 0.0
        elapsed = now - self.start
        average = (done - self.base) / elapsed if elapsed >= 0.5 else 0.0
        eta = 0.0 if done >= self.total else ((self.total - done) / speed if speed > 0 else None)
        return Reading(done, self.total, elapsed, speed, average, eta)


def fmt_rate(bps: float) -> str:
    return f"{fmt_size(int(bps))}/s" if bps > 0 else "…"


def fmt_eta(seconds: Optional[float]) -> str:
    return "…" if seconds is None else fmt_clock(seconds)
