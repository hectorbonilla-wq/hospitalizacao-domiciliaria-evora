"""
ETAPA 5 — Classificar cada subsecção como ELEGÍVEL ou NÃO ELEGÍVEL
===================================================================

OBJETIVO
--------
Aplicar a regra do serviço a cada subsecção, individualmente:

    ELEGÍVEL      se  tempo hospital → domicílio  ≤ 30 minutos
    NÃO ELEGÍVEL  se  tempo hospital → domicílio  > 30 minutos
                  (ou se não foi possível calcular um percurso — nesse caso
                   a coluna "motivo_classificacao" explica porquê)

Assinala também as subsecções PRÓXIMAS DO LIMITE (entre 27 e 33 minutos),
cuja classificação é mais sensível à aproximação pelo centroide.

RESULTADOS
----------
    resultados/tabelas/tabela_individual_subseccoes.csv / .xlsx
    resultados/geojson/subseccoes_centroides.geojson   (pontos)
    resultados/geojson/subseccoes_poligonos.geojson    (polígonos BGRI 2021)

EXECUTAR SÓ ESTA ETAPA (depois das etapas 2 e 3)
------------------------------------------------
    python etapa_05_classificar_elegibilidade.py
"""

import geopandas as gpd
import pandas as pd

import config
from utilitarios import mensagem, registar_metadados, verificar_ficheiro_existe

MARGEM_PROXIMO_LIMITE_MIN = 3  # ± minutos em torno do limite


def classificar_tempo(tempo_minutos, limite=config.LIMITE_TEMPO_MINUTOS):
    """
    Classifica um tempo de viagem segundo a regra dos 30 minutos.

    Parâmetros:
        tempo_minutos (float ou None): tempo hospital → domicílio.
        limite (float): limite máximo em minutos (por omissão, 30).

    Devolve:
        tuple (str, str): (classificação, motivo).

    Exemplos:
        classificar_tempo(29.9)  -> ("elegível", "tempo ≤ 30 min")
        classificar_tempo(30.0)  -> ("elegível", "tempo ≤ 30 min")
        classificar_tempo(30.1)  -> ("não elegível", "tempo > 30 min")
        classificar_tempo(None)  -> ("não elegível", "sem tempo de viagem calculado")
    """
    if tempo_minutos is None or pd.isna(tempo_minutos):
        return "não elegível", "sem tempo de viagem calculado"
    if tempo_minutos <= limite:
        return "elegível", f"tempo ≤ {limite} min"
    return "não elegível", f"tempo > {limite} min"


def construir_tabela_individual():
    """
    Junta a tabela das subsecções (etapa 2) com o routing (etapa 3) e aplica
    a classificação a cada linha.

    Devolve:
        GeoDataFrame: polígonos com todos os atributos e a classificação.
    """
    subseccoes = gpd.read_file(config.FICHEIRO_SUBSECCOES)
    routing = pd.read_csv(config.FICHEIRO_ROUTING, dtype={"id_subseccao": str})
    tabela = subseccoes.merge(routing, on="id_subseccao", how="left")

    classificacoes = [classificar_tempo(t) for t in tabela["tempo_ida_min"]]
    tabela["elegibilidade"] = [c[0] for c in classificacoes]
    tabela["motivo_classificacao"] = [c[1] for c in classificacoes]
    tabela["cumpre_limite_30min"] = tabela["elegibilidade"] == "elegível"
    tabela["proximo_do_limite"] = (
        (tabela["tempo_ida_min"] - config.LIMITE_TEMPO_MINUTOS).abs() <= MARGEM_PROXIMO_LIMITE_MIN)
    tabela["populacao_residente"] = tabela["populacao_residente"].astype(int)
    return tabela


