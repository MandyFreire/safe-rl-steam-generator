"""Tres transmissores de nivel redundantes, com ruido e modos de falha."""
from dataclasses import dataclass
import numpy as np


@dataclass
class SensorFault:
    kind: str = "none"      # none | drift | stuck | bias
    t_start: float = 1e9
    rate: float = 0.0       # %/s para drift
    value: float = 0.0      # % para bias


class LevelTransmitter:
    def __init__(self, name: str, noise: float = 0.25, rng=None,
                 fault: SensorFault | None = None):
        self.name = name
        self.noise = noise
        self.rng = rng or np.random.default_rng(0)
        self.fault = fault or SensorFault()
        self._held = None

    def read(self, true_NR: float, t: float) -> float:
        f = self.fault
        y = true_NR + self.rng.normal(0.0, self.noise)
        if t >= f.t_start:
            if f.kind == "drift":
                y = y + f.rate * (t - f.t_start)
            elif f.kind == "bias":
                y = y + f.value
            elif f.kind == "stuck":
                if self._held is None:
                    self._held = y
                y = self._held
        return float(np.clip(y, -10.0, 120.0))


class SensorRack:
    """Rack de 3 canais independentes (redundancia para votacao 2oo3)."""

    def __init__(self, seed: int = 7, noise: float = 0.25, faults=None):
        rng = np.random.default_rng(seed)
        faults = faults or [None, None, None]
        self.channels = [
            LevelTransmitter(f"LT-{i+1}", noise,
                             np.random.default_rng(rng.integers(1e6)), faults[i])
            for i in range(3)
        ]

    def read(self, true_NR: float, t: float):
        return [c.read(true_NR, t) for c in self.channels]
