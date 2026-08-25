"""
Camada de GARANTIA EM TEMPO DE EXECUCAO (runtime assurance).

Fica ENTRE o controlador de IA e a planta - abaixo da camada de controle,
acima e independente da camada de protecao. E a arquitetura Simplex
(Sha, 2001): um controlador de alto desempenho e nao verificavel opera
enquanto um monitor simples e verificavel provar que o estado permanece
dentro de um envelope; ao primeiro sinal de saida, o comando cai para um
controlador de linha de base comprovado.

Diferenca crucial em relacao a protecao (ESFAS):
  - o ESFAS age DEPOIS que o limite de seguranca foi violado (mitiga);
  - o governor age ANTES, para que o ESFAS nunca precise agir (preserva).
Um trip e um sucesso da seguranca e um fracasso do controle.
"""
from dataclasses import dataclass
import numpy as np

from .plant import PlantParams


# NOTA DE PROJETO - escolha do horizonte:
# curto demais e o governor enxerga so a resposta inversa e aprende a mesma
# licao errada que o agente; longo demais e ele veta o tempo todo e mata a
# disponibilidade. O piso e o tempo do zero de fase nao-minima (~6 s) somado
# ao tempo de transporte do inventario. Varredura em scripts/run_scenarios.py:
#   20 s -> 1 veto, desvio maximo 16 % | 35 s -> 1 veto, 9,0 %
#   45 s -> 2 vetos, 8,4 %  <- escolhido
#   60 s -> 3 vetos e LOCKOUT: veta ate em carga normal
@dataclass
class Envelope:
    NR_min: float = 30.0        # % - bem dentro dos setpoints de trip (20/80)
    NR_max: float = 70.0
    rate_max: float = 2.0       # %/s
    horizon: float = 45.0       # s de previsao (ver nota de projeto abaixo)
    dt_pred: float = 0.5        # s por passo de previsao
    dwell: float = 20.0         # s minimos sob a linha de base apos veto
    recover_band: float = 6.0   # % de |NR - SP| para devolver o controle
    recover_rate: float = 0.6   # %/s
    max_strikes: int = 3        # vetos antes de travar na linha de base


def predict(NR, m, x_sw, q_fw, q_st, u_cmd, load, p: PlantParams, env: Envelope):
    """
    Propaga o modelo NOMINAL de ordem reduzida mantendo a acao candidata.
    Retorna (viola_envelope, NR_min_previsto, NR_max_previsto).
    Deliberadamente simples: precisa ser auditavel, nao exato.
    """
    dt = env.dt_pred
    n = int(env.horizon / dt)
    lo, hi = NR, NR
    valve = q_fw
    for _ in range(n):
        valve += np.clip(u_cmd - valve, -p.rate_valve * dt, p.rate_valve * dt)
        q_fw += dt / p.tau_valve * (valve - q_fw)
        q_st += dt / p.tau_steam * (load - q_st)
        imb = q_fw - q_st
        m += dt * p.K_m * imb
        x_sw += dt / p.tau_sw * (-x_sw - imb)
        NR = m + p.K_sw * x_sw
        lo, hi = min(lo, NR), max(hi, NR)
        if NR < env.NR_min or NR > env.NR_max:
            return True, lo, hi
    return False, lo, hi


class SafetyGovernor:
    """Arbitra entre o agente (nao verificado) e a linha de base (comprovada)."""

    def __init__(self, baseline, params: PlantParams, env: Envelope | None = None,
                 sp: float = 50.0, check_every: float = 0.5, dt: float = 0.1):
        self.baseline = baseline
        self.p = params
        self.env = env or Envelope()
        self.sp = sp
        self.dt = dt
        self.every = max(1, int(round(check_every / dt)))
        self.reset()

    def reset(self):
        self.in_baseline = False
        self.t_switch = -1e9
        self.k = 0
        self.interventions = 0
        self.time_on_agent = 0.0
        self.events = []
        self.locked_out = False
        self._last_reason = ""

    def __call__(self, agent_u, plant_state, load, rate, t):
        """Retorna (u_aplicado, sob_controle_do_agente)."""
        e = self.env
        st = plant_state
        check = (self.k % self.every == 0)
        self.k += 1

        if self.locked_out:
            u = self.baseline(level=st["NR"], q_steam=st["q_st"])
            return u, False

        if check:
            unsafe, lo, hi = predict(st["NR"], st["m"], st["x_sw"], st["q_fw"],
                                     st["q_st"], agent_u, load, self.p, e)
            unsafe = unsafe or abs(rate) > e.rate_max
            if unsafe and not self.in_baseline:
                self.in_baseline = True
                self.t_switch = t
                self.interventions += 1
                self._last_reason = (f"previsao NR -> [{lo:.1f}, {hi:.1f}] % "
                                     f"| taxa {rate:+.2f} %/s")
                self.events.append((t, "VETO -> linha de base", self._last_reason))
                if self.interventions >= e.max_strikes:
                    self.locked_out = True
                    self.events.append(
                        (t, "LOCKOUT: politica degradada",
                         f"{self.interventions} vetos - agente removido do laco "
                         f"ate reset manual e reavaliacao"))
            elif self.in_baseline and not unsafe:
                calm = (abs(st["NR"] - self.sp) <= e.recover_band
                        and abs(rate) <= e.recover_rate)
                if calm and (t - self.t_switch) >= e.dwell:
                    self.in_baseline = False
                    self.events.append((t, "devolve ao agente", ""))

        if self.in_baseline:
            u = self.baseline(level=st["NR"], q_steam=st["q_st"])
            return u, False

        # linha de base ociosa: rastreia a saida ativa (transferencia suave)
        self.baseline.track(agent_u, st["NR"], st["q_st"])
        self.time_on_agent += self.dt
        return agent_u, True
