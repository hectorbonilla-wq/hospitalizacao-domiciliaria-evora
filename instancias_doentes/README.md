# Instâncias de doentes a ≤ 30 min do Hospital do Espírito Santo de Évora

Conjuntos ("instâncias") de **10, 20, 30, …, 100 doentes** para testar o planeamento da
Hospitalização Domiciliária (rotas, capacidade das equipas, algoritmos de otimização), cada um com
a **matriz quadrada de km e minutos** entre o hospital e todos os doentes.

## Que dados são reais e o que é fictício

| Elemento | Origem | Real? |
|---|---|---|
| Doentes (identificador P001…P100) | gerados pelo programa | **fictícios** — não existem dados de doentes reais neste projeto |
| Onde vivem (subsecção estatística) | sorteio proporcional à **população com 65 ou mais anos** de cada subsecção (INE, Censos 2021 / BGRI 2021) | distribuição **real** |
| Localização (latitude, longitude) | ponto aleatório dentro do polígono da subsecção, ligado à **rua pública mais próxima** (rede OpenStreetMap) | ponto **real** numa rua |
| Morada (rua, código postal, localidade) | geocodificação inversa da rua (Nominatim/OpenStreetMap) | morada **real**, sem número de porta |
| Tempos e distâncias | OpenRouteService (rede OpenStreetMap), ida e regresso separados | **calculados** |
| Tempos "em condições reais" | sem trânsito × 1.15 + 3 min (estacionar e chegar à porta) | **estimativa** (pressuposto) |

Os doentes são colocados **na rua e não numa casa concreta**, e a morada **não tem número de
porta**, para não associar uma doença fictícia à casa de uma pessoa real.

## Como foram geradas

```bash
python instancias_doentes/gerar_instancias.py
```

1. Foram consideradas as **1 136 subsecções** a ≤ 30 min do hospital (também em condições reais
   estimadas, no centroide) com residentes de 65+ anos (**11 414 residentes com 65+ anos**).
2. Sortearam-se 130 candidatos (semente 2021, reprodutível), cada um num ponto de uma rua real.
3. Confirmou-se com o OpenRouteService que cada candidato está a **≤ 30 min do hospital em
   condições reais**; 1 candidato estava a mais e foi substituído. Ficaram os primeiros 100.
4. Calculou-se **uma só matriz completa 101 × 101** (hospital + 100 doentes) em 3 pedidos ao
   OpenRouteService, guardada em `matriz_completa/`.
5. Cada instância de N doentes são os **primeiros N** (P001…PN). As instâncias são **encaixadas**:
   a de 10 está contida na de 20, a de 20 na de 30, etc. A matriz de cada instância é a
   sub-matriz da matriz completa (o percurso mais rápido entre dois pontos não depende dos outros).

Executar de novo reutiliza os doentes e a matriz já calculados (não gasta quota). Para sortear tudo
de novo: `python instancias_doentes/gerar_instancias.py --novo`. Os tamanhos, a semente e a variável
de peso (65+ ou população total) estão em `config.py` (`INSTANCIAS_*`).

## Resumo das instâncias (execução de 10/11/2026)

| Instância | Doentes | Matriz | km médio H→D | min médio H→D (reais) | min máximo H→D (reais) | min médio entre doentes (reais) | Verificações |
|---|---:|---:|---:|---:|---:|---:|---|
| instancia_010 | 10 | 11 × 11 | 2.42 | 11.6 | 15.7 | 10.3 | todas OK |
| instancia_020 | 20 | 21 × 21 | 2.45 | 11.4 | 15.7 | 10.2 | todas OK |
| instancia_030 | 30 | 31 × 31 | 3.15 | 12.3 | 26.8 | 12.2 | todas OK |
| instancia_040 | 40 | 41 × 41 | 3.53 | 12.7 | 28.9 | 12.6 | todas OK |
| instancia_050 | 50 | 51 × 51 | 3.45 | 12.5 | 28.9 | 12.6 | todas OK |
| instancia_060 | 60 | 61 × 61 | 3.38 | 12.4 | 28.9 | 12.7 | todas OK |
| instancia_070 | 70 | 71 × 71 | 3.31 | 12.4 | 28.9 | 12.6 | todas OK |
| instancia_080 | 80 | 81 × 81 | 3.23 | 12.3 | 28.9 | 12.3 | todas OK |
| instancia_090 | 90 | 91 × 91 | 3.19 | 12.2 | 28.9 | 12.2 | todas OK |
| instancia_100 | 100 | 101 × 101 | 3.22 | 12.2 | 28.9 | 12.3 | todas OK |

