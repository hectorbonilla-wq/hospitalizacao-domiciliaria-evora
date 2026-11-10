# Resumo — População potencialmente abrangida pela Hospitalização Domiciliária

**Hospital:** ULS do Alentejo Central – Hospital do Espírito Santo de Évora (Hospitalização Domiciliária)  
**Morada:** Largo do Senhor da Pobreza, 7000-811 Évora  
**Coordenadas:** 38.5688861, -7.9031778 (38º34'07.99" N, 7º54'11.44" W)  
**Critério:** tempo de viagem de automóvel hospital → domicílio ≤ 30 min  
**Âmbito territorial:** apenas Portugal (subsecções da BGRI 2021)

## 1. Resultados principais (dados observados + tempos calculados)

| Indicador | Valor |
|---|---:|
| Subsecções estatísticas analisadas | 9 748 |
| Subsecções elegíveis (≤ 30 min) | 1 698 |
| Subsecções não elegíveis | 8 050 |
| Subsecções sem tempo calculado (incluídas nas não elegíveis) | 1 |
| População residente total analisada (Censos 2021) | 240 452 |
| **População residente abrangida (subsecções elegíveis)** | **57 435** |
| **Percentagem da população analisada abrangida** | **23.89 %** |
| População abrangida em **condições reais estimadas** (fluxo livre × 1.15 + 3 min (estimativa) ≤ 30 min) | 49 875 (1 307 subsecções) |
| Subsecções próximas do limite (27–33 min) | 372 |
| População nas subsecções próximas do limite | 6 338 |

Nota: a "população total analisada" é a de todas as subsecções com centroide a ≤ 65 km em linha reta; a percentagem depende desta escolha.

## 2. Tempos e distâncias de viagem (subsecções elegíveis)

| Medida | Mínimo | Mediana | Média | Máximo | Média por residente |
|---|---:|---:|---:|---:|---:|
| Tempo hospital → domicílio (min) | 0.18 | 10.4 | 13.79 | 29.97 | 11.39 |
| Tempo domicílio → hospital (min) | 0.48 | 8.93 | 12.93 | 31.11 | 10.51 |
| Distância hospital → domicílio (km) | 0.05 | 4.22 | 8.96 | 30.15 | 6.56 |
| Distância domicílio → hospital (km) | 0.12 | 3.65 | 8.58 | 29.93 | 6.13 |

## 3. Sensibilidade ao limite de tempo

| Limite (min) | Subsecções | População abrangida | % da população analisada |
|---:|---:|---:|---:|
| 20 | 1 206 | 48 337 | 20.1 % |
| 25 | 1 425 | 52 597 | 21.87 % |
| 27 | 1 597 | 56 055 | 23.31 % |
| 30 | 1 698 | 57 435 | 23.89 % |
| 33 | 1 968 | 62 321 | 25.92 % |
| 35 | 2 170 | 67 432 | 28.04 % |
| 40 | 2 732 | 83 493 | 34.72 % |
| 45 | 3 652 | 108 611 | 45.17 % |

**Isócrona (OpenRouteService — serviço de isócronas):** população com centroide dentro da isócrona de 30 min = 58 106 residentes; 99.8 % dos centroides elegíveis estão dentro dela. O resultado oficial é o da matriz (secção 1).

**Comparação entre motores de routing (mesma população, mesmos centroides):**

| Motor | Subsecções elegíveis | População abrangida |
|---|---:|---:|
| OpenRouteService | 1 698 | 57 435 |
| OSRM | 1 804 | 59 756 |

## 4. População elegível por município

| Município | Subsecções elegíveis | População elegível | População analisada | % do município analisado |
|---|---:|---:|---:|---:|
| Évora | 1493 | 52 717 | 53 577 | 98.4 % |
| Arraiolos | 166 | 3 779 | 6 606 | 57.2 % |
| Viana do Alentejo | 32 | 855 | 5 318 | 16.1 % |
| Montemor-o-Novo | 7 | 84 | 15 799 | 0.5 % |

## 5. Capacidade operacional — CENÁRIO ILUSTRATIVO (pressupostos, não dados)

A população elegível **não** é o número de doentes que o serviço consegue acompanhar.
O cenário seguinte usa os pressupostos editáveis em `config.py`:

* Equipas: 1 (1 médico + 1 enfermeiro); viaturas: 1 (ligeiras de 5 lugares, incluindo o condutor)
* Turno útil: 420 min; duração da visita: 45 min; deslocação entre domicílios: 15 min; visitas por doente/dia: 1

| Caso | Ida (min) | Regresso (min) | Visitas/equipa/dia | Doentes acompanhados |
|---|---:|---:|---:|---:|
| Tempos médios por residente elegível | 11.4 | 10.5 | 6 | 6 |
| Pior caso (domicílio a 30 min) | 30 | 30 | 6 | 6 |

## 6. Fontes e reprodutibilidade

* População e geografia: INE — Censos 2021 (resultados definitivos), BGRI 2021; recolha em 2026-11-10T14:51:05 a partir de https://mapas.ine.pt/
* Routing: OpenRouteService (driving-car) — https://api.openrouteservice.org em https://api.openrouteservice.org, perfil "driving-car"; cálculo entre 2026-11-10T16:18:48 e 2026-11-10T16:19:11; rede OpenStreetMap; sem trânsito em tempo real
* Isócrona: OpenRouteService — serviço de isócronas em https://api.openrouteservice.org (None); recortada pelo território português
* Metadados completos (SHA-256 dos ficheiros, parâmetros, versões): `registo/metadados_execucao.json`

## 7. Limitações a ter em conta

* **Centroides:** cada subsecção é representada pelo centro geométrico do polígono; os residentes não vivem todos nesse ponto. Subsecções perto dos 30 min (ver secção 3) podem ter parte dos domicílios dentro e parte fora do limite.
* **Tempos de viagem:** estimados pelo OpenRouteService (driving-car) — https://api.openrouteservice.org em fluxo livre (sem trânsito, semáforos ou estacionamento); o tempo real tende a ser um pouco maior.
* **Rede rodoviária:** OpenStreetMap pode ter estradas em falta ou mal classificadas.
* **População:** residentes em 2021 (Censos); não inclui alterações posteriores.
