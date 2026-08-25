"""Laco de simulacao: planta + sensores + protecao + controle + governor."""
import numpy as np

from .plant import SteamGenerator, PlantParams
from .sensors import SensorRack
from .protection import ProtectionSystem, TripSetpoints


def default_disturbance(rng):
    """Desbalanco nao medido: purga intermitente + deriva lenta de temperatura
    da agua de alimentacao. E o que impede o feedforward de ser perfeito -
    e portanto o que da espaco para um controlador melhor."""
    phase = rng.uniform(0, 6.28, 3)
    def d(t):
        slow = 0.020 * np.sin(2 * np.pi * t / 240 + phase[0]) \
             + 0.012 * np.sin(2 * np.pi * t / 95 + phase[1])
        blowdown = -0.05 if 300.0 <= t < 360.0 else 0.0
        return slow + blowdown
    return d


def run(controller, duration=900.0, dt=0.1, load=lambda t: 1.0, faults=None,
        voting="2oo3", governor=None, seed=7, sp=50.0, params=None,
        disturbance=None, meas_noise=0.25, aggregate="median"):
    p = params or PlantParams()
    plant = SteamGenerator(p, dt)
    rack = SensorRack(seed=seed, noise=meas_noise, faults=faults)
    rng = np.random.default_rng(seed + 100)
    dist = disturbance if disturbance is not None else default_disturbance(rng)
    rps = ProtectionSystem(TripSetpoints(), dt, voting=voting)
    controller.reset()
    if governor:
        governor.reset()

    n = int(duration / dt)
    rec = {k: np.zeros(n) for k in
           ("t", "NR", "meas", "u", "q_fw", "q_st", "load", "rate",
            "dist", "spread", "ch1", "ch2", "ch3")}
    for k in ("reactor_trip", "turbine_trip", "alarm", "on_agent"):
        rec[k] = np.zeros(n, dtype=bool)

    rate = 0.0
    prev_meas = None
    q_st_meas = plant.q_st        # medidor de vazao de vapor: lento e ruidoso
    for i in range(n):
        t = i * dt
        readings = rack.read(plant.NR, t)
        # agregacao dos 3 canais para a camada de CONTROLE.
        # mediana rejeita 1 canal defeituoso; media se deixa arrastar por ele.
        meas = float(np.median(readings) if aggregate == "median"
                     else np.mean(readings))
        spread = float(max(readings) - min(readings))
        if prev_meas is None:
            prev_meas = meas
        rate += dt / 2.0 * ((meas - prev_meas) / dt - rate)   # derivada filtrada
        prev_meas = meas

        s = rps.scan(readings, t)
        load_demand = 0.05 if s.reactor_trip or s.turbine_trip else load(t)
        afw = 0.09 if s.afw_actuated else None

        q_st_meas += dt / 8.0 * (plant.q_st - q_st_meas)
        q_st_meas_n = q_st_meas + rng.normal(0.0, 0.006)
        u_ctrl = controller(level=meas, q_steam=q_st_meas_n, rate=rate)
        if governor:
            u, on_agent = governor(u_ctrl, plant.state, load_demand, rate, t)
        else:
            u, on_agent = u_ctrl, True

        plant.step(u, load_demand, fw_isolated=s.fw_isolated, afw_flow=afw,
                   disturbance=dist(t))

        rec["t"][i], rec["NR"][i], rec["meas"][i] = t, plant.NR, meas
        rec["u"][i], rec["q_fw"][i], rec["q_st"][i] = u, plant.q_fw, plant.q_st
        rec["load"][i], rec["rate"][i] = load_demand, rate
        rec["dist"][i] = dist(t)
        rec["spread"][i] = spread
        rec["ch1"][i], rec["ch2"][i], rec["ch3"][i] = readings
        rec["reactor_trip"][i], rec["turbine_trip"][i] = s.reactor_trip, s.turbine_trip
        rec["alarm"][i], rec["on_agent"][i] = (s.lo_alarm or s.hi_alarm), on_agent

    rec["trip_log"] = rps.log
    if governor:
        rec["interventions"] = governor.interventions
        rec["agent_share"] = 100.0 * governor.time_on_agent / duration
        rec["governor_events"] = governor.events
    return rec


# ---- perfis de carga ----
def ramp(t0, t1, y0, y1):
    def f(t):
        if t <= t0:
            return y0
        if t >= t1:
            return y1
        return y0 + (y1 - y0) * (t - t0) / (t1 - t0)
    return f


def sequence(segments):
    """segments: lista de (t_inicio, t_fim, y_inicio, y_fim), em ordem."""
    def f(t):
        y = segments[0][2]
        for (t0, t1, y0, y1) in segments:
            if t >= t1:
                y = y1
            elif t > t0:
                y = y0 + (y1 - y0) * (t - t0) / (t1 - t0)
                break
            else:
                break
        return y
    return f
