# População potencialmente abrangida pela Hospitalização Domiciliária — HESE Évora

Projeto em Python que estima **quantas pessoas residem a 30 minutos de automóvel, ou menos,**
do serviço de **Hospitalização Domiciliária da ULS do Alentejo Central – Hospital do Espírito
Santo de Évora** (Largo do Senhor da Pobreza, 7000-811 Évora).

* **Coordenadas do hospital (GPS):** 38º34'07.99" N | 7º54'11.44" W → **38.5688861, −7.9031778**
* **Fonte populacional (obrigatória):** INE — Censos 2021 (resultados definitivos) e BGRI 2021,
  ao nível da **subsecção estatística**
* **Rede rodoviária:** OpenStreetMap, com routing **OpenRouteService** (tempos, distâncias e
  isócrona; precisa de chave gratuita) — ou o **OSRM** público, sem chave, como alternativa
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
| OpenRouteService | tempos, distâncias, isócrona e geocodificação (com chave) | `ORS_URL = https://api.openrouteservice.org` |
| OSRM | alternativa sem chave para tempos e distâncias | `OSRM_URL = https://router.project-osrm.org` |
| Valhalla | isócrona de 30 min (só para o mapa) | `VALHALLA_URL = https://valhalla1.openstreetmap.de` |

Os servidores públicos têm limites de utilização (≈ 1 pedido por segundo). O programa respeita-os
com pausas entre pedidos. Para uso intensivo, ver a secção 5.3 (servidor OSRM próprio).

### Chave do OpenRouteService (recomendado)

O projeto usa por omissão o **OpenRouteService** (`MOTOR_ROUTING = "ors"` em `config.py`): a mesma
rede OpenStreetMap, mas com matrizes grandes (até ~3500 percursos por pedido), isócronas e
geocodificação de moradas.

1. Crie uma conta gratuita em https://openrouteservice.org/dev/#/signup e copie a chave ("API key").
2. Guarde a chave **num destes dois sítios** (nunca em `config.py`, que vai para o GitHub):
   * ficheiro `chave_openrouteservice.txt` na pasta do projeto, só com a chave lá dentro
     (este ficheiro está no `.gitignore` e nunca é enviado para o GitHub); **ou**
   * variável de ambiente `ORS_API_KEY`.

```bash
echo "A_SUA_CHAVE" > chave_openrouteservice.txt
```

Sem chave, o programa avisa e usa automaticamente o OSRM público. O plano gratuito do
OpenRouteService tem quotas diárias (cerca de 50 pedidos de matriz por dia nesta conta, além dos de
geocodificação e isócronas). O estudo completo usa cerca de 10 pedidos de matriz. A etapa 3 guarda os
resultados e não repete pedidos já feitos.

> 🔐 Trate a chave como uma palavra-passe: não a cole em mensagens, e-mails ou ficheiros partilhados.
> Se ela tiver sido exposta, gere uma nova no painel do OpenRouteService e apague a antiga.

---

## 2. Execução rápida

```bash
python executar_tudo.py
```

Demora cerca de **3–5 minutos** com o OpenRouteService (8–12 com o OSRM público) e corre também a Parte B
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

1. **converte cada morada em coordenadas** (geocodificação com OpenRouteService e Nominatim, só em
   Portugal) e **confirma-as** com o concelho/freguesia da BGRI 2021 e o código postal;
2. calcula a **distância (km) e o tempo (min) de/para o hospital** de cada doente, nos dois sentidos;
3. **seleciona os doentes a ≤ 30 min** do hospital (tempo hospital → doente em condições reais estimadas);
4. constrói a **matriz quadrada** hospital + doentes selecionados (todos para todos), em km e em minutos;
5. verifica a matriz e exporta CSV, Excel e um mapa.

> 📁 **Exemplo completo e separado:** a pasta [`exemplo_doentes_30min/`](exemplo_doentes_30min/README.md)
> tem 9 doentes fictícios, todos a ≤ 30 min, com o ficheiro de entrada, o programa
> (`python exemplo_doentes_30min/executar_exemplo.py`), os resultados e a explicação passo a passo.

Os tempos e as distâncias dos doentes são calculados com o **OpenRouteService** (matriz
`/v2/matrix/driving-car`, rede OpenStreetMap), ou com o OSRM se não houver chave. Cada ficheiro
pode ter até 58 doentes com o OpenRouteService (99 com o OSRM).

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
| `matriz_quadrada_tempos_fluxo_livre_min.csv` | a mesma matriz em minutos, fluxo livre (OpenRouteService) |
| `lista_pares_origem_destino.csv` | as matrizes em formato de lista (origem, destino, km, min) |
| `matrizes_doentes.xlsx` | tudo num Excel, incluindo as matrizes de todos os doentes geocodificados, parâmetros e verificações |
| `verificacoes.csv` | controlo de qualidade da matriz |
| `mapa_doentes.html` | mapa com o hospital e os doentes (verde = incluído, laranja = excluído) |

