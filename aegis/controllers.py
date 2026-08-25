"""Controladores da camada de CONTROLE (nao-seguranca)."""
import numpy as np


class PID:
    """PID com anti-windup e modo de rastreamento (transferencia suave)."""

    def __init__(self, Kp, Ki, Kd, dt, u_min=0.0, u_max=1.2, tau_d=2.0):
        self.Kp, self.Ki, self.Kd = Kp, Ki, Kd
        self.dt, self.u_min, self.u_max, self.tau_d = dt, u_min, u_max, tau_d
        self.reset()

    def reset(self):
        self.I = 0.0
        self.d_state = 0.0
        self.prev_pv = None

    def track(self, u_active, pv, sp, ff=0.0):
        """Mantem o integrador alinhado a saida ativa enquanto o PID esta ocioso."""
        e = sp - pv
        self.I = float(np.clip(u_active - ff - self.Kp * e, -1.5, 1.5))
        self.prev_pv = pv

    def __call__(self, pv, sp, ff=0.0):
        e = sp - pv
        if self.prev_pv is None:
            self.prev_pv = pv
        # derivada filtrada sobre a PV (evita chute de setpoint)
        dpv = (pv - self.prev_pv) / self.dt
        self.d_state += self.dt / self.tau_d * (dpv - self.d_state)
        self.prev_pv = pv

        u_unsat = ff + self.Kp * e + self.I - self.Kd * self.d_state
        u = float(np.clip(u_unsat, self.u_min, self.u_max))
        # integracao condicional (anti-windup)
        if self.u_min < u_unsat < self.u_max:
            self.I += self.Ki * e * self.dt
        self.I = float(np.clip(self.I, -1.5, 1.5))
        return u


class ThreeElement:
    """
    Controle classico de nivel de SG a tres elementos:
    feedforward da vazao de vapor + trim de nivel por PID.
    E a linha de base COMPROVADA - e o controlador de fallback do governor.
    """

    def __init__(self, dt, Kp=0.020, Ki=0.0007, Kd=0.10, sp=50.0):
        self.pid = PID(Kp, Ki, Kd, dt)
        self.sp = sp
        self.name = "three-element PID"

    def reset(self):
        self.pid.reset()

    def __call__(self, level, q_steam, **_):
        return self.pid(level, self.sp, ff=q_steam)

    def track(self, u_active, level, q_steam):
        self.pid.track(u_active, level, self.sp, ff=q_steam)


class MisguidedAgent:
    """
    Proxy de uma politica de IA que e OTIMA perto do ponto de operacao de
    treino e EXTRAPOLA ERRADO fora dele.

    Perto do setpoint ela reproduz um feedforward competente - e nesse
    regime bate o PID no IAE. Ao sair da distribuicao de treino, o termo
    aprendido da derivada assume o sinal errado: em uma planta de fase
    nao-minima, abrir a valvula faz o nivel CAIR nos primeiros segundos
    (shrink), e uma politica com horizonte curto aprende exatamente a
    licao invertida - "nivel caindo, fechar a valvula".

    Nao e um espantalho. E o modo de falha classico de ML em sistemas de
    resposta inversa, e a razao pela qual desempenho medio no conjunto de
    teste nao e um argumento de seguranca.
    """

    def __init__(self, dt, Kd_wrong=0.55, e_ref=8.0, rate_ref=1.2, sp=50.0,
                 Kp=0.025, Ki=0.0003, Kd=0.15):
        self.inner = PID(Kp, Ki, Kd, dt)      # o que a politica aprendeu certo
        self.Kd_wrong, self.e_ref, self.rate_ref = Kd_wrong, e_ref, rate_ref
        self.sp, self.dt = sp, dt
        self.name = "agente (politica nao verificada)"

    def ood(self, level, rate):
        """0 = dentro da distribuicao de treino; 1 = extrapolando."""
        return float(np.clip(max(abs(self.sp - level) / self.e_ref,
                                 abs(rate) / self.rate_ref) - 1.0, 0.0, 1.0))

    def reset(self):
        self.inner.reset()

    def __call__(self, level, q_steam, rate=0.0, **_):
        u = self.inner(level, self.sp, ff=q_steam)
        u += self.ood(level, rate) * self.Kd_wrong * rate
        return float(np.clip(u, 0.0, 1.2))

    def track(self, *a, **k):
        pass


AggressiveController = MisguidedAgent   # alias de compatibilidade