Todos os doentes de todas as instâncias estão a **≤ 30 min** do hospital (máximo 28,9 min em
condições reais). As moradas foram confirmadas com a BGRI 2021 (concelho/freguesia) em 100 %.

**Distribuição geográfica:** 99 dos 100 doentes ficam no concelho de Évora (sobretudo nas freguesias
urbanas de Malagueira e Horta das Figueiras, Bacelo e Senhora da Saúde e no centro histórico) e 1 em
Arraiolos. Isto reflete os dados reais: a maior parte dos residentes com 65+ anos a ≤ 30 min (em
condições reais) vive na cidade de Évora. Há 15 doentes em ruas repetidas (pontos diferentes da mesma
rua), o que é normal em ruas residenciais compridas.

**Desigualdade triangular:** na matriz em **condições reais** (a usada para planear) há **0 violações**
em todas as instâncias. Na matriz **sem trânsito** há algumas violações pequenas a partir da instância
de 40 (no máximo 2 min, entre doentes vizinhos do centro de Évora). É normal: num ponto de paragem o
motor permite inverter a marcha, o que não é permitido a meio de uma rua com sentidos proibidos.
Passar por um doente vizinho pode, assim, ser mais rápido do que ir direto. O tempo de paragem
(3 min) da matriz em condições reais anula este efeito.

## Ficheiros

```
instancias_doentes/
├── gerar_instancias.py            ← programa
├── instancia_010.csv … instancia_100.csv   ← ENTRADA de cada instância (para matriz_doentes.py)
├── doentes_todos.csv              ← os 100 doentes com a subsecção sorteada, população 65+ e tempos
├── matriz_completa/               ← matriz 101 × 101 (min sem trânsito, km, encaixe na rede)
├── resumo_instancias.csv          ← quadro acima
└── resultados/instancia_NNN/      ← para cada instância:
    ├── tabela_doentes.csv                           (km e minutos de/para o hospital, verificação da morada)
    ├── matriz_quadrada_distancias_km.csv            (N+1) × (N+1)
    ├── matriz_quadrada_tempos_condicoes_reais_min.csv
    ├── matriz_quadrada_tempos_fluxo_livre_min.csv
    ├── lista_pares_origem_destino.csv
    ├── matrizes_doentes.xlsx                        (tudo num Excel)
    ├── verificacoes.csv
    └── mapa_doentes.html                            (com percursos desenhados nas instâncias de 10 e 20)
```

Formato da entrada (as coordenadas já vêm preenchidas, por isso não há nova geocodificação):

```text
id_doente;morada;codigo_postal;localidade;concelho;latitude;longitude
P001;Travessa das Anjinhas;7000-548;Évora;Évora;38.573791;-7.91386
P002;Rua de Arraiolos;7000-862;Évora;Évora;38.577679;-7.919015
P003;Rua Luís Inácio Nunes;7000-306;Évora;Évora;38.568995;-7.926342
P004;Rua do Cano;7000-596;Évora;Évora;38.573636;-7.910485
P005;Rua Nossa Senhora de Fátima à Torregela;7005-567;Évora;Évora;38.562954;-7.924798
```

Para correr uma instância sozinha com o programa da Parte B:

```bash
python matriz_doentes.py instancias_doentes/instancia_030.csv
```

(gasta pedidos ao OpenRouteService: 1 pedido até 58 doentes, 2–3 pedidos para 60–100 doentes).

## Limites e cuidados

* **Máximo de 100 doentes** nestas instâncias (configurável em `INSTANCIAS_TAMANHOS`). O programa
  aceita até 200 doentes por ficheiro; matrizes grandes são pedidas em blocos e gastam mais quota
  diária do OpenRouteService.
* Os doentes são fictícios: as instâncias servem para **testar métodos**, não para descrever doentes
  reais nem a procura real do serviço.
* A probabilidade proporcional à população com 65+ anos é um **pressuposto** (os doentes de
  hospitalização domiciliária são maioritariamente idosos); pode ser trocada pela população total.
* Os tempos não incluem trânsito em tempo real; a parcela "condições reais" é uma estimativa.
