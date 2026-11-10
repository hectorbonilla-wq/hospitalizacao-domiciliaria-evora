# Exemplo — Matriz de km e minutos de doentes a ≤ 30 min do hospital

**Situação:** a equipa de Hospitalização Domiciliária do Hospital do Espírito Santo de Évora tem
9 doentes, identificados **pela morada**, que vivem a 30 minutos ou menos do hospital. Quer saber
os km e os minutos de cada doente ao hospital (ida e regresso) e a **matriz quadrada** entre todos.

> Os doentes são **fictícios**: as moradas são de locais públicos (praças, largos, ruas do centro
> de Évora, São Miguel de Machede e Arraiolos). Não correspondem a pessoas reais.

## 1. Ficheiro de entrada — `doentes.csv`

```text
id_doente;morada;codigo_postal;localidade
E01;Praça do Sertório;7000-651;Évora
E02;Largo dos Colegiais 2;7000-803;Évora
E03;Rua 5 de Outubro;7000-854;Évora
E04;Rua de Machede;7005-207;Évora
E05;Rua Serpa Pinto;;Évora
E06;Praça Joaquim António de Aguiar;7000-510;Évora
E07;Avenida Túlio Espanca;7005-840;Évora
E08;Largo da Igreja;7005-760;São Miguel de Machede
E09;Praça do Município;7040-027;Arraiolos
```

## 2. Executar (a partir da pasta principal do projeto)

```bash
python exemplo_doentes_30min/executar_exemplo.py
```

O programa:

1. converte cada morada em latitude/longitude (Nominatim/OpenStreetMap, só Portugal);
2. pede ao OSRM (rede OpenStreetMap) a matriz completa hospital + doentes, nos dois sentidos;
3. calcula os minutos em **condições reais estimadas** (sem trânsito × 1,15 + 3 min para estacionar);
4. confirma que cada doente está a ≤ 30 min do hospital;
5. verifica e exporta a matriz quadrada.

## 3. Resultados — pasta `resultados/`

### Doentes: km e minutos de/para o hospital

| Doente | Morada | km H→D | min H→D (reais) | min D→H (reais) | ≤ 30 min |
|---|---|---:|---:|---:|:---:|
| E01 | Praça do Sertório, Évora | 1,8 | 7,1 | 6,9 | sim |
| E02 | Largo dos Colegiais 2, Évora | 1,5 | 6,5 | 5,1 | sim |
| E03 | Rua 5 de Outubro, Évora | 1,0 | 6,5 | 6,9 | sim |
| E04 | Rua de Machede, Évora | 0,7 | 5,2 | 5,0 | sim |
| E05 | Rua Serpa Pinto, Évora | 2,9 | 8,8 | 7,5 | sim |
| E06 | Praça Joaquim António de Aguiar, Évora | 2,5 | 7,4 | 7,8 | sim |
| E07 | Avenida Túlio Espanca, Évora | 2,6 | 8,4 | 7,8 | sim |
| E08 | Largo da Igreja, São Miguel de Machede | 18,4 | 24,8 | 25,1 | sim |
| E09 | Praça do Município, Arraiolos | 23,9 | 29,4 | 28,8 | sim |

### Matriz quadrada — minutos em condições reais (linha = origem, coluna = destino)

```text
          HOSPITAL   E01   E02   E03   E04   E05   E06   E07   E08   E09
HOSPITAL       0.0   7.1   6.5   6.4   5.2   8.8   7.4   8.4  24.8  29.4
E01            6.9   0.0   4.8   4.9   5.7   7.0   6.1   7.3  25.3  28.1
E02            5.1   6.9   0.0   5.6   4.4   8.6   7.2   8.5  24.6  29.3
E03            6.9   5.0   4.8   0.0   5.7   8.3   6.9   8.2  25.3  28.9
E04            5.0   5.6   4.9   6.5   0.0   7.2   5.9   7.1  23.2  27.9
E05            7.5   6.1   6.0   7.0   5.9   0.0   5.0   5.5  25.5  27.1
E06            7.8   5.0   5.7   5.8   6.6   4.7   0.0   6.0  26.3  28.9
E07            7.8   8.6   8.5   9.5   8.4   6.5   7.5   0.0  28.1  29.6
E08           25.1  25.3  24.6  26.2  23.5  27.0  25.6  26.8   0.0  40.9
E09           28.8  27.4  27.3  28.2  27.2  27.7  26.3  27.5  40.3   0.0
```

**Como ler:** para saber quanto demora ir de E02 para E04, procure a linha **E02** e a coluna
**E04**: 4,4 min. O regresso (linha E04, coluna E02) demora 4,9 min. Os dois sentidos são
calculados separadamente e não têm de ser iguais. A matriz em km está em
`matriz_quadrada_distancias_km.csv`.

### Verificações (todas OK)

Matriz 10 × 10 · mesma ordem nas linhas e colunas · sem pares em falta · diagonal = 0 ·
0 violações da desigualdade triangular em 1000 trios · todos os pontos a < 1 km da estrada e em
Portugal · todos os doentes a ≤ 30 min.

### Ficheiros

| Ficheiro | Conteúdo |
|---|---|
| `tabela_doentes.csv` | morada, endereço encontrado, precisão, coordenadas, km e min (ida e regresso) |
| `matriz_quadrada_distancias_km.csv` | matriz quadrada em km |
| `matriz_quadrada_tempos_condicoes_reais_min.csv` | matriz quadrada em minutos (condições reais estimadas) |
| `matriz_quadrada_tempos_fluxo_livre_min.csv` | matriz quadrada em minutos (sem trânsito) |
| `lista_pares_origem_destino.csv` | as 90 ligações em lista (origem, destino, km, min) |
| `matrizes_doentes.xlsx` | tudo num ficheiro Excel |
| `mapa_doentes.html` | mapa sobre OpenStreetMap: hospital (H), doentes, percursos reais e tabela |

**Mapa:** os 7 doentes de Évora aparecem agrupados num círculo com o número 7. Clique no círculo
(ou aproxime) para os ver separados, cada um com a etiqueta "E01 · 7 min". Clique num doente para
ver a morada, a precisão da localização, os km e os minutos.

## 4. Usar com os seus doentes

1. Copie `doentes.csv` para `doentes/os_meus_doentes.csv` (esta pasta não vai para o GitHub).
2. Substitua as moradas — **só um código e a morada**, sem nomes nem dados clínicos.
3. Execute:

```bash
python matriz_doentes.py doentes/os_meus_doentes.csv
```

Os resultados ficam em `resultados/doentes/os_meus_doentes/`. Leia a secção de privacidade do
README principal antes de usar moradas reais: na geocodificação, as moradas são enviadas ao
serviço Nominatim.
