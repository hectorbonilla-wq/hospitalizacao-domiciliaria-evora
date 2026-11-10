# População potencialmente abrangida pela Hospitalização Domiciliária — HESE Évora

Projeto em Python que estima **quantas pessoas residem a 30 minutos de automóvel, ou menos,**
do serviço de **Hospitalização Domiciliária da ULS do Alentejo Central – Hospital do Espírito
Santo de Évora** (Largo do Senhor da Pobreza, 7000-811 Évora).

* **Coordenadas do hospital (GPS):** 38º34'07.99" N | 7º54'11.44" W → **38.5688861, −7.9031778**
* **Fonte populacional (obrigatória):** INE — Censos 2021 (resultados definitivos) e BGRI 2021,
  ao nível da **subsecção estatística**
* **Rede rodoviária:** OpenStreetMap, com routing **OSRM** (tempos e distâncias) e **Valhalla**
  (apenas para desenhar a isócrona)
* **Âmbito territorial:** **apenas Portugal**

> ⚠️ **População elegível ≠ doentes acompanhados.** O estudo calcula quantos *residentes* vivem
> dentro do limite de 30 minutos. O número de doentes que o serviço consegue acompanhar por dia é
> muito menor e depende de equipas, viaturas e tempos de visita (ver secção 9).

## Começar em 3 comandos

```bash
git clone https://github.com/hectorbonilla-wq/hospitalizacao-domiciliaria-evora.git
```

```bash
cd hospitalizacao-domiciliaria-evora && pip install -r requirements.txt
```

```bash
python executar_tudo.py
```

Não quer executar nada? Os resultados de uma execução de 10/11/2026 já estão na pasta
`resultados/`. Descarregue `resultados/mapas/mapa_centroides.html` e abra-o no navegador, ou leia
`resultados/relatorios/resumo_resultados.md`.

**Licenças:** o código está sob licença MIT (ver `LICENSE`). Os dados populacionais e geográficos são
do **INE — Censos 2021 / BGRI 2021** (cite "Fonte: INE"). A rede rodoviária é do **© OpenStreetMap
contributors** (licença ODbL). Os ficheiros originais do INE não estão no repositório: a etapa 1
descarrega-os diretamente do portal oficial.

---

## Índice

