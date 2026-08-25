"""
Testes da camada de PROTECAO, escritos como casos de validacao de SIF.

Este arquivo e o argumento de seguranca do projeto em forma executavel:
a logica de protecao e pequena o bastante para ser testada
exaustivamente - e por isso ela nao pode conter IA.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aegis.protection import ProtectionSystem, TripSetpoints
from aegis.governor import SafetyGovernor, Envelope, predict
from aegis.plant import PlantParams
from aegis.controllers import ThreeElement

DT = 0.1


def drive(rps, readings_fn, duration=10.0):
    for i in range(int(duration / DT)):
        t = i * DT
        rps.scan(readings_fn(t), t)
    return rps.s


def test_um_canal_baixo_nao_dispara_2oo3():
    rps = ProtectionSystem(dt=DT)
    s = drive(rps, lambda t: [10.0, 50.0, 50.0])
    assert not s.reactor_trip and s.votes_lo == 1


def test_dois_canais_baixos_disparam_reator_e_afw():
    rps = ProtectionSystem(dt=DT)
    s = drive(rps, lambda t: [10.0, 12.0, 50.0])
    assert s.reactor_trip and s.afw_actuated
    assert not s.turbine_trip


def test_dois_canais_altos_disparam_turbina_e_isolamento():
    rps = ProtectionSystem(dt=DT)
    s = drive(rps, lambda t: [85.0, 88.0, 50.0])
    assert s.turbine_trip and s.fw_isolated


def test_tempo_de_resposta_e_respeitado():
    """Nao pode atuar antes do tempo de resposta declarado, nem muito depois."""
    sp = TripSetpoints(response_time=1.0)
    rps = ProtectionSystem(sp, dt=DT)
    for i in range(int(0.9 / DT)):
        rps.scan([10.0, 10.0, 50.0], i * DT)
    assert not rps.s.reactor_trip
    for i in range(int(0.9 / DT), int(1.5 / DT)):
        rps.scan([10.0, 10.0, 50.0], i * DT)
    assert rps.s.reactor_trip
    assert rps.log[0][0] == pytest.approx(1.0, abs=0.15)


def test_trip_fica_travado_apos_condicao_normalizar():
    rps = ProtectionSystem(dt=DT)
    drive(rps, lambda t: [10.0, 10.0, 50.0], 5.0)
    assert rps.s.reactor_trip
    drive(rps, lambda t: [50.0, 50.0, 50.0], 60.0)
    assert rps.s.reactor_trip, "latch: so reset manual pode limpar um trip"
    rps.manual_reset()
    assert not rps.s.reactor_trip


def test_ruido_no_setpoint_nao_gera_trip_espurio():
    """1e6 amostras oscilando 0,25 % em torno de +3 % do setpoint: zero trips."""
    rng = np.random.default_rng(1)
    rps = ProtectionSystem(dt=DT)
    for i in range(20000):
        rps.scan(list(23.0 + rng.normal(0, 0.25, 3)), i * DT)
    assert not rps.tripped


def test_histerese_evita_chattering_do_bistavel():
    sp = TripSetpoints(deadband=2.0)
    rps = ProtectionSystem(sp, dt=DT)
    rps.scan([19.5, 50.0, 50.0], 0.0)
    assert rps.s.channel_lo[0]
    rps.scan([21.0, 50.0, 50.0], 0.1)          # dentro da banda morta
    assert rps.s.channel_lo[0], "bistavel nao deve resetar dentro da banda morta"
    rps.scan([23.0, 50.0, 50.0], 0.2)
    assert not rps.s.channel_lo[0]


def test_votacao_1oo1_e_menos_segura_que_2oo3():
    """Documenta a diferenca: um unico canal em deriva derruba a planta."""
    a = ProtectionSystem(dt=DT, voting="1oo1")
    b = ProtectionSystem(dt=DT, voting="2oo3")
    for rps in (a, b):
        drive(rps, lambda t: [85.0, 50.0, 50.0], 5.0)
    assert a.tripped and not b.tripped


# ------------------------- camada de garantia -------------------------
def test_governor_veta_acao_que_sai_do_envelope():
    p, env = PlantParams(), Envelope()
    gov = SafetyGovernor(ThreeElement(DT), p, env, dt=DT)
    st = dict(NR=50.0, m=50.0, x_sw=0.0, q_fw=1.0, q_st=1.0)
    u, on_agent = gov(0.0, st, 1.0, 0.0, 0.0)     # fechar a valvula: esvazia o SG
    assert not on_agent and gov.interventions == 1


def test_governor_aceita_acao_segura():
    p, env = PlantParams(), Envelope()
    gov = SafetyGovernor(ThreeElement(DT), p, env, dt=DT)
    st = dict(NR=50.0, m=50.0, x_sw=0.0, q_fw=1.0, q_st=1.0)
    u, on_agent = gov(1.0, st, 1.0, 0.0, 0.0)     # manter o balanco
    assert on_agent and u == 1.0


def test_governor_trava_apos_tres_vetos():
    p = PlantParams()
    gov = SafetyGovernor(ThreeElement(DT), p, Envelope(max_strikes=3),
                         check_every=DT, dt=DT)
    st = dict(NR=50.0, m=50.0, x_sw=0.0, q_fw=1.0, q_st=1.0)
    for k in range(3):
        gov.in_baseline = False
        gov.t_switch = -1e9
        gov(0.0, st, 1.0, 0.0, k * 100.0)
    assert gov.locked_out
    _, on_agent = gov(1.0, st, 1.0, 0.0, 500.0)
    assert not on_agent, "apos lockout o agente nao volta sem reset manual"


def test_previsao_do_envelope_acerta_a_direcao():
    """Fechar a valvula esvazia o SG; manter a valvula aberta demais enche."""
    p, env = PlantParams(), Envelope(horizon=60.0)
    bad_lo, lo, _ = predict(50, 50, 0, 1.0, 1.0, 0.0, 1.0, p, env)
    assert bad_lo and lo < Envelope().NR_min

    bad_hi, _, hi = predict(50, 50, 0, 1.0, 1.0, 1.2, 1.0, p, env)
    assert bad_hi and hi > Envelope().NR_max


def test_previsao_captura_a_resposta_inversa():
    """
    Abrir a valvula faz o nivel CAIR antes de subir (shrink).
    O horizonte de previsao precisa ser longo o bastante para enxergar
    alem da resposta inversa - senao o governor aprende a mesma licao
    errada que o agente.
    """
    p = PlantParams()
    _, lo_curto, hi_curto = predict(50, 50, 0, 1.0, 1.0, 1.2, 1.0, p,
                                    Envelope(horizon=8.0))
    _, _, hi_longo = predict(50, 50, 0, 1.0, 1.0, 1.2, 1.0, p,
                             Envelope(horizon=60.0))
    assert lo_curto < 50.0, "no curto prazo o nivel CAI (shrink)"
    assert hi_curto <= 50.1, "8 s nao bastam para ver a subida do inventario"
    assert hi_longo > 65.0, "no horizonte correto o enchimento aparece"


def test_zero_da_planta_e_de_fase_nao_minima():
    """
    Sem isso o projeto nao tem objeto: se K_sw <= K_m*tau_sw o zero migra
    para o semiplano esquerdo e a planta vira trivial.
    """
    from aegis.plant import PlantParams as PP, zero_nao_minimo
    assert zero_nao_minimo(PP()) > 0
    assert zero_nao_minimo(PP(K_sw=30.0)) < 0
