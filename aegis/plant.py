"""
Modelo dinamico simplificado de um gerador de vapor (SG) de PWR.

Foco: controle de nivel narrow-range (NR) com o efeito shrink & swell,
que torna a planta de FASE NAO-MINIMA (resposta inversa) - a razao pela
qual controle de nivel de SG e um problema classicamente dificil e uma
das maiores causas de trip espurio em plantas reais.

Modelo (2 estados de processo + 2 de atuacao):
    dm/dt        = K_m * (q_fw - q_st)                  # inventario (integrador)
    tau_sw dx/dt = -x + (q_st - q_fw)                   # vazio/bolhas (transitorio)
    NR           = m + K_sw * x                         # nivel medido

    q_st segue a demanda de carga (1a ordem)
    q_fw segue a valvula (1a ordem + rate limit + saturacao)

Nao pretende ser fiel a uma planta especifica: e um modelo de ORDEM REDUZIDA
com a assinatura dinamica correta (resposta inversa + integrador), suficiente
para estudar arquitetura de controle e protecao.
"""
from dataclasses import dataclass, field
import numpy as np


@dataclass
class PlantParams:
    K_m: float = 5.0        # %/s por fracao de desbalanco de vazao
    tau_sw: float = 12.0    # s, constante de tempo do efeito de vazio
    K_sw: float = 30.0      # % por fracao (intensidade do shrink/swell)
    tau_valve: float = 3.0  # s, atuador de agua de alimentacao
    rate_valve: float = 0.08  # fracao/s, limite de taxa da valvula
    tau_steam: float = 6.0  # s, resposta da vazao de vapor a demanda
    u_min: float = 0.0
    u_max: float = 1.2
    NR0: float = 50.0       # % nivel inicial
    q0: float = 1.0         # fracao de vazao nominal inicial


class SteamGenerator:
    def __init__(self, params: PlantParams | None = None, dt: float = 0.1):
        self.p = params or PlantParams()
        self.dt = dt
        self.reset()

    def reset(self):
        p = self.p
        self.m = p.NR0        # componente de inventario do nivel [%]
        self.x_sw = 0.0       # estado de vazio [fracao]
        self.q_fw = p.q0      # vazao de agua de alimentacao [fracao]
        self.q_st = p.q0      # vazao de vapor [fracao]
        self.valve = p.q0     # posicao efetiva da valvula [fracao]
        self.t = 0.0
        return self.state

    @property
    def NR(self) -> float:
        """Nivel narrow-range verdadeiro [%]."""
        return self.m + self.p.K_sw * self.x_sw

    @property
    def state(self) -> dict:
        return dict(t=self.t, NR=self.NR, m=self.m, x_sw=self.x_sw,
                    q_fw=self.q_fw, q_st=self.q_st, valve=self.valve)

    def step(self, u_cmd: float, load_demand: float,
             fw_isolated: bool = False, afw_flow: float | None = None,
             disturbance: float = 0.0) -> dict:
        """
        u_cmd        : demanda de abertura da valvula de agua [fracao 0..1.2]
        load_demand  : demanda de vapor [fracao] (0.05 tipico apos trip = calor residual)
        fw_isolated  : isolamento de agua de alimentacao pelo ESFAS
        afw_flow     : se != None, vazao imposta pela agua auxiliar (AFW)
        disturbance  : desbalanco NAO MEDIDO [fracao] - purga, vazamento,
                       variacao de temperatura da agua de alimentacao
        """
        p, dt = self.p, self.dt

        # --- atuador de agua de alimentacao (com rate limit e saturacao) ---
        u_cmd = float(np.clip(u_cmd, p.u_min, p.u_max))
        max_move = p.rate_valve * dt
        self.valve += np.clip(u_cmd - self.valve, -max_move, max_move)
        self.valve = float(np.clip(self.valve, p.u_min, p.u_max))

        q_fw_target = self.valve
        if fw_isolated:
            q_fw_target = 0.0
        if afw_flow is not None:
            q_fw_target = afw_flow
        self.q_fw += dt / p.tau_valve * (q_fw_target - self.q_fw)

        # --- vazao de vapor segue a demanda de carga ---
        self.q_st += dt / p.tau_steam * (load_demand - self.q_st)

        # --- processo ---
        imbalance = self.q_fw - self.q_st + disturbance
        self.m += dt * p.K_m * imbalance
        self.x_sw += dt / p.tau_sw * (-self.x_sw - imbalance)

        self.m = float(np.clip(self.m, -50.0, 150.0))
        self.t += dt
        return self.state