**Como ler a matriz quadrada:** a **linha é a origem** e a **coluna é o destino**. As linhas e as
colunas têm a mesma ordem (HOSPITAL primeiro). A diagonal é 0. A→B e B→A são calculados
separadamente e podem ser diferentes (sentidos únicos, rotundas, acessos). A etapa confirma: matriz
quadrada, mesma ordem, sem pares em falta, diagonal nula, valores positivos, desigualdade triangular,
pontos de encaixe em Portugal.

Exemplo (pasta `exemplo_doentes_30min/`, tempos em condições reais, minutos):

```text
          HOSPITAL   E01   E02   E03   E04   E05   E06   E07   E08
HOSPITAL       0.0   9.5   8.9   7.6   5.4  13.1  11.5  16.0  28.9
E01            8.7   0.0   5.7   5.5   7.4   8.0   6.5  13.0  28.9
E02            6.1   8.7   0.0   6.8   5.4  12.4  10.5  15.1  28.0
E03            8.4   5.4   5.4   0.0   7.2  10.0   8.5  14.3  28.7
E04            6.1   8.7   7.7   6.9   0.0  12.1  10.3  14.9  27.7
E05           10.5   8.3   8.1   9.4   9.0   0.0   7.0   8.5  30.5
E06            9.6   5.3   6.5   6.4   8.3   5.2   0.0  10.2  29.8
E07           12.2  12.5  12.3  13.6  13.2   9.6  11.2   0.0  34.7
E08           29.3  28.8  27.8  29.9  27.1  32.3  30.4  35.0   0.0
```

**O mapa dos doentes** (`mapa_doentes.html`, fundo OpenStreetMap):

* `H` = hospital; verde = doente incluído (≤ 30 min); laranja = excluído (> 30 min);
* cada doente tem a etiqueta "id · minutos desde o hospital"; linhas verdes = percurso real na rede;
* doentes muito próximos aparecem **agrupados** num círculo com o número de doentes; clique para os ver;
* a caixa no canto inferior esquerdo tem a tabela de km e minutos e lista os doentes que não puderam
  ser localizados (estes não são desenhados, para não mostrar uma posição errada).

**Revisão das moradas (confirmação de que as coordenadas são as certas):**

Com chave do OpenRouteService, cada morada é procurada em **dois serviços independentes**
(geocodificador do OpenRouteService e Nominatim/OpenStreetMap). Para cada resultado o programa verifica:

1. **Concelho e freguesia (BGRI 2021):** o ponto é colocado na subsecção estatística que o contém e a
   *localidade* do ficheiro tem de corresponder ao concelho ou à freguesia dessa subsecção. Há ruas
   com o mesmo nome em muitas terras. No exemplo, o OpenRouteService colocou a "Rua 5 de Outubro,
   Évora" em Arcos (Estremoz) e a "Rua Serpa Pinto, Évora" em Reguengos de Monsaraz; a verificação
   rejeitou esses resultados e ficou com os do Nominatim, que estão em Évora.
2. **Código postal:** os 4 primeiros dígitos (CP4) indicados têm de coincidir com os do código postal
   devolvido, quando o serviço o devolve.
3. **Precisão:** pelo menos rua ou código postal (nunca só a localidade).
4. **Concordância entre serviços:** se os dois encontrarem a rua mas a mais de 250 m um do outro, pede-se
   confirmação. Se um só encontrou o centro da localidade e o outro está a mais de 3 km desse centro,
   também se pede confirmação (pode ser uma rua com o mesmo nome noutra terra do mesmo concelho).

Fica o resultado que passa mais verificações. As colunas `verificacao_morada`, `morada_confirmada`,
`concelho_bgri`, `freguesia_bgri`, `subseccao_bgri`, `fonte_coordenadas` e
`diferenca_entre_servicos_m` da `tabela_doentes.csv` mostram o que foi verificado. **Se aparecer
"VERIFICAR", confirme a morada** (ou escreva as coordenadas GPS do domicílio nas colunas
`latitude;longitude`) antes de usar o resultado.

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

### Instâncias de 10 a 100 doentes

A pasta [`instancias_doentes/`](instancias_doentes/README.md) tem **10 instâncias encaixadas** (10, 20,
…, 100 doentes), todas a ≤ 30 min do hospital, com matriz quadrada de km e minutos. Os doentes são
**fictícios**, mas as localizações são **ruas reais** do OpenStreetMap. Os doentes são sorteados nas
subsecções da BGRI 2021 proporcionalmente à **população com 65 ou mais anos** (Censos 2021).
Geram-se com:

