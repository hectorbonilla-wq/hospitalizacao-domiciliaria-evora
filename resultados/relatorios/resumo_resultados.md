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
| Subsecções elegíveis (≤ 30 min) | 1 804 |
| Subsecções não elegíveis | 7 944 |
| Subsecções sem tempo calculado (incluídas nas não elegíveis) | 0 |
| População residente total analisada (Censos 2021) | 240 452 |
| **População residente abrangida (subsecções elegíveis)** | **59 756** |
| **Percentagem da população analisada abrangida** | **24.85 %** |
| População abrangida em **condições reais estimadas** (fluxo livre × 1.15 + 3 min (estimativa) ≤ 30 min) | 54 604 (1 510 subsecções) |
| Subsecções próximas do limite (27–33 min) | 593 |
| População nas subsecções próximas do limite | 14 680 |

Nota: a "população total analisada" é a de todas as subsecções com centroide a ≤ 65 km em linha reta; a percentagem depende desta escolha.

## 2. Tempos e distâncias de viagem (subsecções elegíveis)

| Medida | Mínimo | Mediana | Média | Máximo | Média por residente |
|---|---:|---:|---:|---:|---:|
| Tempo hospital → domicílio (min) | 0.12 | 7.21 | 12.39 | 30.0 | 9.49 |
| Tempo domicílio → hospital (min) | 0.39 | 6.42 | 11.87 | 36.27 | 8.95 |
| Distância hospital → domicílio (km) | 0.05 | 4.51 | 10.24 | 39.08 | 7.51 |
| Distância domicílio → hospital (km) | 0.12 | 3.97 | 9.96 | 45.27 | 7.22 |

## 3. Sensibilidade ao limite de tempo

| Limite (min) | Subsecções | População abrangida | % da população analisada |
|---:|---:|---:|---:|
| 20 | 1 259 | 49 383 | 20.54 % |
| 25 | 1 567 | 55 665 | 23.15 % |
| 27 | 1 635 | 56 797 | 23.62 % |
| 30 | 1 804 | 59 756 | 24.85 % |
| 33 | 2 228 | 71 477 | 29.73 % |
| 35 | 2 399 | 76 872 | 31.97 % |
| 40 | 3 123 | 97 635 | 40.6 % |
| 45 | 3 736 | 111 920 | 46.55 % |

**Comparação entre motores de routing (sensibilidade):** a população com centroide dentro da isócrona de 30 min do Valhalla é 49 889 residentes (OSRM: 59 756). 70.3 % dos centroides elegíveis segundo o OSRM estão dentro da isócrona do Valhalla. O Valhalla usa velocidades mais prudentes; o resultado oficial do estudo é o do OSRM.

## 4. População elegível por município

| Município | Subsecções elegíveis | População elegível | População analisada | % do município analisado |
|---|---:|---:|---:|---:|
| Évora | 1526 | 53 240 | 53 577 | 99.4 % |
| Arraiolos | 178 | 3 922 | 6 606 | 59.4 % |
| Viana do Alentejo | 40 | 1 205 | 5 318 | 22.7 % |
| Portel | 27 | 697 | 5 747 | 12.1 % |
| Estremoz | 13 | 377 | 12 680 | 3.0 % |
| Redondo | 9 | 207 | 6 286 | 3.3 % |
| Montemor-o-Novo | 11 | 108 | 15 799 | 0.7 % |

## 5. Capacidade operacional — CENÁRIO ILUSTRATIVO (pressupostos, não dados)

A população elegível **não** é o número de doentes que o serviço consegue acompanhar.
O cenário seguinte usa os pressupostos editáveis em `config.py`:

* Equipas: 1 (1 médico + 1 enfermeiro); viaturas: 1 (ligeiras de 5 lugares, incluindo o condutor)
* Turno útil: 420 min; duração da visita: 45 min; deslocação entre domicílios: 15 min; visitas por doente/dia: 1

| Caso | Ida (min) | Regresso (min) | Visitas/equipa/dia | Doentes acompanhados |
|---|---:|---:|---:|---:|
| Tempos médios por residente elegível | 9.5 | 8.9 | 6 | 6 |
| Pior caso (domicílio a 30 min) | 30 | 30 | 6 | 6 |

## 6. Fontes e reprodutibilidade

* População e geografia: INE — Censos 2021 (resultados definitivos), BGRI 2021; recolha em 2026-11-10T14:51:05 a partir de https://mapas.ine.pt/
* Routing: OSRM (Open Source Routing Machine) — serviço /table em https://router.project-osrm.org, perfil "driving"; cálculo entre 2026-11-10T14:51:53 e 2026-11-10T14:57:43; rede OpenStreetMap; sem trânsito em tempo real
* Isócrona: Valhalla — serviço /isochrone em https://valhalla1.openstreetmap.de ({'versao': '3.9.1-52228c4', 'dados_osm_modificados_em': '2026-11-10'}); recortada pelo território português
* Metadados completos (SHA-256 dos ficheiros, parâmetros, versões): `registo/metadados_execucao.json`

## 7. Limitações a ter em conta

* **Centroides:** cada subsecção é representada pelo centro geométrico do polígono; os residentes não vivem todos nesse ponto. Subsecções perto dos 30 min (ver secção 3) podem ter parte dos domicílios dentro e parte fora do limite.
* **Tempos de viagem:** estimados pelo OSRM em fluxo livre (sem trânsito, semáforos ou estacionamento); o tempo real tende a ser um pouco maior.
* **Rede rodoviária:** OpenStreetMap pode ter estradas em falta ou mal classificadas.
* **População:** residentes em 2021 (Censos); não inclui alterações posteriores.
