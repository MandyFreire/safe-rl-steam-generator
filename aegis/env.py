"""
Ambiente de RL compativel com a API Gymnasium (sem exigir o pacote).

Ponto central do projeto: o agente e treinado COM o governor no laco
("shielded RL"). Ele nunca ve um estado que o envelope proibiria, e cada
veto entra na recompensa como custo. O resultado e uma politica que
aprende a nao chegar perto da fronteira - e nao apenas uma politica que
e impedida de cruza-la.

Uso com stable-baselines3:
    from stable_baselines3 import SAC
    env = SGLevelEnv(shielded=True)
    SAC("MlpPolicy", env).learn(300_000)
"""
import numpy as np

from .plant import SteamGenerator, PlantParams
from .sensors import SensorRack
from .protection import ProtectionSystem, TripSetpoints
from .controllers import ThreeElement
from .governor import SafetyGovernor, Envelope
from .simulator import default_disturbance, sequence

try:                                  # opcional
    import gymnasium as gym
    from gymnasium import spaces
    BASE = gym.Env
except Exception:                     # pragma: no cover
    BASE, spaces = object, None


class SGLevelEnv(BASE):
    """Observacao normalizada; acao = variacao da abertura da valvula."""

    metadata = {"render_modes": []}

    def __init__(self, dt=0.5, horizon=900.0, sp=50.0, shielded=True,
                 seed=0, w_effort=0.4, w_veto=5.0, trip_penalty=200.0):
        self.dt, self.horizon, self.sp = dt, horizon, sp
        self.shielded = shielded
        self.w_effort, self.w_veto, self.trip_penalty = w_effort, w_veto, trip_penalty
        self.rng = np.random.default_rng(seed)
        if spaces is not None:
            self.action_space = spaces.Box(-1.0, 1.0, (1,), np.float32)
            self.observation_space = spaces.Box(-np.inf, np.inf, (7,), np.float32)
        self.reset()

    # ---------------------------------------------------------------
    def _random_load(self):
        t0 = self.rng.uniform(60, 300)
        dur = self.rng.uniform(20, 200)          # de rejeicao brusca a rampa lenta
        y1 = self.rng.uniform(0.40, 1.00)
        t2 = t0 + dur + self.rng.uniform(60, 250)
        return sequence([(t0, t0 + dur, 1.0, y1),
                         (t2, t2 + dur, y1, self.rng.uniform(0.5, 1.0))])

    def reset(self, seed=None, options=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.p = PlantParams()
        self.plant = SteamGenerator(self.p, self.dt)
        self.rack = SensorRack(seed=int(self.rng.integers(1e6)))
        self.rps = ProtectionSystem(TripSetpoints(), self.dt)
        self.base = ThreeElement(self.dt, 0.035, 0.0015, 0.20, sp=self.sp)
        self.gov = (SafetyGovernor(self.base, self.p, Envelope(), self.sp,
                                   check_every=self.dt, dt=self.dt)
                    if self.shielded else None)
        self.load = self._random_load()
        self.dist = default_disturbance(self.rng)
        self.u = self.plant.q_fw
        self.rate, self._prev = 0.0, self.plant.NR
        self.t = 0.0
        self._vetos = 0
        return self._obs(), {}

    def _obs(self):
        sp_ = TripSetpoints()
        return np.array([
            (self.plant.NR - self.sp) / 20.0,
            self.rate / 2.0,
            self.plant.q_st - 0.7,
            self.plant.q_fw - 0.7,
            self.u - 0.7,
            (self.plant.NR - sp_.lo_lo) / 30.0,
            (sp_.hi_hi - self.plant.NR) / 30.0,
        ], dtype=np.float32)

    # ---------------------------------------------------------------
    def step(self, action):
        a = float(np.clip(np.asarray(action).ravel()[0], -1, 1))
        u_agent = float(np.clip(self.u + 0.05 * a, 0.0, 1.2))

        readings = self.rack.read(self.plant.NR, self.t)
        s = self.rps.scan(readings, self.t)
        load = 0.05 if (s.reactor_trip or s.turbine_trip) else self.load(self.t)

        vetoed = False
        if self.gov is not None:
            u, on_agent = self.gov(u_agent, self.plant.state, load, self.rate, self.t)
            vetoed = not on_agent
        else:
            u = u_agent
        self.u = u

        self.plant.step(u, load, fw_isolated=s.fw_isolated,
                        afw_flow=0.09 if s.afw_actuated else None,
                        disturbance=self.dist(self.t))
        self.rate += self.dt / 2.0 * ((self.plant.NR - self._prev) / self.dt - self.rate)
        self._prev = self.plant.NR
        self.t += self.dt

        err = abs(self.plant.NR - self.sp)
        r = -err / 10.0 - self.w_effort * abs(0.05 * a)
        if vetoed:
            r -= self.w_veto * self.dt
            self._vetos += 1
        tripped = s.reactor_trip or s.turbine_trip
        if tripped:
            r -= self.trip_penalty
        term = bool(tripped)
        trunc = self.t >= self.horizon
        return self._obs(), float(r), term, trunc, {"vetos": self._vetos}