```bash
python instancias_doentes/gerar_instancias.py
```

### Tempos em "condições reais"

O OpenRouteService e o OSRM calculam tempos em **fluxo livre** (sem trânsito), com velocidades típicas por tipo de via do OpenStreetMap. Os servidores públicos
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
  também a população abrangida em condições reais estimadas: **49 875** residentes (contra
  57 435 em fluxo livre, OpenRouteService).

---

## 3. Estrutura das pastas

```
hospitalizacao_domiciliaria_evora/
├── README.md                         ← este guia
├── requirements.txt                  ← bibliotecas a instalar
├── config.py                         ← TODOS os parâmetros editáveis
├── utilitarios.py                    ← mensagens, downloads, metadados
├── routing.py                        ← pedidos de matrizes (OpenRouteService ou OSRM)
├── chave_openrouteservice.txt        ← a SUA chave (criada por si; fora do Git)
├── executar_tudo.py                  ← corre as etapas 1 a 10 (10 = Parte B, exemplo)
├── matriz_doentes.py                 ← PARTE B: doentes por morada → matriz quadrada
├── exemplo_doentes_30min/            ← EXEMPLO separado: 9 doentes a ≤ 30 min (entrada, programa, resultados)
├── instancias_doentes/               ← INSTÂNCIAS de 10, 20, …, 100 doentes fictícios em ruas reais, com matrizes
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
| **3** | Pede ao OpenRouteService (blocos de 3000) ou ao OSRM (blocos de 99) os tempos e distâncias **hospital → domicílio** e **domicílio → hospital** (pedidos separados). Pontos sem ligação direta à rede são ligados à estrada mais próxima e recalculados. Exporta as matrizes. Pode ser interrompida e retomada. | Sim |
| **4** | Verificações: rotas em falta, distância à estrada, pontos fora de Portugal, velocidades implausíveis, estrada ≥ linha reta, assimetria ida/regresso, **desigualdade triangular** numa matriz quadrada de amostra, diagonal nula, repetibilidade. | Sim (1 pedido) |
| **5** | Classifica cada subsecção: **elegível** se tempo hospital → domicílio ≤ 30 min, **não elegível** caso contrário. Exporta tabela individual (CSV/Excel) e GeoJSON. | Não |
| **6** | Obtém a isócrona de 30 min (OpenRouteService; Valhalla se não houver chave), recorta-a pelo território português e cria a área das subsecções elegíveis. Mede a concordância com a classificação. | Sim |
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

Execução real de 10/11/2026 com o **OpenRouteService** (excerto; o registo completo fica em
`registo/execucao.log`):

```text
ETAPA 2 — Preparar subsecções estatísticas (polígonos, centroides, população)
   OK: o hospital está em Portugal, na subsecção 07052300732 (município 0705).
   Cobertura do círculo de 65 km: 96.94 % (em falta a leste — Espanha: 405.1 km²; a oeste: 0.0 km²)
   Subsecções com centroide a ≤ 65 km em linha reta: 9748
   Controlo: 0 subsecções com população diferente entre o Ficheiro Síntese e o GeoPackage (esperado: 0).
   Controlo de totais municipais: 16 municípios completos verificados, 0 com diferenças (esperado: 0).
ETAPA 3 — Distâncias e tempos de viagem na rede rodoviária (OpenStreetMap)
   Motor de routing: OpenRouteService (driving-car) — https://api.openrouteservice.org
   Subsecções a calcular: 9748 em 4 blocos de até 3000 (2 pedidos por bloco: ida e regresso).
   2 subsecções sem ligação direta à rede: a ligar à estrada mais próxima...
   Resolvidas na segunda tentativa: 1 de 2
   Estados do cálculo: {'ok': 9665, 'ok_afastado_da_rede': 81, 'sem_rota': 1, 'ok_reencaixado': 1}
ETAPA 4 — Verificações de consistência
   [  OK   ] Pontos de encaixe na estrada fora de Portugal: 0
   [  OK   ] Distância por estrada menor que em linha reta: 0
   [  OK   ] Desigualdade triangular (tempos): 0 violações em 68921 trios
ETAPA 5 — Classificação de elegibilidade (≤ 30 min)
   Subsecções analisadas: 9748 | elegíveis: 1698 | não elegíveis: 8050
   População nas subsecções elegíveis: 57 435
ETAPA 6 — Isócrona de 30 minutos
   OK: nenhum percurso de 30 min a partir do hospital sai de Portugal.
   Isócrona OpenRouteService: 1154 km²; população com centroide dentro dela: 58 106
   Concordância: 99.8 % dos centroides elegíveis (ORS) estão dentro da isócrona OpenRouteService
