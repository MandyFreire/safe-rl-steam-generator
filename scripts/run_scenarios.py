"""
Campanha de ensaios do AEGIS-SG. Roda os cenarios, imprime as metricas
e salva as figuras em figs/.

    python scripts/run_scenarios.py
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis import (ThreeElement, MisguidedAgent, SafetyGovernor, Envelope,
                   run, sequence, evaluate, table)
from aegis.plant import PlantParams
from aegis.sensors import SensorFault
from scripts.plotting import (apply_style, level_bands, finish, plt,
                              BLUE, ORANGE, AQUA, RED, VIOLET, MUTED, INK2)

FIGS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "figs")
os.makedirs(FIGS, exist_ok=True)

BASE = dict(Kp=0.025, Ki=0.0003, Kd=0.15)
LOAD_NORMAL = sequence([(100, 250, 1.0, 0.65), (500, 650, 0.65, 1.0)])   # ~14%/min
LOAD_SEVERE = sequence([(120, 145, 1.0, 0.45), (500, 560, 0.45, 0.95)])  # rejeicao


def baseline(): return ThreeElement(0.1, **BASE)


# ---------------------------------------------------------------- cenario 1
def scenario_baseline():
    r = run(baseline(), duration=900, load=LOAD_NORMAL)
    apply_style()
    fig, ax = plt.subplots(3, 1, figsize=(9.5, 8), sharex=True,
                           gridspec_kw=dict(height_ratios=[2.2, 1, 1]))
    level_bands(ax[0])
    ax[0].plot(r["t"], r["NR"], color=BLUE, label="nivel narrow-range (real)")
    ax[0].set_ylim(10, 90)
    ax[0].set_ylabel("nivel [%]")
    ax[0].set_title("1 · Linha de base: controle a tres elementos em seguimento de carga",
                    loc="left", fontsize=12, pad=12)
    ax[0].legend(loc="upper left")

    ax[1].plot(r["t"], r["q_st"], color=ORANGE, label="vazao de vapor (carga)")
    ax[1].plot(r["t"], r["q_fw"], color=AQUA, label="vazao de agua de alimentacao")
    ax[1].set_ylabel("fracao do nominal")
    ax[1].legend(loc="upper right", ncol=2)

    ax[2].plot(r["t"], r["dist"], color=MUTED,
               label="desbalanco nao medido (purga + temperatura)")
    ax[2].set_ylabel("fracao")
    ax[2].set_xlabel("tempo [s]")
    ax[2].legend(loc="upper right")
    for a in ax:
        a.grid(axis="y", alpha=0.7)
    m = evaluate(r)
    ax[0].text(0.30, 0.935,
               f"sem trip · margem minima ao trip {m['margem minima ao trip [%]']:.1f} %"
               f" · IAE {m['IAE [%.s]']:.0f} %·s",
               transform=ax[0].transAxes, fontsize=9, color=INK2)
    finish(fig, os.path.join(FIGS, "fig1_linha_de_base.png"))
    return {"linha de base": m}


# ---------------------------------------------------------------- cenario 2
def scenario_governor():
    agent = lambda: MisguidedAgent(0.1, Kd_wrong=0.55)
    r_free = run(agent(), duration=800, load=LOAD_SEVERE)
    gov = SafetyGovernor(baseline(), PlantParams(), Envelope())
    r_gov = run(agent(), duration=800, load=LOAD_SEVERE, governor=gov)

    apply_style()
    fig, ax = plt.subplots(2, 2, figsize=(12, 7), sharex=True, sharey="row")
    for col, (r, ttl) in enumerate([
            (r_free, "sem garantia em tempo de execucao"),
            (r_gov, "com governor (envelope + reversao)")]):
        a = ax[0][col]
        level_bands(a, label=(col == 1))
        a.plot(r["t"], r["NR"], color=BLUE if col else RED,
               label="nivel narrow-range (real)")
        a.set_ylim(-10, 110)
        a.set_title(ttl, loc="left", fontsize=11, pad=8)
        if col == 0:
            a.set_ylabel("nivel [%]")
        for k, (tt, msg) in enumerate(r["trip_log"]):
            a.axvline(tt, color=RED, lw=1.2, ls="--")
            a.annotate(msg.split(" -> ")[1], xy=(tt, 104 - 9 * k), fontsize=8,
                       color=RED, ha="left", va="top", xytext=(6, 0),
                       textcoords="offset points")
        a.grid(axis="y", alpha=0.7)
        a.legend(loc="lower left")

        b = ax[1][col]
        b.plot(r["t"], r["u"], color=ORANGE, label="comando de valvula aplicado")
        if col == 1:
            b.fill_between(r["t"], 0, 1.3, where=~r["on_agent"], color=VIOLET,
                           alpha=0.20, lw=0,
                           label="linha de base assume (veto do governor)")
            for (tt, ev, why) in gov.events:
                color = VIOLET if "VETO" in ev else (RED if "LOCKOUT" in ev else MUTED)
                b.axvline(tt, color=color, lw=1.0, ls=":")
            lock = [e for e in gov.events if "LOCKOUT" in e[1]]
            if lock:
                b.annotate("LOCKOUT: politica removida do laco",
                           xy=(lock[0][0], 1.15), fontsize=8, color=RED,
                           ha="left", xytext=(6, 0), textcoords="offset points")
            b.annotate(f"{gov.interventions} veto(s) do governor", xy=(0.02, 0.88),
                       xycoords="axes fraction", fontsize=9, color=VIOLET)
        b.set_ylim(0, 1.3)
        b.set_xlabel("tempo [s]")
        if col == 0:
            b.set_ylabel("fracao de abertura")
        b.grid(axis="y", alpha=0.7)
        b.legend(loc="lower left")
    fig.suptitle("2 · A mesma politica de IA, com e sem o envelope de seguranca\n"
                 "em carga normal ela e numericamente identica ao controlador aprovado",
                 x=0.005, ha="left", fontsize=13, y=1.02)
    finish(fig, os.path.join(FIGS, "fig2_governor.png"))
    r_base_sev = run(baseline(), duration=800, load=LOAD_SEVERE)
    r_norm_base = run(baseline(), duration=900, load=LOAD_NORMAL)
    r_norm_agent = run(agent(), duration=900, load=LOAD_NORMAL)
    return ({"linha de base": evaluate(r_base_sev),
             "agente sozinho": evaluate(r_free),
             "agente + governor": evaluate(r_gov)},
            {"linha de base (carga normal)": evaluate(r_norm_base),
             "agente (carga normal)": evaluate(r_norm_agent)})


# ---------------------------------------------------------------- cenario 3
def scenario_sensor():
    drift = [SensorFault("drift", t_start=200.0, rate=0.12), None, None]
    flat = lambda t: 1.0
    r_ok = run(baseline(), duration=900, load=flat, faults=drift,
               voting="2oo3", aggregate="median")
    r_1oo1 = run(baseline(), duration=900, load=flat, faults=drift,
                 voting="1oo1", aggregate="median")
    r_mean = run(baseline(), duration=900, load=flat, faults=drift,
                 voting="2oo3", aggregate="mean")

    apply_style()
    fig, ax = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True,
                           gridspec_kw=dict(height_ratios=[1.1, 1.4]))
    ax[0].axhline(80, color=RED, lw=1.2)
    ax[0].text(0.995, 81.5, "setpoint do bistavel HI-HI", color=RED, fontsize=8,
               ha="right", transform=ax[0].get_yaxis_transform())
    ax[0].plot(r_ok["t"], r_ok["ch1"], color=RED, label="LT-1 (em deriva)")
    ax[0].plot(r_ok["t"], r_ok["ch2"], color=BLUE, lw=3.2, label="LT-2")
    ax[0].plot(r_ok["t"], r_ok["ch3"], color=AQUA, lw=1.4, label="LT-3")
    ax[0].set_ylabel("leitura [%]")
    ax[0].set_ylim(30, 120)
    ax[0].set_title("3 · Um transmissor mente. O que a arquitetura faz com isso?",
                    loc="left", fontsize=12, pad=12)
    ax[0].legend(loc="upper left", ncol=3)

    level_bands(ax[1], label=True)
    ax[1].plot(r_ok["t"], r_ok["NR"], color=AQUA,
               label="2oo3 + mediana — a planta nem percebe")
    ax[1].plot(r_mean["t"], r_mean["NR"], color=ORANGE,
               label="2oo3 + media — protecao ok, controle enganado")
    ax[1].plot(r_1oo1["t"], r_1oo1["NR"], color=RED,
               label="canal unico — trip espurio e planta desligada")
    ax[1].set_ylim(-10, 90)
    ax[1].set_ylabel("nivel real [%]")
    ax[1].set_xlabel("tempo [s]")
    ax[1].legend(loc="lower left")
    for a in ax:
        a.grid(axis="y", alpha=0.7)
    finish(fig, os.path.join(FIGS, "fig3_sensores.png"))
    return {"2oo3+mediana": evaluate(r_ok), "2oo3+media": evaluate(r_mean),
            "1oo1": evaluate(r_1oo1)}


# ---------------------------------------------------------------- cenario 4
def scenario_phase():
    agent = lambda: MisguidedAgent(0.1, Kd_wrong=0.55)
    r_free = run(agent(), duration=800, load=LOAD_SEVERE)
    gov = SafetyGovernor(baseline(), PlantParams(), Envelope())
    r_gov = run(agent(), duration=800, load=LOAD_SEVERE, governor=gov)
    r_base = run(baseline(), duration=800, load=LOAD_SEVERE)

    def smooth(x, n=40):
        k = np.ones(n) / n
        return np.convolve(x, k, mode="same")

    apply_style()
    fig, ax = plt.subplots(figsize=(9, 6.4))
    ax.axvspan(-20, 20, color=RED, alpha=0.10, lw=0)
    ax.axvspan(80, 120, color=RED, alpha=0.10, lw=0)
    ax.add_patch(plt.Rectangle((30, -2.0), 40, 4.0, fill=False, lw=1.2,
                               ls="--", edgecolor=VIOLET))
    ax.plot(r_free["NR"][:-40], smooth(r_free["rate"])[:-40], color=RED, lw=1.4,
            alpha=0.85, label="agente sozinho — sai do envelope e dispara o ESFAS")
    ax.plot(r_gov["NR"][:-40], smooth(r_gov["rate"])[:-40], color=BLUE, lw=1.6,
            label="agente + governor — contido dentro do envelope")
    ax.plot(r_base["NR"][:-40], smooth(r_base["rate"])[:-40], color=AQUA, lw=1.8,
            label="linha de base (three-element)")
    ax.set_xlim(-5, 108)
    ax.set_ylim(-3, 3)
    ax.set_xlabel("nivel narrow-range [%]")
    ax.set_ylabel("taxa de variacao do nivel [%/s]  (media movel de 4 s)")
    ax.set_title("4 · Plano de fase: o envelope e uma regiao, nao um limite escalar",
                 loc="left", fontsize=12, pad=12)
    ax.text(31, 2.15, "envelope de seguranca (governor)", color=VIOLET, fontsize=9)
    ax.text(1, -2.75, "regiao do ESFAS", color=RED, fontsize=9)
    ax.text(82, -2.75, "regiao do ESFAS", color=RED, fontsize=9)
    ax.grid(alpha=0.5)
    ax.legend(loc="upper center", fontsize=9)
    finish(fig, os.path.join(FIGS, "fig4_envelope.png"))


if __name__ == "__main__":
    rows = {}
    scenario_baseline()
    sev_rows, norm_rows = scenario_governor()
    rows.update(sev_rows)
    print("\n=== ACEITACAO EM CARGA NORMAL: indistinguiveis ===\n")
    print(table(norm_rows))
    print("\n=== REJEICAO DE CARGA SEVERA: desempenho x seguranca ===\n")
    print(table(rows))
    print("\n=== ARQUITETURA DE MEDICAO (transmissor em deriva) ===\n")
    print(table(scenario_sensor()))
    scenario_phase()
    print("\nfiguras salvas em figs/")
