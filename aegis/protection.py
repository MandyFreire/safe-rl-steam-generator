"""
Camada de PROTECAO (RPS / ESFAS) - deterministica, simples, auditavel.

Principio de projeto do AEGIS: esta camada NUNCA contem IA.
Ela e a funcao instrumentada de seguranca (SIF): bistaveis por canal,
votacao 2-out-of-3, tempo de resposta declarado, latch e reset manual.
Toda a logica cabe em uma pagina e pode ser testada exaustivamente -
que e exatamente o que uma reivindicacao de SIL exige (IEC 61508 /
IEC 61511; para nuclear, IEC 61513 e a defesa em profundidade da AIEA).

Funcoes implementadas (analogas a uma planta PWR real):
  LO-LO nivel  -> REACTOR_TRIP + atuacao da agua de alimentacao auxiliar (AFW)
  HI-HI nivel  -> TURBINE_TRIP + isolamento da agua de alimentacao (FWI)
Alarmes LO/HI apenas anunciam - nao atuam.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class TripSetpoints:
    lo_lo: float = 20.0     # % NR
    hi_hi: float = 80.0     # % NR
    lo_alarm: float = 35.0
    hi_alarm: float = 65.0
    deadband: float = 2.0   # % histerese para reset do bistavel
    response_time: float = 1.0   # s entre voto valido e atuacao


@dataclass
class ProtectionState:
    reactor_trip: bool = False
    turbine_trip: bool = False
    afw_actuated: bool = False
    fw_isolated: bool = False
    lo_alarm: bool = False
    hi_alarm: bool = False
    votes_lo: int = 0
    votes_hi: int = 0
    channel_lo: List[bool] = field(default_factory=lambda: [False] * 3)
    channel_hi: List[bool] = field(default_factory=lambda: [False] * 3)


class ProtectionSystem:
    """RPS/ESFAS 2oo3 com latch. Reset apenas por acao manual explicita."""

    def __init__(self, sp: TripSetpoints | None = None, dt: float = 0.1,
                 voting: str = "2oo3"):
        self.sp = sp or TripSetpoints()
        self.dt = dt
        self.voting = voting
        self.reset()

    def reset(self):
        self.s = ProtectionState()
        self._t_lo = None      # instante em que o voto LO ficou valido
        self._t_hi = None
        self.t = 0.0
        self.log = []
        return self.s

    # --- bistaveis por canal, com histerese ---
    def _bistables(self, readings, prev, setpoint, direction):
        out = []
        for y, p in zip(readings, prev):
            if direction == "lo":
                trig = y <= setpoint if not p else y <= setpoint + self.sp.deadband
            else:
                trig = y >= setpoint if not p else y >= setpoint - self.sp.deadband
            out.append(bool(trig))
        return out

    def _vote(self, bits) -> bool:
        n = sum(bits)
        if self.voting == "2oo3":
            return n >= 2
        if self.voting == "1oo3":
            return n >= 1
        if self.voting == "1oo1":       # canal unico, para comparacao didatica
            return bits[0]
        raise ValueError(self.voting)

    def scan(self, readings, t: float) -> ProtectionState:
        s, sp = self.s, self.sp
        self.t = t

        s.channel_lo = self._bistables(readings, s.channel_lo, sp.lo_lo, "lo")
        s.channel_hi = self._bistables(readings, s.channel_hi, sp.hi_hi, "hi")
        s.votes_lo, s.votes_hi = sum(s.channel_lo), sum(s.channel_hi)

        s.lo_alarm = sum(y <= sp.lo_alarm for y in readings) >= 2
        s.hi_alarm = sum(y >= sp.hi_alarm for y in readings) >= 2

        # --- LO-LO: trip do reator + AFW ---
        if self._vote(s.channel_lo):
            if self._t_lo is None:
                self._t_lo = t
            elif t - self._t_lo >= sp.response_time and not s.reactor_trip:
                s.reactor_trip = True
                s.afw_actuated = True
                self.log.append((t, "LO-LO NR -> REACTOR TRIP + AFW"))
        else:
            self._t_lo = None

        # --- HI-HI: trip da turbina + isolamento de agua ---
        if self._vote(s.channel_hi):
            if self._t_hi is None:
                self._t_hi = t
            elif t - self._t_hi >= sp.response_time and not s.turbine_trip:
                s.turbine_trip = True
                s.fw_isolated = True
                self.log.append((t, "HI-HI NR -> TURBINE TRIP + FW ISOLATION"))
        else:
            self._t_hi = None

        return s

    @property
    def tripped(self) -> bool:
        return self.s.reactor_trip or self.s.turbine_trip

    def manual_reset(self):
        """Reset so e permitido por acao humana deliberada (latch)."""
        self.reset()