ETAPA 8 — Resumo dos resultados e capacidade operacional
   POPULAÇÃO ABRANGIDA (≤ 30 min) ... 57 435
   Percentagem de cobertura ......... 23.89 %
   Em condições reais estimadas ..... 49 875
   Tempo médio por residente elegível: 11.39 min
ETAPA 9 — Lista de verificação final
   Resultado: 36/36 verificações OK.
```

### Principais resultados — população a ≤ 30 min do hospital

A partir das coordenadas do hospital (38.5688861, −7.9031778), calculou-se o tempo de automóvel até
ao centroide de **cada uma das 9 748 subsecções estatísticas** da BGRI 2021 num raio físico de 65 km.
A população abrangida é a soma dos residentes (Censos 2021) das subsecções a ≤ 30 min.

| Indicador | Valor |
|---|---:|
| Subsecções analisadas / elegíveis / não elegíveis | 9 748 / 1 698 / 8 050 |
| População total analisada (≤ 65 km em linha reta) | 240 452 |
| **População residente a ≤ 30 min (OpenRouteService, sem trânsito)** | **57 435 (23,89 %)** |
| População a ≤ 30 min em condições reais estimadas (× 1,15 + 3 min) | 49 875 |
| Tempo médio hospital → domicílio, por residente elegível | 11,4 min (6,6 km) |
| População em subsecções entre 27 e 33 min | 6 338 |
| Sensibilidade: com 27 min / 33 min | 56 055 / 62 321 |
| Isócrona de 30 min do OpenRouteService (centroides dentro) | 58 106 (concordância 99,8 %) |
| Comparação: mesmo cálculo com o OSRM | 59 756 |

Por município (OpenRouteService): Évora 52 717 (98,4 % do concelho), Arraiolos 3 779, Viana do
Alentejo 855, Montemor-o-Novo 84.

**Porque é que o OpenRouteService dá menos 2 321 residentes do que o OSRM?** Os dois usam a mesma rede
OpenStreetMap mas velocidades diferentes por tipo de via; o ORS é um pouco mais conservador (tempo
médio por residente elegível 11,4 min contra 9,5 min). A diferença concentra-se nas subsecções entre
25 e 33 min (Arraiolos, Viana do Alentejo, Portel, Redondo, Estremoz). A sede de concelho de Arraiolos,
por exemplo, fica a ~25,5 min no ORS e ~23 min no OSRM. Os dois valores são estimativas válidas;
o oficial deste estudo é o do motor configurado (`MOTOR_ROUTING`). Os resultados do OSRM ficam
guardados em `dados/processados/resultados_routing_osrm.csv` para comparação.

Os números mudam ligeiramente se o OpenStreetMap ou os servidores forem atualizados; os valores de
cada execução ficam em `resultados/relatorios/resumo_resultados.md` e nos metadados.

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
* **Cores dos mapas:** verde = elegível; cinzento claro = não elegível (discreto, para não tapar o
  OpenStreetMap); azul = isócrona de 30 min. Os mapas abrem já enquadrados na área de cobertura.
* **Mapa de centroides:** cada círculo é uma subsecção; o tamanho é proporcional à população. Clique
  para ver os dados. A caixa de pesquisa aceita o código de 11 dígitos (por exemplo, `07052300732`).
* **Mapa de polígonos:** mostra a forma real das subsecções. A camada "densidade populacional"
  ajuda a ver onde vivem as pessoas dentro da área elegível.
* **Isócrona vs. classificação:** com o OpenRouteService, a isócrona e a matriz vêm do mesmo motor e
  concordam a 99,8 %. Sem chave usa-se o OSRM (matriz) e o Valhalla (isócrona), que são motores diferentes; a fronteira da isócrona
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
| **Dados calculados** | Centroides; tempos e distâncias (OpenRouteService ou OSRM); isócrona; coordenadas das moradas dos doentes (geocodificação); classificação |
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

**Encaixe na rede.** O motor de routing liga cada centroide à estrada mais próxima; o troço a pé ou em caminho
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
| `Chave do OpenRouteService inválida ou sem permissão` | chave errada, expirada ou com espaços | confirme `chave_openrouteservice.txt` (só a chave, numa linha) |
| `ERRO no OpenRouteService … quota/limite de pedidos atingido (429)` | quota diária do plano gratuito esgotada | espere pelo dia seguinte (a etapa 3 retoma onde parou) ou mude `MOTOR_ROUTING = "osrm"` |
| `AVISO: sem chave do OpenRouteService` | não há chave | crie a chave (secção 1) ou aceite o OSRM público |
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
* **Routing:** motor (OpenRouteService ou OSRM), servidor, perfil, datas de início e fim do cálculo, encaixe do hospital na rede;
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
