"""
ETAPA 9 — Lista de verificação automática dos resultados
=========================================================

OBJETIVO
--------
Confirmar, no fim, que o algoritmo funcionou corretamente. Cada verificação
mostra [OK] ou [FALHA] e uma explicação. Se aparecer alguma FALHA, leia a
mensagem e volte à etapa indicada.

EXECUTAR (depois de todas as outras etapas)
-------------------------------------------
    python etapa_09_lista_verificacao.py
"""

import json

import geopandas as gpd
import pandas as pd

import config
from utilitarios import ler_metadados, mensagem

FICHEIROS_OBRIGATORIOS = [
    "resultados/tabelas/subseccoes_georreferenciadas.csv",
    "resultados/tabelas/tabela_individual_subseccoes.csv",
    "resultados/tabelas/tabela_individual_subseccoes.xlsx",
    "resultados/matrizes/matriz_tempos_minutos.csv",
    "resultados/matrizes/matriz_distancias_km.csv",
    "resultados/matrizes/matrizes_ida_regresso.xlsx",
    "resultados/matrizes/matriz_amostra_tempos_minutos.csv",
    "resultados/matrizes/matriz_amostra_distancias_km.csv",
    "resultados/geojson/subseccoes_centroides.geojson",
    "resultados/geojson/subseccoes_poligonos.geojson",
    "resultados/geojson/area_subseccoes_elegiveis.geojson",
    "resultados/geojson/hospital.geojson",
    "resultados/mapas/mapa_centroides.html",
    "resultados/mapas/mapa_poligonos_bgri.html",
    "resultados/relatorios/resumo_resultados.md",
    "resultados/relatorios/verificacoes_consistencia.csv",
    "registo/metadados_execucao.json",
]


def executar_lista_verificacao():
    """
    Corre todas as verificações finais e mostra o resultado de cada uma.

    Devolve:
        bool: True se todas as verificações passaram.
    """
    mensagem("=" * 70)
    mensagem("ETAPA 9 — Lista de verificação final")
    mensagem("=" * 70)
    resultados = []

    def verificar(descricao, condicao, detalhe=""):
        """Regista e mostra uma verificação (função interna)."""
        resultados.append(bool(condicao))
        mensagem(f"   [{'OK' if condicao else 'FALHA'}] {descricao} {detalhe}")

    # 1. Ficheiros obrigatórios
    for caminho in FICHEIROS_OBRIGATORIOS:
        ficheiro = config.PASTA_PROJETO / caminho
        verificar(f"Existe {caminho}", ficheiro.exists() and ficheiro.stat().st_size > 0)

    tabela = pd.read_csv(config.PASTA_TABELAS / "tabela_individual_subseccoes.csv",
                         sep=";", decimal=",", dtype={"id_subseccao": str})
    subseccoes = gpd.read_file(config.FICHEIRO_SUBSECCOES)
    with open(config.PASTA_RELATORIOS / "resumo_resultados.json", encoding="utf-8") as f:
        resumo = json.load(f)["indicadores"]

    # 2. Integridade da tabela
    verificar("Identificadores únicos", tabela["id_subseccao"].is_unique)
    verificar("Identificadores com 11 dígitos (subsecção)",
              tabela["id_subseccao"].str.fullmatch(r"\d{11}").all() or
              (tabela["nivel_geografico"] != "subsecção estatística").any())
    verificar("Todas as subsecções da etapa 2 foram classificadas", len(tabela) == len(subseccoes),
              f"({len(tabela)} vs {len(subseccoes)})")
    verificar("População sem valores em falta nem negativos",
              tabela["populacao_residente"].notna().all() and (tabela["populacao_residente"] >= 0).all())
    verificar("Coordenadas dentro de Portugal Continental",
              tabela["latitude"].between(36.8, 42.2).all() and tabela["longitude"].between(-9.6, -6.1).all())

    # 3. Regra de elegibilidade aplicada corretamente
    regra = (tabela["tempo_hospital_domicilio_min"] <= config.LIMITE_TEMPO_MINUTOS)
    verificar("Classificação coerente com a regra dos 30 min",
              ((tabela["elegibilidade"] == "elegível") == regra).all())

    # 4. Somas coerentes
    soma_elegivel = int(tabela.loc[tabela["elegibilidade"] == "elegível", "populacao_residente"].sum())
    verificar("População abrangida = soma das subsecções elegíveis",
              soma_elegivel == resumo["populacao_residente_abrangida"],
              f"({soma_elegivel})")
    verificar("Elegíveis + não elegíveis = total",
              resumo["subseccoes_elegiveis"] + resumo["subseccoes_nao_elegiveis"]
              == resumo["subseccoes_analisadas"])
    verificar("População da tabela = população da etapa 2",
              int(tabela["populacao_residente"].sum()) == int(subseccoes["populacao_residente"].sum()))

    # 5. Plausibilidade
    eleg = tabela[tabela["elegibilidade"] == "elegível"]
    reta_max = eleg["distancia_linha_reta_km"].max()
    verificar("Raio de pré-seleção suficiente (elegível mais distante bem dentro do raio)",
              reta_max < 0.9 * config.RAIO_PRE_SELECAO_KM,
              f"({reta_max:.1f} km de {config.RAIO_PRE_SELECAO_KM:.0f} km)")
    verificar("Subsecção do hospital é elegível com tempo ≈ 0",
              tabela.loc[tabela["id_subseccao"] == ler_metadados().get("etapa_02_preparacao", {})
                         .get("subseccao_do_hospital"), "tempo_hospital_domicilio_min"].le(5).all())
    verificar("Município de Évora maioritariamente elegível",
              eleg.loc[eleg["municipio"] == "Évora", "populacao_residente"].sum()
              > 0.8 * tabela.loc[tabela["municipio"] == "Évora", "populacao_residente"].sum())

    # 6. Consistência (etapa 4)
    consistencia = pd.read_csv(config.PASTA_RELATORIOS / "verificacoes_consistencia.csv", sep=";")
    erros = consistencia[consistencia["resultado"] == "ERRO"]
    verificar("Sem ERROS nas verificações de consistência", erros.empty,
              "" if erros.empty else f"({', '.join(erros['verificacao'])})")

    # 7. Metadados para reprodutibilidade
    metadados = ler_metadados()
    for seccao in ["etapa_01_fontes_ine", "etapa_02_preparacao", "etapa_03_routing",
                   "etapa_04_consistencia", "etapa_05_classificacao", "etapa_08_resumo"]:
        verificar(f"Metadados registados: {seccao}", seccao in metadados)

    passou = all(resultados)
    mensagem(f"   Resultado: {sum(resultados)}/{len(resultados)} verificações OK.")
    mensagem("ETAPA 9 concluída." if passou else "ETAPA 9: há verificações em FALHA — ver acima.")
    return passou


if __name__ == "__main__":
    executar_lista_verificacao()
