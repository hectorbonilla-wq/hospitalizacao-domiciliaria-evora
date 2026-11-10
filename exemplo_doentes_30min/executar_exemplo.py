"""
EXEMPLO — Matriz de tempos e distâncias de um conjunto de doentes
==================================================================

Situação: a equipa de Hospitalização Domiciliária selecionou 9 doentes
(FICTÍCIOS, em moradas de locais públicos) que vivem a 30 minutos ou menos
do hospital e quer saber:
  * a distância (km) e o tempo (min) de cada doente ao hospital e do
    hospital a cada doente;
  * a matriz quadrada de km e minutos entre todos (hospital + doentes).

Como executar (a partir da pasta principal do projeto):
    python exemplo_doentes_30min/executar_exemplo.py

Os resultados ficam em exemplo_doentes_30min/resultados/.
Para usar os seus doentes, copie doentes.csv, troque as moradas e execute:
    python matriz_doentes.py o_seu_ficheiro.csv
"""

import sys
from pathlib import Path

PASTA_EXEMPLO = Path(__file__).resolve().parent
sys.path.insert(0, str(PASTA_EXEMPLO.parent))   # para encontrar os módulos do projeto

from matriz_doentes import executar_matriz_doentes  # noqa: E402

if __name__ == "__main__":
    executar_matriz_doentes(PASTA_EXEMPLO / "doentes.csv",
                            pasta_resultados=PASTA_EXEMPLO / "resultados")