def exportar_resultados(tabela):
    """
    Exporta a tabela individual (CSV e Excel) e os ficheiros GeoJSON.

    Parâmetros:
        tabela (GeoDataFrame): resultado de construir_tabela_individual().

    Devolve:
        Nada.
    """
    colunas = ["id_subseccao", "designacao", "municipio", "freguesia", "nivel_geografico",
               "latitude", "longitude", "populacao_residente",
               "distancia_ida_km", "tempo_ida_min",
               "distancia_regresso_km", "tempo_regresso_min",
               "elegibilidade", "cumpre_limite_30min", "motivo_classificacao",
               "proximo_do_limite", "estado_routing", "distancia_ate_estrada_m",
               "centroide_dentro_poligono", "distancia_linha_reta_km", "observacao",
               "fonte_populacao", "data_calculo"]
    nomes_legiveis = {
        "distancia_ida_km": "distancia_hospital_domicilio_km",
        "tempo_ida_min": "tempo_hospital_domicilio_min",
        "distancia_regresso_km": "distancia_domicilio_hospital_km",
        "tempo_regresso_min": "tempo_domicilio_hospital_min",
    }
    individual = pd.DataFrame(tabela[colunas]).rename(columns=nomes_legiveis)
    individual = individual.sort_values(["tempo_hospital_domicilio_min", "id_subseccao"])

    individual.to_csv(config.PASTA_TABELAS / "tabela_individual_subseccoes.csv",
                      index=False, encoding="utf-8-sig", sep=";", decimal=",")
    with pd.ExcelWriter(config.PASTA_TABELAS / "tabela_individual_subseccoes.xlsx") as excel:
        individual.to_excel(excel, sheet_name="todas", index=False)
        individual[individual["elegibilidade"] == "elegível"].to_excel(
            excel, sheet_name="elegiveis", index=False)
        individual[individual["proximo_do_limite"]].to_excel(
            excel, sheet_name="proximas_do_limite", index=False)
    mensagem("   Tabela individual: resultados/tabelas/tabela_individual_subseccoes.csv/.xlsx")

    # GeoJSON — os ficheiros GeoJSON usam sempre latitude/longitude (WGS84)
    config.PASTA_GEOJSON.mkdir(parents=True, exist_ok=True)
    poligonos = gpd.GeoDataFrame(individual.merge(tabela[["id_subseccao", "geometry"]],
                                                  on="id_subseccao"),
                                 geometry="geometry", crs=config.CRS_PORTUGAL).to_crs(config.CRS_WGS84)
    poligonos.to_file(config.PASTA_GEOJSON / "subseccoes_poligonos.geojson", driver="GeoJSON")
    pontos = gpd.GeoDataFrame(individual, crs=config.CRS_WGS84,
                              geometry=gpd.points_from_xy(individual["longitude"], individual["latitude"]))
    pontos.to_file(config.PASTA_GEOJSON / "subseccoes_centroides.geojson", driver="GeoJSON")
    hospital = gpd.GeoDataFrame({"nome": [config.HOSPITAL_NOME], "morada": [config.HOSPITAL_MORADA]},
                                geometry=gpd.points_from_xy([config.HOSPITAL_LONGITUDE],
                                                            [config.HOSPITAL_LATITUDE]),
                                crs=config.CRS_WGS84)
    hospital.to_file(config.PASTA_GEOJSON / "hospital.geojson", driver="GeoJSON")
    mensagem("   GeoJSON: resultados/geojson/ (centroides, polígonos, hospital)")


def executar_etapa_5():
    """
    Executa a etapa 5: classificação e exportação.

    Devolve:
        GeoDataFrame: tabela classificada (usada pelas etapas 6–8).
    """
    mensagem("=" * 70)
    mensagem(f"ETAPA 5 — Classificação de elegibilidade (≤ {config.LIMITE_TEMPO_MINUTOS} min)")
    mensagem("=" * 70)
    tabela = construir_tabela_individual()
    elegiveis = tabela[tabela["cumpre_limite_30min"]]
    mensagem(f"   Subsecções analisadas: {len(tabela)} | elegíveis: {len(elegiveis)} | "
             f"não elegíveis: {len(tabela) - len(elegiveis)}")
    mensagem(f"   População nas subsecções elegíveis: "
             f"{int(elegiveis['populacao_residente'].sum()):,}".replace(",", " "))
    exportar_resultados(tabela)
    registar_metadados("etapa_05_classificacao", {
        "regra": f"elegível se tempo hospital → domicílio ≤ {config.LIMITE_TEMPO_MINUTOS} min",
        "sentido_usado": "hospital → domicílio (ida)",
        "margem_proximo_do_limite_min": MARGEM_PROXIMO_LIMITE_MIN,
    })
    mensagem("ETAPA 5 concluída.")
    return tabela


if __name__ == "__main__":
    verificar_ficheiro_existe(config.FICHEIRO_ROUTING, "etapa_03_calcular_matrizes_osrm.py")
    executar_etapa_5()
