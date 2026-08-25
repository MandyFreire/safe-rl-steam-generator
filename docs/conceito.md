# AEGIS-SG — projeto de conceito

_Criado em 25/08/2026. Escopo: 6 semanas, ~8 h/semana. Esqueleto de código já rodando._

**Pitch de uma linha:** um agente de IA controla o nível de um gerador de vapor;
uma camada determinística garante que ele nunca chegue perto de desligar a planta.

---

## 1. Por que este projeto, e por que ela

A vitrine de dados da Fase 1 do plano de carreira pedia "1–2 mini-projetos".
Este não é um mini-projeto genérico de manutenção preditiva — é o único e que eu escolhi fazer.

| Ativo | Como aparece no projeto |
|---|---|
| Nuclear crítico | ESFAS/RPS reais: LO-LO → trip + AFW; HI-HI → trip de turbina + isolamento |
| Segurança funcional certificada | camadas independentes, votação 2oo3, latch, tempo de resposta, testes como validação de SIF |
| Controle e sintonia | planta de fase não-mínima (shrink & swell), controle a três elementos, feedforward |
| Transição para dados/produto | ML, métricas, dashboard, decisão de arquitetura documentada |

O território — **IA dentro de ambiente regulado, sem mentir sobre o que ela
pode reivindicar** — está praticamente vazio em português. E é o mesmo
raciocínio que banco e fintech chamam de gestão de risco de modelo.

## 2. A tese

A pergunta comum ("IA pode ser SIL 3?") é a errada. A pergunta é:

> **Onde a IA pode ficar, para que a planta fique melhor sem que o argumento
> de segurança fique pior?**

Resposta em três camadas, com independência entre elas:

1. **Controle** (não relacionada à segurança) — aqui a IA pode ficar. RL/MPC.
2. **Garantia em tempo de execução** — envelope + previsão + reversão para um
   controlador comprovado (arquitetura Simplex). Determinística, sem IA,
   testável exaustivamente.
3. **Proteção** (RPS/ESFAS) — bistáveis, 2oo3, latch. **Nunca** contém IA.

A camada 2 age **antes** do limite de segurança, para que a camada 3 nunca
precise agir. Frase-síntese do projeto:
**um trip é um sucesso da proteção e um fracasso do controle.**

## 3. A planta (e por que ela é difícil de propósito)

Nível narrow-range de gerador de vapor, com **shrink & swell**: abrir a válvula
de água de alimentação faz o nível **cair** antes de subir. Fase não-mínima,
zero em `s = +1/6 s⁻¹`.

Isso não é enfeite. É o que:

- quebra sintonia por tentativa e erro;
- quebra RL de horizonte curto, que aprende a correlação invertida
  ("nível caindo → fechar a válvula");
- é uma das maiores causas de trip espúrio em plantas reais.

A condição `K_sw > K_m · τ_sw` está codificada e coberta por teste. Se ela cai,
o projeto perde o objeto — foi um erro real cometido e corrigido na montagem
do esqueleto, e vale como história.

## 4. O que já está de pé (semana 0)

Código rodando, com testes:

- modelo do gerador de vapor com resposta inversa, ruído e desbalanço não medido;
- 3 transmissores redundantes com modos de falha (deriva, congelado, viés);
- ESFAS/RPS com bistáveis, histerese, votação 2oo3/1oo3/1oo1, latch e tempo de resposta;
- controle a três elementos (linha de base) e um agente proxy que extrapola errado;
- governor com envelope, previsão de 45 s, reversão suave e *lockout* por reincidência;
- ambiente Gymnasium com o governor **dentro** do laço (shielded RL);
- 14 casos de teste escritos como validação de função instrumentada;
- 4 figuras e a tabela de métricas.

**Resultado central (rejeição de carga de 100 % → 45 % em 25 s):**

| | linha de base | agente sozinho | agente + governor |
|---|---:|---:|---:|
| IAE [%·s] | 1564 | 12117 | **1219** |
| desvio máximo [%] | 14,4 | 55,4 | **8,4** |
| margem mínima ao trip [%] | 15,6 | −25,4 | **21,6** |
| trips | 0 | 1 | **0** |

Em carga normal, agente e controlador aprovado são **numericamente idênticos**
(IAE 824,97 nos dois). A política passa em qualquer teste de aceitação e falha
exatamente onde ninguém testou. Com a contenção, ela entrega mais desempenho
**e** mais margem que a linha de base.

## 5. Roadmap de 6 semanas (~8 h/semana)

