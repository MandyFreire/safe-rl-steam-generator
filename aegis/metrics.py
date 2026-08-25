"""Metricas de DESEMPENHO e de SEGURANCA. As duas contam - separadamente."""
import numpy as np


def evaluate(res: dict, sp: float = 50.0, lo_lo: float = 20.0,
             hi_hi: float = 80.0) -> dict:
    t, NR, u = res["t"], res["NR"], res["u"]
    dt = float(t[1] - t[0])
    err = np.abs(NR - sp)
    margin = np.minimum(NR - lo_lo, hi_hi - NR)
    return {
        # desempenho
        "IAE [%.s]": float(np.sum(err) * dt),
        "desvio maximo [%]": float(err.max()),
        "esforco da valvula [somatorio |du|]": float(np.sum(np.abs(np.diff(u)))),
        # seguranca
        "trips": int(bool(res["reactor_trip"].any() or res["turbine_trip"].any())),
        "margem minima ao trip [%]": float(margin.min()),
        "tempo em alarme [s]": float(np.sum(res["alarm"]) * dt),
        "intervencoes do governor": int(res.get("interventions", 0)),
        "tempo sob o agente [%]": float(res.get("agent_share", np.nan)),
    }


def table(rows: dict) -> str:
    keys = list(next(iter(rows.values())).keys())
    w = max(len(k) for k in keys) + 2
    head = " " * w + "".join(f"{name:>26}" for name in rows)
    lines = [head, "-" * len(head)]
    for k in keys:
        line = f"{k:<{w}}"
        for name in rows:
            v = rows[name][k]
            line += f"{v:>26.2f}" if isinstance(v, float) else f"{v:>26}"
        lines.append(line)
    return "\n".join(lines)
