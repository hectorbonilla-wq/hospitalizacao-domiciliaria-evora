# Exemplo — Matriz de km e minutos de doentes a ≤ 30 min do hospital

**Situação:** a equipa de Hospitalização Domiciliária do Hospital do Espírito Santo de Évora
selecionou 9 doentes, identificados **pela morada**, que julga viverem a 30 minutos ou menos do
hospital. Quer saber
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

1. procura cada morada em **dois serviços** (OpenRouteService e Nominatim/OpenStreetMap, só Portugal);
2. **revê** cada resultado: concelho e freguesia (BGRI 2021), código postal e precisão, e fica com o
   que bate certo com a morada;
3. pede ao **OpenRouteService** (rede OpenStreetMap) a matriz completa hospital + doentes, nos dois sentidos;
4. calcula os minutos em **condições reais estimadas** (sem trânsito × 1,15 + 3 min para estacionar);
5. fica só com os doentes a **≤ 30 min** do hospital e constrói a **matriz quadrada** desses doentes.

## 3. Resultados — pasta `resultados/` (execução de 10/11/2026)

### Revisão das moradas

| Doente | Morada | Localizado em (BGRI 2021) | Serviço escolhido | Verificação |
|---|---|---|---|---|
| E01 | Praça do Sertório, Évora | U.F. de Évora (Évora) | Nominatim | OK (o ORS só encontrou "Évora") |
| E02 | Largo dos Colegiais 2, Évora | U.F. de Évora (Évora) | Nominatim | OK, número de porta; os dois serviços a 48 m |
| E03 | Rua 5 de Outubro, Évora | U.F. de Évora (Évora) | Nominatim | OK (o ORS pôs a rua em **Arcos, Estremoz** — rejeitado) |
| E04 | Rua de Machede, Évora | U.F. de Évora (Évora) | OpenRouteService | OK (o Nominatim devolveu outro código postal — rejeitado) |
| E05 | Rua Serpa Pinto, Évora | U.F. de Évora (Évora) | Nominatim | OK (o ORS pôs a rua em **Reguengos de Monsaraz** — rejeitado) |
| E06 | Praça Joaquim António de Aguiar, Évora | U.F. de Évora (Évora) | OpenRouteService | OK, os dois serviços a 76 m |
| E07 | Avenida Túlio Espanca, Évora | U.F. Malagueira e Horta das Figueiras (Évora) | OpenRouteService | **VERIFICAR**: os serviços diferem 1,4 km (avenida comprida — indique o número de porta) |
| E08 | Largo da Igreja, São Miguel de Machede | São Miguel de Machede (Évora) | OpenRouteService | OK |
| E09 | Praça do Município, Arraiolos | Arraiolos (Arraiolos) | OpenRouteService | OK |

Este quadro mostra porque é preciso rever as moradas: em 3 das 9, um dos serviços encontrou uma rua
com o mesmo nome noutra terra. Sem a verificação pela BGRI, o doente teria sido colocado a dezenas
de quilómetros do domicílio real.

### Doentes: km e minutos de/para o hospital (OpenRouteService)

| Doente | km H→D | min H→D sem trânsito | min H→D condições reais | min D→H condições reais | ≤ 30 min |
|---|---:|---:|---:|---:|:---:|
| E01 | 1,4 | 5,7 | 9,5 | 8,7 | sim |
| E02 | 1,5 | 5,1 | 8,9 | 6,1 | sim |
| E03 | 1,0 | 4,0 | 7,6 | 8,4 | sim |
| E04 | 0,5 | 2,1 | 5,4 | 6,1 | sim |
| E05 | 2,7 | 8,8 | 13,1 | 10,5 | sim |
| E06 | 2,6 | 7,4 | 11,5 | 9,6 | sim |
| E07 | 4,5 | 11,3 | 16,0 | 12,2 | sim |
| E08 | 18,3 | 22,5 | 28,9 | 29,3 | sim |
| E09 | 23,9 | 25,5 | **32,4** | 32,3 | **não** |

O E09 (Arraiolos) fica a 25,5 min sem trânsito, mas a **32,4 min em condições reais estimadas**, por
isso **sai da matriz**. O programa não confia na seleção prévia: confirma sempre o limite dos 30 min.

### Matriz quadrada — minutos em condições reais (linha = origem, coluna = destino)

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

### Matriz quadrada — km (linha = origem, coluna = destino)

```text
          HOSPITAL   E01   E02   E03   E04   E05   E06   E07   E08
HOSPITAL       0.0   1.4   1.5   1.0   0.5   2.7   2.6   4.5  18.3
E01            1.2   0.0   0.6   0.5   1.3   1.1   0.8   3.3  18.7
E02            0.7   1.2   0.0   0.8   0.5   2.8   2.4   5.3  18.1
E03            1.2   0.5   0.5   0.0   1.2   1.5   1.2   4.9  18.6
E04            0.7   1.5   1.3   0.8   0.0   2.8   2.4   5.2  18.1
E05            2.0   1.3   1.8   1.5   2.2   0.0   1.0   2.3  19.6
E06            1.4   0.5   0.8   0.7   1.5   0.5   0.0   2.7  18.9
E07            3.3   3.7   4.2   3.9   4.6   2.4   3.4   0.0  22.0
E08           18.6  18.7  18.4  18.9  17.9  19.9  19.5  22.4   0.0
```

**Como ler:** para saber quanto demora ir de E02 para E04, procure a linha **E02** e a coluna **E04**:
5,4 min. O regresso (linha E04, coluna E02) demora 7,7 min. Os dois sentidos são calculados
separadamente (ruas de sentido único, acessos) e não têm de ser iguais.

### Verificações da matriz (todas OK)

Matriz 9 × 9 · mesma ordem nas linhas e colunas · sem pares em falta · diagonal = 0 · valores > 0 ·
0 violações da desigualdade triangular em 729 trios · todos os pontos a < 1 km da estrada e em
Portugal.

### Ficheiros

| Ficheiro | Conteúdo |
|---|---|
| `tabela_doentes.csv` | morada, endereço encontrado, serviço, concelho/freguesia BGRI, verificação, coordenadas, km e min (ida e regresso) |
| `matriz_quadrada_distancias_km.csv` | matriz quadrada em km |
| `matriz_quadrada_tempos_condicoes_reais_min.csv` | matriz quadrada em minutos (condições reais estimadas) |
| `matriz_quadrada_tempos_fluxo_livre_min.csv` | matriz quadrada em minutos (sem trânsito) |
| `lista_pares_origem_destino.csv` | as 72 ligações em lista (origem, destino, km, min) |
| `matrizes_doentes.xlsx` | tudo num ficheiro Excel |
| `mapa_doentes.html` | mapa sobre OpenStreetMap: hospital (H), doentes, percursos reais e tabela |

**Mapa:** os doentes de Évora aparecem agrupados num círculo com o número de doentes. Clique no
círculo (ou aproxime) para os ver separados, cada um com a etiqueta "E01 · 10 min". Clique num doente
para ver a morada, o serviço usado, a verificação, os km e os minutos.

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
