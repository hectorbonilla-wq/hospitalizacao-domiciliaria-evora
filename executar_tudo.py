"""
executar_tudo.py — Executa todas as etapas, por ordem
======================================================

Utilização:
    python executar_tudo.py                 # corre as etapas 1 a 10
    python executar_tudo.py --do-zero       # apaga dados e resultados e corre tudo de novo
    python executar_tudo.py --desde 5       # recomeça na etapa 5
    python executar_tudo.py --ate 2         # corre apenas as etapas 1 e 2

Cada etapa também pode ser executada sozinha, por exemplo:
    python etapa_03_calcular_matrizes_osrm.py
"""

import argparse
import shutil
import sys
import time

from etapa_01_descarregar_dados_ine import executar_etapa_1
from etapa_02_preparar_subseccoes import executar_etapa_2
from etapa_03_calcular_matrizes_osrm import executar_etapa_3
from etapa_04_verificar_consistencia import executar_etapa_4
from etapa_05_classificar_elegibilidade import executar_etapa_5
from etapa_06_isocrona import executar_etapa_6
from etapa_07_mapas_interativos import executar_etapa_7
from etapa_08_resumo_e_capacidade import executar_etapa_8
from etapa_09_lista_verificacao import executar_lista_verificacao
from matriz_doentes import FICHEIRO_EXEMPLO, criar_exemplo, executar_matriz_doentes
import config
from utilitarios import mensagem


def matriz_doentes_exemplo():
    """Etapa 10 (Parte B): matriz de tempos/distâncias para os doentes de exemplo."""
    if not FICHEIRO_EXEMPLO.exists():
        criar_exemplo()
    executar_matriz_doentes(FICHEIRO_EXEMPLO)


def apagar_tudo():
    """
    Apaga os dados descarregados, os ficheiros intermédios, os resultados e o
    registo, para repetir o estudo do zero. O código e o ficheiro de doentes
    de exemplo NÃO são apagados.
    """
    pastas = [config.PASTA_ENTRADA, config.PASTA_PROCESSADOS, config.PASTA_TABELAS,
              config.PASTA_MATRIZES, config.PASTA_GEOJSON, config.PASTA_MAPAS,
              config.PASTA_RELATORIOS, config.PASTA_REGISTO,
              config.PASTA_PROJETO / "resultados" / "doentes"]
    for pasta in pastas:
        if pasta.exists():
            for item in pasta.iterdir():
                if item.name == ".gitkeep":
                    continue
                shutil.rmtree(item) if item.is_dir() else item.unlink()
    print("Dados e resultados anteriores apagados. A recomeçar do zero.")

ETAPAS = {
    1: ("Descarregar dados do INE", executar_etapa_1),
    2: ("Preparar subsecções", executar_etapa_2),
    3: ("Routing OSRM (ida e regresso)", executar_etapa_3),
    4: ("Verificações de consistência", executar_etapa_4),
    5: ("Classificação de elegibilidade", executar_etapa_5),
    6: ("Isócrona de 30 minutos", executar_etapa_6),
    7: ("Mapas interativos", executar_etapa_7),
    8: ("Resumo e capacidade operacional", executar_etapa_8),
    9: ("Lista de verificação", executar_lista_verificacao),
    10: ("Parte B — matriz dos doentes (exemplo)", matriz_doentes_exemplo),
}


def main():
    """
    Lê as opções da linha de comandos e executa as etapas pedidas.

    Devolve:
        int: 0 se tudo correu bem, 1 se alguma etapa falhou.
    """
    leitor = argparse.ArgumentParser(description="Estudo de cobertura da Hospitalização Domiciliária")
    leitor.add_argument("--desde", type=int, default=1, help="primeira etapa a executar (1–10)")
    leitor.add_argument("--ate", type=int, default=10, help="última etapa a executar (1–10)")
    leitor.add_argument("--do-zero", action="store_true",
                        help="apaga dados e resultados anteriores antes de começar")
    opcoes = leitor.parse_args()
    if opcoes.do_zero:
        apagar_tudo()
        opcoes.desde = 1

    inicio = time.time()
    for numero in range(opcoes.desde, opcoes.ate + 1):
        nome, funcao = ETAPAS[numero]
        try:
            funcao()
        except Exception as erro:  # mostra o erro de forma clara e pára
            mensagem(f"ERRO na etapa {numero} ({nome}): {type(erro).__name__}: {erro}")
            mensagem(f"Corrija o problema e recomece com: python executar_tudo.py --desde {numero}")
            return 1
    mensagem(f"Concluído em {(time.time() - inicio) / 60:.1f} minutos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