1. [Instalação](#1-instalação)
2. [Execução rápida](#2-execução-rápida)
2B. [Parte B — Doentes por morada e matriz quadrada](#2b-parte-b--doentes-por-morada-e-matriz-quadrada)
3. [Estrutura das pastas](#3-estrutura-das-pastas)
4. [As etapas, uma a uma](#4-as-etapas-uma-a-uma)
5. [Configuração (config.py) e APIs](#5-configuração-configpy-e-apis)
6. [Ficheiros de resultados](#6-ficheiros-de-resultados)
7. [Exemplo de execução](#7-exemplo-de-execução)
8. [Guia de interpretação dos resultados](#8-guia-de-interpretação-dos-resultados)
9. [Elegibilidade geográfica vs. capacidade operacional](#9-elegibilidade-geográfica-vs-capacidade-operacional)
10. [Dados observados, pressupostos e aproximações](#10-dados-observados-pressupostos-e-aproximações)
11. [Limitações](#11-limitações)
12. [Erros comuns e como resolver](#12-erros-comuns-e-como-resolver)
13. [Lista de verificação](#13-lista-de-verificação)
14. [Reprodutibilidade](#14-reprodutibilidade)
15. [Como modificar o estudo](#15-como-modificar-o-estudo)

---

## 1. Instalação

**Requisitos:** Python 3.10 ou mais recente e ligação à Internet (≈ 150 MB de downloads do INE).

```bash
# 1) (recomendado) criar um ambiente virtual, para não misturar bibliotecas
python -m venv .venv
```

```bash
# 2) ativar o ambiente — Linux/macOS:
source .venv/bin/activate
```

```bash
# 2) ativar o ambiente — Windows (PowerShell):
.venv\Scripts\Activate.ps1
```

```bash
# 3) instalar as bibliotecas
pip install -r requirements.txt
```

Se o `pip` não conseguir instalar o `geopandas` no Windows, use o Anaconda:
`conda install -c conda-forge geopandas folium openpyxl requests`.

**Configurar as APIs:** não é preciso nenhuma chave. O projeto usa servidores públicos gratuitos:

| Serviço | Para quê | Endereço (em `config.py`) |
|---|---|---|
| INE — mapas.ine.pt | BGRI 2021 e Ficheiro Síntese dos Censos 2021 | `INE_PAGINAS_DOWNLOAD`, `INE_URL_BASE` |
| OSRM | tempos e distâncias de automóvel | `OSRM_URL = https://router.project-osrm.org` |
| Valhalla | isócrona de 30 min (só para o mapa) | `VALHALLA_URL = https://valhalla1.openstreetmap.de` |

Os servidores públicos têm limites de utilização (≈ 1 pedido por segundo). O programa respeita-os
com pausas entre pedidos. Para uso intensivo, ver a secção 5.3 (servidor OSRM próprio).

---

## 2. Execução rápida

```bash
python executar_tudo.py
```

Demora cerca de **8–12 minutos** (a maior parte é o routing no OSRM) e corre também a Parte B
com os doentes de exemplo. No fim, abra no navegador:

* `resultados/mapas/mapa_centroides.html`
* `resultados/mapas/mapa_poligonos_bgri.html`

e leia `resultados/relatorios/resumo_resultados.md`.

Para repetir **tudo do zero** (apaga os dados descarregados e os resultados e volta a calcular):

```bash
python executar_tudo.py --do-zero
```

Para recomeçar a partir de uma etapa (por exemplo, depois de mudar o limite de tempo):

```bash
python executar_tudo.py --desde 5
```

Testes rápidos, sem Internet:

```bash
python testes/test_funcoes.py
```

---

## 2B. Parte B — Doentes por morada e matriz quadrada

Para o trabalho diário do serviço: a partir de uma **lista de doentes identificados pela morada**,
o programa:

1. **converte cada morada em coordenadas** (geocodificação com Nominatim/OpenStreetMap, só em
   Portugal), registando o endereço encontrado e a precisão (número de porta, rua, código postal...);
2. calcula a **distância (km) e o tempo (min) de/para o hospital** de cada doente, nos dois sentidos;
3. **seleciona os doentes a ≤ 30 min** do hospital (tempo hospital → doente em condições reais estimadas);
4. constrói a **matriz quadrada** hospital + doentes selecionados (todos para todos), em km e em minutos;
5. verifica a matriz e exporta CSV, Excel e um mapa.

**1) Preparar o ficheiro** `doentes/os_meus_doentes.csv` (separador `;`, abre no Excel):

```text
id_doente;morada;codigo_postal;localidade
D01;Rua 5 de Outubro;7000-854;Évora
D02;Praça do Município;7040-027;Arraiolos
```

Opcional: colunas `latitude;longitude` — se preenchidas, a morada não é geocodificada.

**2) Executar:**

```bash
python matriz_doentes.py doentes/os_meus_doentes.csv
```

Sem argumento, usa o exemplo `doentes/doentes_exemplo.csv` (11 doentes **fictícios** em moradas de
locais públicos, incluindo um fora dos 30 min e uma morada inexistente, para mostrar os erros).

**3) Resultados** em `resultados/doentes/<nome_do_ficheiro>/`:

| Ficheiro | Conteúdo |
|---|---|
| `tabela_doentes.csv` | uma linha por doente: morada, endereço encontrado, precisão, latitude, longitude, km e minutos (fluxo livre e condições reais) de e para o hospital, incluído/excluído e motivo |
| `matriz_quadrada_distancias_km.csv` | matriz quadrada (hospital + doentes incluídos), em km |
| `matriz_quadrada_tempos_condicoes_reais_min.csv` | a mesma matriz em minutos, condições reais estimadas |
| `matriz_quadrada_tempos_fluxo_livre_min.csv` | a mesma matriz em minutos, fluxo livre (OSRM) |
| `lista_pares_origem_destino.csv` | as matrizes em formato de lista (origem, destino, km, min) |
| `matrizes_doentes.xlsx` | tudo num Excel, incluindo as matrizes de todos os doentes geocodificados, parâmetros e verificações |
| `verificacoes.csv` | controlo de qualidade da matriz |
| `mapa_doentes.html` | mapa com o hospital e os doentes (verde = incluído, laranja = excluído) |

**Como ler a matriz quadrada:** a **linha é a origem** e a **coluna é o destino**. As linhas e as
colunas têm a mesma ordem (HOSPITAL primeiro). A diagonal é 0. A→B e B→A são calculados
separadamente e podem ser diferentes (sentidos únicos, rotundas, acessos). A etapa confirma: matriz
quadrada, mesma ordem, sem pares em falta, diagonal nula, valores positivos, desigualdade triangular,
pontos de encaixe em Portugal.

Exemplo (tempos em condições reais, minutos):

```text
          HOSPITAL   D01   D02   D03   D04   D05
HOSPITAL       0.0   7.1   6.5   6.4   8.4  29.4
D01            6.9   0.0   4.8   4.9   7.3  28.1
D02            5.1   6.9   0.0   5.6   8.5  29.3
D03            6.9   5.0   4.8   0.0   8.2  28.9
D04            7.8   8.6   8.5   9.5   0.0  29.6
D05           28.8  27.4  27.3  28.2  27.5   0.0
```

**Regras de segurança da geocodificação:**

* Se a morada completa não for encontrada, tenta-se o código postal + localidade (precisão
  "código postal", com aviso).
* Se só se encontrar a **localidade ou o concelho**, o doente é **excluído** da matriz: um ponto no
  centro da vila pode estar a vários quilómetros do domicílio real. Corrija a morada ou indique as
  coordenadas GPS.
* Moradas não encontradas ficam na tabela com o motivo.
* As pesquisas ficam guardadas em `doentes/cache_geocodificacao.csv` (não se repetem).

> 🔒 **Privacidade (RGPD).** Moradas de doentes são dados de saúde. Na geocodificação, as moradas são
> **enviadas** ao servidor Nominatim indicado em `config.py` (`GEOCODIFICACAO_URL`). Não coloque
> nomes, diagnósticos ou outros dados no ficheiro — só um código e a morada. Para doentes reais,
> confirme com o Encarregado de Proteção de Dados da ULS ou instale um Nominatim na instituição.
> A pasta `doentes/` e `resultados/doentes/` estão no `.gitignore`: **nunca** são enviadas para o
> GitHub, exceto o exemplo fictício.

### Tempos em "condições reais"

O OpenStreetMap e o OSRM calculam tempos em **fluxo livre** (sem trânsito). Os servidores públicos
gratuitos **não têm trânsito em tempo real**: foi testado que o Valhalla dá exatamente o mesmo tempo
às 03:00, às 08:30 e às 18:00. Por isso o projeto calcula também uma **estimativa de condições reais**:

```text
tempo em condições reais = tempo em fluxo livre × 1,15 + 3 min
```

* `× 1,15` (`CONDICOES_REAIS_FATOR_TRANSITO`): semáforos, cruzamentos, trânsito urbano;
* `+ 3 min` (`CONDICOES_REAIS_TEMPO_ACESSO_MIN`): estacionar e chegar à porta (não se soma na diagonal).

São **pressupostos**, não trânsito medido. Calibre-os com tempos reais da equipa (por exemplo,
registos GPS da viatura durante algumas semanas). Para trânsito real seria preciso um serviço comercial
(Google, HERE, TomTom), que não é OpenStreetMap e tem custos e condições próprias.

* Na **Parte B**, a regra dos 30 min usa o tempo em **condições reais**.
* Na **Parte A**, a classificação oficial usa o **fluxo livre** (como no enunciado). O resumo mostra
  também a população abrangida em condições reais estimadas: **54 604** residentes (contra
  59 756 em fluxo livre).

---

## 3. Estrutura das pastas

```
hospitalizacao_domiciliaria_evora/
├── README.md                         ← este guia
├── requirements.txt                  ← bibliotecas a instalar
├── config.py                         ← TODOS os parâmetros editáveis
├── utilitarios.py                    ← mensagens, downloads, metadados
├── executar_tudo.py                  ← corre as etapas 1 a 10 (10 = Parte B, exemplo)
├── matriz_doentes.py                 ← PARTE B: doentes por morada → matriz quadrada
├── doentes/
│   └── doentes_exemplo.csv           ← doentes FICTÍCIOS (os seus ficheiros ficam aqui, fora do Git)
├── etapa_01_descarregar_dados_ine.py
├── etapa_02_preparar_subseccoes.py
├── etapa_03_calcular_matrizes_osrm.py
├── etapa_04_verificar_consistencia.py
├── etapa_05_classificar_elegibilidade.py
├── etapa_06_isocrona.py
├── etapa_07_mapas_interativos.py
├── etapa_08_resumo_e_capacidade.py
├── etapa_09_lista_verificacao.py
├── testes/
│   └── test_funcoes.py               ← testes que não precisam de Internet
├── dados/
│   ├── entrada/                      ← ficheiros ORIGINAIS do INE (não editar)
│   │   ├── BGRI21_ALENTEJO/…gpkg     ← polígonos + variáveis (BGRI 2021)
│   │   ├── BGRI21_LISBOA/…gpkg
│   │   ├── FS2021SubSeccaoTot/…xlsx  ← Ficheiro Síntese por subsecção (Censos 2021)
│   │   ├── FS2021SeccaoTot/…xlsx     ← Ficheiro Síntese por secção (recurso)
│   │   └── C2021_FSINTESE_VARIAVEIS.csv ← dicionário de variáveis
│   └── processados/                  ← ficheiros intermédios entre etapas
│       ├── subseccoes_area_estudo.gpkg
│       ├── territorio_portugal_area_estudo.gpkg
│       └── resultados_routing.csv
├── resultados/
│   ├── tabelas/                      ← tabela individual (CSV + Excel)
│   ├── matrizes/                     ← matrizes de tempos e distâncias (ida e regresso)
│   ├── geojson/                      ← resultados geográficos
│   ├── mapas/                        ← mapas interativos HTML
│   ├── relatorios/                   ← resumo, verificações, sensibilidade
│   └── doentes/<ficheiro>/           ← resultados da Parte B (matriz quadrada, mapa)
└── registo/
    ├── execucao.log                  ← todas as mensagens de progresso
    └── metadados_execucao.json       ← datas, fontes, versões, parâmetros, SHA-256
```

**Formato dos CSV de resultados:** separador `;` e vírgula decimal (`12,5`), codificação UTF-8
com BOM — abrem diretamente no Excel em português. Em Python: `pd.read_csv(f, sep=";", decimal=",")`.

---

## 4. As etapas, uma a uma

Cada etapa é um ficheiro independente que pode ser executado sozinho (`python etapa_0X_….py`)
depois das anteriores. No início de cada ficheiro há uma explicação do objetivo e do método.

| Etapa | O que faz | Precisa de Internet |
|---|---|---|
| **1** | Lê a página do INE, extrai os links oficiais e descarrega a BGRI 2021 (GeoPackage) do Alentejo e da AML, o Ficheiro Síntese (subsecção e secção) e o dicionário de variáveis. Regista data de recolha e SHA-256. | Sim |
| **2** | Lê os polígonos das subsecções, confirma que o hospital está em Portugal, calcula centroides (em PT-TM06, metros), pré-seleciona subsecções a ≤ 65 km em linha reta, associa a população residente (`N_INDIVIDUOS`) pelo código da subsecção, faz controlos de qualidade e converte para latitude/longitude. | Não |
| **3** | Pede ao OSRM, em blocos de 99, os tempos e distâncias **hospital → domicílio** e **domicílio → hospital** (pedidos separados). Exporta as matrizes. Pode ser interrompida e retomada. | Sim |
| **4** | Verificações: rotas em falta, distância à estrada, pontos fora de Portugal, velocidades implausíveis, estrada ≥ linha reta, assimetria ida/regresso, **desigualdade triangular** numa matriz quadrada de amostra, diagonal nula, repetibilidade. | Sim (1 pedido) |
| **5** | Classifica cada subsecção: **elegível** se tempo hospital → domicílio ≤ 30 min, **não elegível** caso contrário. Exporta tabela individual (CSV/Excel) e GeoJSON. | Não |
| **6** | Obtém a isócrona de 30 min (Valhalla), recorta-a pelo território português e cria a área das subsecções elegíveis. Mede a concordância OSRM/Valhalla. | Sim |
| **7** | Cria os mapas interativos HTML. | Não (para criar); sim, para ver o fundo do mapa |
| **8** | Calcula o resumo, a sensibilidade ao limite de tempo, a população por município e o cenário de capacidade operacional. | Não |
| **9** | Lista de verificação automática (ficheiros, somas, regras, metadados). | Não |

### Porquê 65 km em linha reta (etapa 2)?

A distância por estrada é sempre ≥ à distância em linha reta. A velocidade máxima legal em Portugal
é 130 km/h; em 30 minutos não se percorrem mais de 65 km. Portanto, **nenhuma subsecção a mais de
65 km em linha reta pode estar a 30 minutos** — este filtro é físico, não administrativo: não exclui
subsecções por pertencerem a um concelho, distrito ou NUTS. A etapa 9 confirma que a subsecção
elegível mais distante fica muito aquém dos 65 km.

### Como se garante que tudo fica em Portugal

* Só se analisam polígonos da **BGRI 2021**, que cobre exclusivamente o território nacional.
* A etapa 2 confirma que as coordenadas do hospital caem numa subsecção portuguesa (Évora) e que
  o círculo de 65 km está coberto por subsecções, exceto a parte que é território espanhol.
* A etapa 4 verifica que todos os pontos de encaixe na estrada ficam em Portugal.
* A etapa 6 recorta a isócrona pelo território português e mede a área que ficava em Espanha. Se essa
  área for zero, **nenhum percurso de 30 minutos sai de Portugal**: qualquer ponto de um percurso com
  30 min ou menos também se alcança em 30 min ou menos, logo estaria dentro da isócrona.

### Plano de recurso: sem população ao nível da subsecção

A população vem do Ficheiro Síntese por subsecção e é comparada com o atributo do GeoPackage da
BGRI (as duas fontes oficiais devem coincidir). Se faltar a população de alguma subsecção, a etapa 2
junta as subsecções dessa **secção estatística** (o nível imediatamente superior) num só polígono com
a população oficial da secção, e marca `nivel_geografico = "secção estatística"`. Nunca se inventam
nem estimam valores, e a mudança fica registada nos metadados.

---

## 5. Configuração (config.py) e APIs

### 5.1 Parâmetros principais

| Parâmetro | Valor por omissão | Significado |
|---|---|---|
| `HOSPITAL_LATITUDE/LONGITUDE` | 38.5688861 / −7.9031778 | GPS oficial (GMS convertido) |
| `LIMITE_TEMPO_MINUTOS` | 30 | limite de elegibilidade |
| `RAIO_PRE_SELECAO_KM` | 65 | 30 min × 130 km/h |
| `REGIOES_BGRI_NUTS2` | ALENTEJO, LISBOA | regiões descarregadas |
| `VARIAVEL_POPULACAO` | `N_INDIVIDUOS` | população residente (Censos 2021) |
| `OSRM_PONTOS_POR_PEDIDO` | 99 | subsecções por pedido `/table` |
| `DISTANCIA_MAXIMA_ATE_ESTRADA_M` | 1000 | alerta "afastado da rede" |
| `TAMANHO_AMOSTRA_TRIANGULAR` | 40 | tamanho da matriz quadrada de teste |
| `CAPACIDADE_*` | ver ficheiro | pressupostos do cenário operacional |

### 5.2 Coordenadas em graus, minutos e segundos

`config.py` tem a função `gms_para_decimal(graus, minutos, segundos, hemisferio)`. Oeste (W) e
Sul (S) dão valores **negativos** — trocar o sinal da longitude colocaria o hospital fora de Portugal,
e a etapa 2 recusa-se a continuar com uma mensagem clara.

### 5.3 (Opcional) Servidor OSRM próprio

Para muitos cálculos ou para fixar a versão da rede, instale o OSRM com Docker e os dados de Portugal
da Geofabrik:

```bash
wget https://download.geofabrik.de/europe/portugal-latest.osm.pbf
```

```bash
docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend osrm-extract -p /opt/car.lua /data/portugal-latest.osm.pbf
```

```bash
docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend osrm-partition /data/portugal-latest.osrm
```

```bash
docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend osrm-customize /data/portugal-latest.osrm
```

```bash
docker run -t -p 5000:5000 -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend osrm-routed --algorithm mld --max-table-size 10000 /data/portugal-latest.osrm
```

Depois, em `config.py`: `OSRM_URL = "http://localhost:5000"` e `OSRM_PAUSA_ENTRE_PEDIDOS_S = 0`.
Usar apenas o ficheiro de Portugal garante também que a rede rodoviária é só a portuguesa.

---

## 6. Ficheiros de resultados

| Ficheiro | Conteúdo |
|---|---|
| `resultados/tabelas/tabela_individual_subseccoes.csv` / `.xlsx` | **Uma linha por subsecção:** identificador, designação, município, freguesia, latitude, longitude, população residente, distância e tempo (ida e regresso), elegibilidade, cumprimento dos 30 min, proximidade ao limite, estado do routing, observações. O Excel tem as folhas `todas`, `elegiveis` e `proximas_do_limite`. |
| `resultados/tabelas/subseccoes_georreferenciadas.csv` | Tabela da etapa 2 (antes do routing): id, designação, população, coordenadas. |
| `resultados/matrizes/matriz_tempos_minutos.csv` | Matriz completa hospital ↔ subsecções: colunas `HOSPITAL_para_domicilio_min`, `domicilio_para_HOSPITAL_min` e a diferença. |
| `resultados/matrizes/matriz_distancias_km.csv` | O mesmo, para distâncias (km). |
| `resultados/matrizes/matrizes_ida_regresso.xlsx` | As duas matrizes e os dados completos do routing. |
| `resultados/matrizes/matriz_amostra_*.csv` | Matrizes **quadradas** (todos-para-todos) da amostra usada na desigualdade triangular. |
| `resultados/geojson/subseccoes_centroides.geojson` | Pontos (centroides) com todos os atributos. |
| `resultados/geojson/subseccoes_poligonos.geojson` | Polígonos da BGRI 2021 com todos os atributos. |
| `resultados/geojson/isocrona_30min.geojson` | Isócrona de 30 min (Valhalla, recortada por Portugal). |
| `resultados/geojson/area_subseccoes_elegiveis.geojson` | União das subsecções elegíveis. |
| `resultados/geojson/hospital.geojson` | Localização do hospital. |
| `resultados/mapas/mapa_centroides.html` | Mapa interativo dos centroides (com pesquisa por identificador). |
| `resultados/mapas/mapa_poligonos_bgri.html` | Mapa interativo dos polígonos (elegibilidade e densidade). |
| `resultados/relatorios/resumo_resultados.md` / `.json` | Resumo final. |
| `resultados/relatorios/verificacoes_consistencia.csv` | Resultado das verificações da etapa 4. |
| `resultados/relatorios/problemas_por_subseccao.csv` | Subsecções com algum problema de routing. |
| `resultados/relatorios/sensibilidade_limite_tempo.csv` | População abrangida para limites de 20 a 45 min. |
| `resultados/relatorios/populacao_elegivel_por_municipio.csv` | População elegível por município. |
| `registo/metadados_execucao.json` | Datas, URL, SHA-256, servidores, parâmetros. |

Os ficheiros GeoJSON abrem no QGIS (gratuito), em geojson.io ou em qualquer SIG.

---

## 7. Exemplo de execução

Execução real de 10/11/2026 (excerto do ecrã; o registo completo fica em `registo/execucao.log`):

```text
ETAPA 1 — Descarregar dados oficiais do INE (BGRI 2021 / Censos 2021)
   A ler a página do INE: https://mapas.ine.pt/download/index2021.phtml
   A página respondeu com o código 404; a tentar a seguinte.
   A ler a página do INE: https://mapas.ine.pt/
   Encontrados 342 ficheiros na página.
   A descarregar (1/4): https://mapas.ine.pt/download/filesGPG/2021/nuts2/BGRI21_ALENTEJO.zip
   Concluído: BGRI21_ALENTEJO.zip (55.5 MB)
   ...
ETAPA 2 — Preparar subsecções estatísticas (polígonos, centroides, população)
   Total de polígonos lidos: 51 942
   OK: o hospital está em Portugal, na subsecção 07052300732 (município 0705).
   Cobertura do círculo de 65 km: 96.94 % (em falta a leste — Espanha: 405.1 km²; a oeste: 0.0 km²)
   OK: todo o território português dentro do círculo está coberto.
   Subsecções com centroide a ≤ 65 km em linha reta: 9748
   Controlo: 0 subsecções com população diferente entre o Ficheiro Síntese e o GeoPackage (esperado: 0).
   Controlo de totais municipais: 16 municípios completos verificados, 0 com diferenças (esperado: 0).
   População residente total na área pré-selecionada: 240 452
ETAPA 3 — Distâncias e tempos de viagem na rede rodoviária (OSRM)
   Subsecções a calcular: 9748 em 99 blocos de até 99.
   Progresso: bloco 10/99
   ...
   Estados do cálculo: {'ok': 9673, 'ok_afastado_da_rede': 75}
ETAPA 4 — Verificações de consistência
   [  OK   ] Subsecções sem tempo de viagem: 0
   [ AVISO ] Centroides afastados da estrada (> 1000 m): 75
   [  OK   ] Pontos de encaixe na estrada fora de Portugal: 0
   [  OK   ] Velocidades médias implausíveis (ida): 0
   [  OK   ] Distância por estrada menor que em linha reta: 0
   [ INFO  ] Subsecções com assimetria ida/regresso > 10 %: 601
   [ INFO  ] Subsecções cuja classificação mudaria se se usasse o regresso: 189
   [  OK   ] Diagonal da matriz (tempo de um ponto para si próprio): 0.0 s
   [  OK   ] Desigualdade triangular (tempos): 0 violações em 68921 trios
   [ INFO  ] Desigualdade triangular (distâncias): 1608 violações em 68921 trios
   [  OK   ] Repetibilidade: mesma rota pedida duas vezes: 0.01 min
ETAPA 5 — Classificação de elegibilidade (≤ 30 min)
   Subsecções analisadas: 9748 | elegíveis: 1804 | não elegíveis: 7944
   População nas subsecções elegíveis: 59 756
ETAPA 6 — Isócrona de 30 minutos
   Área da isócrona fora de Portugal (removida): 0.00 km²
   OK: nenhum percurso de 30 min a partir do hospital sai de Portugal.
   Isócrona Valhalla: 278 km²; população com centroide dentro dela: 49 889
ETAPA 8 — Resumo dos resultados e capacidade operacional
   Subsecções analisadas ............ 9 748
   Subsecções elegíveis ............. 1 804
   Subsecções não elegíveis ......... 7 944
   População total analisada ........ 240 452
   POPULAÇÃO ABRANGIDA (≤ 30 min) ... 59 756
   Percentagem de cobertura ......... 24.85 %
   Tempo médio por residente elegível: 9.49 min
   Capacidade (cenário ilustrativo, tempos médios): 6 doentes/dia
ETAPA 9 — Lista de verificação final
   Resultado: 36/36 verificações OK.
```

### Principais resultados desta execução

| Indicador | Valor |
|---|---:|
| Subsecções analisadas / elegíveis / não elegíveis | 9 748 / 1 804 / 7 944 |
| População total analisada (≤ 65 km em linha reta) | 240 452 |
| **População residente abrangida (≤ 30 min, OSRM)** | **59 756 (24,85 %)** |
| Tempo médio hospital → domicílio, por residente elegível | 9,5 min (7,5 km) |
| População em subsecções entre 27 e 33 min | 14 680 |
| Sensibilidade: com 27 min / 33 min | 56 797 / 71 477 |
| Comparação: centroides dentro da isócrona Valhalla | 49 889 |

Por município: Évora 53 240 (99,4 % do concelho), Arraiolos 3 922, Viana do Alentejo 1 205,
Portel 697, Estremoz 377, Redondo 207, Montemor-o-Novo 108. A sede de concelho de Montemor-o-Novo
fica a cerca de 32,5 min no OSRM, **logo acima do limite**: é um exemplo de como o resultado
depende do limite e do motor de routing.

**Diferenças entre motores.** Os centroides elegíveis segundo o OSRM que ficam fora da isócrona do
Valhalla estão perto da estrada (mediana: 33 m), mas a uma mediana de 3,5 km para lá do limite da
isócrona. A diferença deve-se, portanto, às velocidades, que no Valhalla são mais prudentes, e não à
forma da isócrona. A isócrona do Valhalla tem a forma de "corredores" ao longo das estradas porque
fora delas nada se alcança de automóvel.

Os números acima mudam ligeiramente se o OpenStreetMap ou os servidores forem atualizados; os valores
de cada execução ficam em `resultados/relatorios/resumo_resultados.md` e nos metadados.

---

## 8. Guia de interpretação dos resultados

* **População residente abrangida** = soma dos residentes (Censos 2021) das subsecções cujo
  centroide está a ≤ 30 min do hospital, de automóvel e sem trânsito. É a população *potencialmente*
  servível do ponto de vista geográfico.
* **Percentagem de cobertura** = população abrangida ÷ população total analisada. O denominador é
  a população das subsecções a ≤ 65 km em linha reta, por isso a percentagem **não** é "da região"
  nem "do distrito". Para outra base (por exemplo, o município de Évora), use
  `populacao_elegivel_por_municipio.csv`.
* **Subsecções próximas do limite (27–33 min):** a classificação destas é a mais incerta. Veja a
  tabela de sensibilidade: se a população muda muito entre 27 e 33 min, o resultado é sensível ao
  limite e à aproximação pelo centroide.
* **Ida vs. regresso:** a classificação usa a **ida** (hospital → domicílio), como pedido. A etapa 4
  indica quantas subsecções mudariam de classe se se usasse o regresso.
* **Subsecções com 0 residentes** (campos, zonas industriais, albufeiras) entram na contagem de
  subsecções mas não alteram a população.
* **Mapa de centroides:** cada círculo é uma subsecção; o tamanho é proporcional à população. Clique
  para ver os dados. A caixa de pesquisa aceita o código de 11 dígitos (por exemplo, `07052300732`).
* **Mapa de polígonos:** mostra a forma real das subsecções. A camada "densidade populacional"
  ajuda a ver onde vivem as pessoas dentro da área elegível.
* **Isócrona (Valhalla) vs. classificação (OSRM):** são motores diferentes; a fronteira da isócrona
  não coincide ponto a ponto com a classificação. A concordância está nos metadados da etapa 6. O
  resultado oficial do estudo é o do **OSRM**.

---

## 9. Elegibilidade geográfica vs. capacidade operacional

| | População geograficamente elegível | Capacidade operacional diária |
|---|---|---|
| Pergunta | Quem *vive* a ≤ 30 min do hospital? | Quantos doentes as equipas *conseguem visitar* por dia? |
| Depende de | Censos 2021 + rede rodoviária | Equipas, viaturas, duração das visitas, deslocações, turno |
| Natureza | Dado observado + cálculo | **Cenário ilustrativo** com pressupostos |
| Ordem de grandeza | Dezenas de milhares de pessoas | Uma mão-cheia de doentes por equipa |

O cenário da etapa 8 modela o circuito diário de uma equipa (1 médico + 1 enfermeiro, numa viatura
ligeira de 5 lugares incluindo o condutor):

```
hospital → doente 1 → doente 2 → … → doente n → hospital
ida + n × duração da visita + (n − 1) × deslocação entre visitas + regresso ≤ turno
```

Uma viatura de 5 lugares leva fisicamente até 2 equipas (4 pessoas), mas então ambas fariam o mesmo
circuito; por isso assume-se **1 viatura por equipa**. Altere `CAPACIDADE_*` em `config.py` para os
valores reais do serviço e execute `python etapa_08_resumo_e_capacidade.py`.

---

## 10. Dados observados, pressupostos e aproximações

| Tipo | Elemento |
|---|---|
| **Dados observados (oficiais)** | População residente por subsecção (Censos 2021, `N_INDIVIDUOS`); polígonos BGRI 2021; designações de município e freguesia (Ficheiro Síntese) |
| **Dados de entrada fornecidos** | Coordenadas GPS do hospital (não geocodificadas pelo programa) |
| **Dados calculados** | Centroides; tempos e distâncias OSRM; isócrona Valhalla; classificação |
| **Aproximações** | Residentes concentrados no centroide; encaixe do centroide na estrada mais próxima; velocidades típicas por tipo de via (sem trânsito) |
| **Pressupostos metodológicos** | Limite de 30 min aplicado à ida; raio físico de 65 km; tolerâncias das verificações |
| **Pressupostos operacionais (ilustrativos)** | Nº de equipas e viaturas, turno, duração das visitas, deslocação entre visitas |

Não se usou geocodificação de moradas: as únicas coordenadas são as do hospital (dadas) e as dos
centroides (calculadas a partir dos polígonos oficiais). Não se usaram estimativas populacionais de
outras plataformas.

---

## 11. Limitações

**População (Censos 2021).** Retrata a população residente no momento censitário (abril de 2021);
não inclui alterações posteriores, população sazonal ou flutuante. O INE pode aplicar regras de
confidencialidade a variáveis desagregadas, mas o total de indivíduos por subsecção é publicado.

**Centroides — a principal aproximação.** Cada subsecção é representada por um único ponto: o centro
geométrico do polígono. Isto **não** significa que todos os residentes vivam nesse ponto:

* em subsecções urbanas (pequenas), o erro é de poucas dezenas de metros e não afeta o resultado;
* em subsecções rurais grandes, as casas podem estar a vários quilómetros do centroide; o centroide
  pode cair num campo, longe de qualquer estrada, ou até **fora do polígono** (formas em "C" —
  ver coluna `centroide_dentro_poligono`);
* para subsecções **perto dos 30 minutos**, uma parte das habitações pode estar dentro do limite e
  outra fora, mas a subsecção inteira é classificada de uma só vez. Toda a população da subsecção é
  contada como elegível ou não elegível. Use a coluna `proximo_do_limite` e a tabela de
  sensibilidade para avaliar este efeito.

**Encaixe na rede.** O OSRM liga cada centroide à estrada mais próxima; o troço a pé ou em caminho
de terra entre o centroide e essa estrada não é contado (`distancia_ate_estrada_m`).

**Rede rodoviária (OpenStreetMap).** Mapeada por voluntários; pode ter estradas em falta, sentidos
errados ou velocidades mal classificadas, sobretudo em caminhos rurais. A versão da rede é a que está
no servidor público no dia do cálculo; repetir o estudo noutro dia pode dar pequenas diferenças.

**Tempos de viagem.** São tempos de fluxo livre: não incluem trânsito, obras, meteorologia, procura
de estacionamento nem o tempo a pé até à porta. Os tempos reais da equipa tendem a ser maiores.

**Isócrona.** Calculada por outro motor (Valhalla), com velocidades ligeiramente diferentes, e
generalizada (simplificada) para desenho. Serve para visualizar, não para classificar.

**Pré-seleção.** A percentagem de cobertura depende do denominador (população a ≤ 65 km em linha reta).

---

## 12. Erros comuns e como resolver

| Mensagem | Causa provável | Solução |
|---|---|---|
| `ERRO de ligação: 403 Forbidden` (INE) | o servidor do INE recusa pedidos sem identificação | já resolvido com `CABECALHOS_HTTP` em `config.py`; se persistir, tente mais tarde |
| `Não foi possível descarregar … após 4 tentativas` | sem Internet ou o INE mudou o endereço | verifique a ligação; abra https://mapas.ine.pt/ e confirme os nomes dos ficheiros |
| `Ficheiro em falta: … Execute primeiro: python etapa_0X…` | etapa anterior não executada | execute a etapa indicada |
| `As coordenadas do hospital não caem em nenhuma subsecção` | coordenadas erradas, trocadas ou longitude positiva | corrija em `config.py` (Oeste = negativo) |
| `AVISO: há território a oeste do hospital sem subsecções` | faltam regiões NUTS II | acrescente a região em `REGIOES_BGRI_NUTS2` |
| `ERRO na API OSRM … demasiados pedidos (429)` | limite do servidor público | o programa espera e tenta de novo; aumente `OSRM_PAUSA_ENTRE_PEDIDOS_S` |
| `Falha definitiva no OSRM` | servidor em baixo | volte a correr a etapa 3: retoma onde parou |
| Estado `sem_rota` | centroide sem ligação à rede (ilha, albufeira) | ver `problemas_por_subseccao.csv`; a subsecção fica não elegível |
| Estado `ok_afastado_da_rede` | centroide > 1 km da estrada | resultado válido mas menos preciso |
| `isócrona do Valhalla indisponível` | servidor Valhalla em baixo | o mapa mostra só a área das subsecções elegíveis; repita a etapa 6 mais tarde |
| `ModuleNotFoundError: geopandas` | bibliotecas não instaladas | `pip install -r requirements.txt` (com o ambiente virtual ativo) |

Todas as mensagens ficam também em `registo/execucao.log`.

---

## 13. Lista de verificação

A etapa 9 verifica automaticamente a maior parte destes pontos (`python etapa_09_lista_verificacao.py`):

- [ ] Todos os ficheiros de resultados existem (tabelas, matrizes, GeoJSON, mapas, relatórios).
- [ ] O hospital cai numa subsecção do município de Évora (etapa 2).
- [ ] O território português dentro do círculo de 65 km está coberto; a única parte em falta é Espanha (etapa 2).
- [ ] 0 diferenças entre a população do Ficheiro Síntese e a do GeoPackage (etapa 2).
- [ ] Os totais municipais coincidem com os publicados pelo INE (etapa 2).
- [ ] Os identificadores são únicos e têm 11 dígitos.
- [ ] Nenhuma população em falta ou negativa.
- [ ] Todos os pontos de encaixe na estrada estão em Portugal (etapa 4).
- [ ] Velocidades médias plausíveis e distância por estrada ≥ linha reta (etapa 4).
- [ ] 0 violações da desigualdade triangular nos tempos (etapa 4).
- [ ] Classificação coerente com a regra (≤ 30 min ⇒ elegível).
- [ ] População abrangida = soma das subsecções elegíveis; elegíveis + não elegíveis = total.
- [ ] A subsecção elegível mais distante está bem dentro dos 65 km (o raio não cortou nada).
- [ ] A isócrona não tem área em Espanha (etapa 6).
- [ ] Os mapas abrem no navegador, os círculos verdes rodeiam Évora e ao clicar aparecem os dados.
- [ ] Verificação manual: escolha 2 ou 3 subsecções e compare o tempo com o Google Maps/OSM sem
      trânsito. Diferenças de alguns minutos são normais.
- [ ] `registo/metadados_execucao.json` tem a data de recolha, as versões e os parâmetros.

---

## 14. Reprodutibilidade

O ficheiro `registo/metadados_execucao.json` regista, para cada execução:

* **Fontes INE:** página e URL de cada ficheiro, data de recolha, tamanho, **SHA-256** e data interna
  dos ficheiros no ZIP (versão publicada pelo INE);
* **Routing:** servidor OSRM, perfil, datas de início e fim do cálculo, encaixe do hospital na rede;
* **Isócrona:** servidor e versão do Valhalla e data dos dados OSM carregados;
* **Parâmetros:** limite de tempo, raio, tolerâncias, amostra e semente aleatória, pressupostos de
  capacidade;
* **Controlos de qualidade** e indicadores finais.

Para reproduzir exatamente o mesmo resultado no futuro, guarde a pasta `dados/entrada/` (os ficheiros
do INE) e use um servidor OSRM próprio com um ficheiro `.osm.pbf` datado (secção 5.3).

---

## 15. Como modificar o estudo

* **Outro limite de tempo (ex.: 45 min):** em `config.py`, `LIMITE_TEMPO_MINUTOS = 45` (o raio de
  pré-seleção ajusta-se sozinho para 97,5 km). Depois execute `python executar_tudo.py --desde 2`.
  Pode ter de acrescentar regiões (o aviso da etapa 2 diz-lhe quais).
* **Outro hospital:** altere as coordenadas e o nome em `config.py` e as regiões em `REGIOES_BGRI_NUTS2`.
* **Classificar pelo regresso ou pelo pior dos sentidos:** em `etapa_05_classificar_elegibilidade.py`,
  na função `construir_tabela_individual`, troque `tabela["tempo_ida_min"]` por
  `tabela["tempo_regresso_min"]` ou por `tabela[["tempo_ida_min", "tempo_regresso_min"]].max(axis=1)`.
* **Capacidade operacional:** altere os parâmetros `CAPACIDADE_*` e execute só a etapa 8.
* **Outra variável populacional (ex.: residentes com 65 ou mais anos):** a variável
  `N_INDIVIDUOS_65_OU_MAIS` existe nos mesmos ficheiros; altere `VARIAVEL_POPULACAO` e repita as
  etapas 2, 5 e 8 (apague antes `dados/processados/FS2021SubSeccaoTot.csv`).