| Semana | Entrega | Como saber que terminou |
|---|---|---|
| 1 | Consolidar a linha de base e a campanha de ensaios | matriz cenário × semente rodando por script; métricas de segurança separadas das de desempenho |
| 2 | MPC com restrição rígida no envelope | MPC bate o PID no IAE sem reduzir a margem mínima; vira o teto de referência |
| 3 | RL (SAC) treinado com o governor no laço | política supera o PID em ≥ 2 cenários; zero trips em 100 episódios de avaliação |
| 4 | Robustez: falhas de sensor, atuador travado, deriva de modelo | tabela de degradação graciosa; nº de vetos como indicador de saúde da política |
| 5 | Dashboard + OPC UA (opcional) | página única com trajetórias, métricas e eventos do governor |
| 5b |HIL com microcontrolador (decidido em 25/08, para depois) — ESP32 ou Pico W roda o controlador em C, a planta segue em Python no PC, via Modbus TCP . O ganho não é realismo físico e sim temporização: tempo de ciclo, jitter e perda de pacote passam a existir, e o governor precisa decidir com dados atrasados.	| malha fechada por rede, com o atraso medido e reportado nas métricas|
| 6 | Caso de segurança + README em inglês | documento que diz o que é reivindicado, o que **não** é, e por quê |

**Regra de corte:** semanas 5 e 6 são as primeiras a encolher. O projeto já é
publicável ao fim da semana 3.

## 6. Critérios de sucesso

- **Técnico:** zero trips em toda a campanha de avaliação com o governor ativo;
  IAE melhor que a linha de base em pelo menos dois cenários; ≥ 90 % do tempo
  sob o agente em operação normal.
- **De carreira:** um repositório que um gestor de produto entende pelo README
  e um engenheiro de segurança respeita pelos testes.
- **De conteúdo:** 4 posts com história própria, não tutorial.

## 7. Riscos

| Risco | Mitigação |
|---|---|
| Treinamento de RL consome as 6 semanas | o projeto já é publicável sem RL; MPC é plano B legítimo |
| Virar "mais um projeto de RL em simulador" | a diferenciação é a camada de segurança e os testes, não o agente |
| Afirmar demais sobre normas | falar de *arquitetura compatível com*, nunca de conformidade; citar ISO/IEC TR 5469 como referência, não como selo |
| Perfeccionismo no modelo da planta | modelo de ordem reduzida é declarado como tal no README; fidelidade não é o entregável |

## 8. Mapa de conteúdo — encaixa no calendário já existente

| Data | Slot do plano | Post |
|---|---|---|
| 07/10 | Dados | **"Meu controlador de IA era idêntico ao PID em todos os testes. Aí veio a rejeição de carga."** Cena: as duas linhas sobrepostas no gráfico, IAE igual até a terceira casa. Lição: desempenho médio no conjunto de teste não é argumento de segurança. POV: quem valida modelo por métrica agregada está validando a parte fácil. Pergunta: como vocês testam o comportamento fora da distribuição? |
| 21/10 | Nuclear | **"Um transmissor de nível subiu 70 % e a planta nem percebeu."** Cena: as três leituras divergindo. Lição: 2oo3 e mediana. POV: a votação te protege do trip espúrio, não da agregação errada no controle — no caso da média, o nível real chegou a 1,8 % do setpoint de trip. Pergunta: quantos sistemas por aí fazem média de sensores redundantes? |
| 04/11 | Gestão ★ | **"Um trip é um sucesso da segurança e um fracasso do controle."** Lição: a diferença entre agir antes e agir depois do limite. POV: o mesmo raciocínio vale para gestão — quando o plano de contingência dispara, o problema não foi resolvido, foi contido. Pergunta: quais são os "trips" do seu processo? |
| 18/11 | Produto ★ | **"Onde a IA pode ficar."** Lição: alocação de funções por camada; o que o produto pode reivindicar e o que não pode. POV: a decisão de arquitetura de IA é, antes de tudo, uma decisão de produto sobre risco. Pergunta: quem na sua empresa decide onde o modelo pode ficar? |

Extra para reciclagem: o erro do zero no semiplano errado ("passei duas horas
convencida de que a planta era difícil — ela não era, e o teste que escrevi
depois é o que me impede de repetir isso").

## 9. Referências

- IEC 61508 / IEC 61511 — segurança funcional, SIL, independência de camadas.
- ISO/IEC TR 5469:2024 — *Artificial intelligence — Functional safety and AI systems*.
- IEC 61513 — I&C de segurança em instalações nucleares.
- Sha, L. (2001) — *Using simplicity to control complexity* (arquitetura Simplex).

---
_Código: `aegis-sg.zip` (roda com numpy + matplotlib + pytest)._
