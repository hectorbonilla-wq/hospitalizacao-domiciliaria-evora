"""
gerar_instancias.py — Instâncias de 10, 20, ..., 100 doentes a ≤ 30 min do hospital
=====================================================================================

OBJETIVO
--------
Criar conjuntos de doentes ("instâncias") para testar o planeamento da
Hospitalização Domiciliária com dados REALISTAS e REPRODUTÍVEIS, sem usar
dados de doentes reais (que são confidenciais e não estão disponíveis):

  * os DOENTES são FICTÍCIOS;
  * as LOCALIZAÇÕES são REAIS: ruas públicas do OpenStreetMap, dentro de
    subsecções estatísticas da BGRI 2021 a ≤ 30 min do hospital;
  * a DISTRIBUIÇÃO é REAL: cada doente é sorteado numa subsecção com
    probabilidade proporcional à população com 65 ou mais anos dessa
    subsecção (Censos 2021) — mais idosos, mais probabilidade de doentes.

PASSOS
------
  1. Ler as subsecções elegíveis (Parte A) e a população 65+ da BGRI 2021.
  2. Sortear subsecções (proporcional à população 65+) e, em cada uma, um
     ponto aleatório dentro do polígono.
  3. Ligar o ponto à RUA mais próxima (rede OpenStreetMap). O doente fica nesse
     ponto da rua pública — não numa casa concreta (proteção de privacidade).
  4. Obter a morada dessa rua (nome da rua, código postal, localidade) por
     geocodificação inversa no Nominatim/OpenStreetMap. Sem número de porta.
  5. Confirmar com o motor de routing que cada doente está a ≤ 30 min do
     hospital em CONDIÇÕES REAIS estimadas; os que não estão são substituídos.
  6. Calcular UMA matriz completa hospital + 100 doentes (todos para todos).
  7. Para cada tamanho (10, 20, ..., 100) gravar a instância (primeiros N
     doentes) e correr a Parte B com a sub-matriz correspondente.
     As instâncias são ENCAIXADAS: a de 10 está contida na de 20, etc.

EXECUTAR (a partir da pasta principal do projeto, depois da Parte A)
--------------------------------------------------------------------
    python instancias_doentes/gerar_instancias.py

Demora ~6–8 minutos (pedidos ao OpenStreetMap com pausas de 1 s) e gasta
~5 pedidos de matriz do OpenRouteService.
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point

PASTA = Path(__file__).resolve().parent
sys.path.insert(0, str(PASTA.parent))

import config  # noqa: E402
from matriz_doentes import (aplicar_condicoes_reais, calcular_matriz,  # noqa: E402
                            executar_matriz_doentes)
from routing import descricao_motor, pedir_matriz, ponto_mais_proximo_na_estrada  # noqa: E402
from utilitarios import mensagem, registar_metadados  # noqa: E402


def ler_subseccoes_elegiveis():
    """
    Lê as subsecções a ≤ 30 min (Parte A) com o polígono e a população 65+.

    Devolve:
        GeoDataFrame: subsecções elegíveis com população de referência > 0
        (EPSG:3763, metros), com a coluna "peso".
    """
    poligonos = gpd.read_file(config.PASTA_GEOJSON / "subseccoes_poligonos.geojson")
    poligonos = poligonos[poligonos["elegibilidade"] == "elegível"].to_crs(config.CRS_PORTUGAL)
    # Tempo do centroide em condições reais: pré-filtro (o doente é confirmado depois)
    tempo_real = (poligonos["tempo_hospital_domicilio_min"] * config.CONDICOES_REAIS_FATOR_TRANSITO
                  + config.CONDICOES_REAIS_TEMPO_ACESSO_MIN)
    poligonos = poligonos[tempo_real <= config.LIMITE_TEMPO_MINUTOS]

    # População com 65 ou mais anos (BGRI 2021, mesmo recenseamento)
    partes = []
    for regiao in config.REGIOES_BGRI_NUTS2:
        ficheiro = next((config.PASTA_ENTRADA / f"BGRI21_{regiao}").glob("*.gpkg"))
        partes.append(pd.DataFrame(gpd.read_file(ficheiro, columns=["SUBSECCAO", config.INSTANCIAS_VARIAVEL_PESO],
                                                 ignore_geometry=True)))
    peso = pd.concat(partes).rename(columns={"SUBSECCAO": "id_subseccao",
                                             config.INSTANCIAS_VARIAVEL_PESO: "peso"})
    poligonos = poligonos.merge(peso, on="id_subseccao", how="left")
    poligonos["peso"] = poligonos["peso"].fillna(0)
    return poligonos[poligonos["peso"] > 0].reset_index(drop=True)


def ponto_aleatorio_no_poligono(poligono, gerador):
    """
    Sorteia um ponto ao acaso dentro de um polígono (método de rejeição: sorteia
    no retângulo envolvente até cair dentro do polígono).

    Parâmetros:
        poligono (shapely geometry): polígono em metros.
        gerador (numpy.random.Generator): gerador de números aleatórios.

    Devolve:
        shapely.Point: ponto dentro do polígono.
    """
    xmin, ymin, xmax, ymax = poligono.bounds
    for _ in range(1000):
        ponto = Point(gerador.uniform(xmin, xmax), gerador.uniform(ymin, ymax))
        if poligono.contains(ponto):
            return ponto
    return poligono.representative_point()


def morada_da_rua(latitude, longitude):
    """
    Geocodificação inversa (Nominatim/OpenStreetMap): que rua passa neste ponto?

    Parâmetros:
        latitude, longitude (float): ponto na rua.

    Devolve:
        dict ou None: morada (rua), codigo_postal, localidade, concelho.
    """
    import time
    try:
        resposta = requests.get(f"{config.GEOCODIFICACAO_URL}/reverse",
                                params={"lat": latitude, "lon": longitude, "format": "jsonv2",
                                        "zoom": 17, "addressdetails": 1},
                                headers=config.GEOCODIFICACAO_CABECALHOS, timeout=30)
        time.sleep(config.GEOCODIFICACAO_PAUSA_S)
        endereco = resposta.json().get("address", {})
    except (requests.RequestException, ValueError):
        return None
    rua = endereco.get("road") or endereco.get("pedestrian") or endereco.get("square")
    if not rua:
        return None
    localidade = (endereco.get("city") or endereco.get("town") or endereco.get("village")
                  or endereco.get("hamlet") or endereco.get("suburb") or "")
    return {"morada": rua, "codigo_postal": endereco.get("postcode", ""),
            "localidade": localidade, "concelho": endereco.get("municipality") or endereco.get("county", "")}


def sortear_candidatos(subseccoes, quantidade, gerador):
    """
    Sorteia doentes fictícios em ruas reais (passos 2 a 4).

    Parâmetros:
        subseccoes (GeoDataFrame): resultado de ler_subseccoes_elegiveis().
        quantidade (int): número de candidatos pretendido.
        gerador (numpy.random.Generator): gerador aleatório (com semente).

    Devolve:
        DataFrame: candidatos com morada, coordenadas e subsecção de origem.
    """
    probabilidades = subseccoes["peso"] / subseccoes["peso"].sum()
    para_wgs84 = gpd.GeoSeries([], crs=config.CRS_PORTUGAL)
    candidatos, tentativas = [], 0
    while len(candidatos) < quantidade and tentativas < quantidade * 5:
        tentativas += 1
        escolha = gerador.choice(len(subseccoes), p=probabilidades)
        sub = subseccoes.iloc[escolha]
        ponto = ponto_aleatorio_no_poligono(sub.geometry, gerador)
        ponto_wgs84 = para_wgs84.__class__([ponto], crs=config.CRS_PORTUGAL).to_crs(config.CRS_WGS84).iloc[0]
        estrada = ponto_mais_proximo_na_estrada(ponto_wgs84.x, ponto_wgs84.y)
        if not estrada or estrada[2] > config.INSTANCIAS_DISTANCIA_MAX_RUA_M:
            continue   # ponto num campo longe de estradas: sorteia outro
        lon, lat, _ = estrada
        morada = morada_da_rua(lat, lon)
        if not morada:
            continue   # caminho sem nome: sorteia outro
        candidatos.append({"latitude": round(lat, 6), "longitude": round(lon, 6), **morada,
                           "subseccao_sorteada": sub["id_subseccao"],
                           "municipio_bgri": sub["municipio"], "freguesia_bgri": sub["freguesia"],
                           "populacao_65_mais_subseccao": int(sub["peso"])})
        if len(candidatos) % 10 == 0:
            mensagem(f"   Candidatos sorteados: {len(candidatos)}/{quantidade}")
    return pd.DataFrame(candidatos)


def confirmar_30_minutos(candidatos):
    """
    Passo 5: tempo hospital → candidato com o motor de routing (2 pedidos) e
    seleção dos que ficam a ≤ 30 min em condições reais estimadas.

    Parâmetros:
        candidatos (DataFrame): resultado de sortear_candidatos().

    Devolve:
        DataFrame: candidatos com tempo_real_min e a coluna "dentro_dos_30min".
    """
    coordenadas = [(config.HOSPITAL_LONGITUDE, config.HOSPITAL_LATITUDE)]
    coordenadas += list(zip(candidatos["longitude"], candidatos["latitude"]))
    ida = pedir_matriz(coordenadas, sources=[0])
    livre = pd.Series(ida["durations"][0][1:], dtype=float) / 60
    candidatos = candidatos.copy()
    candidatos["tempo_fluxo_livre_min"] = livre.round(2).values
    candidatos["tempo_condicoes_reais_min"] = (livre * config.CONDICOES_REAIS_FATOR_TRANSITO
                                               + config.CONDICOES_REAIS_TEMPO_ACESSO_MIN).round(2).values
    candidatos["dentro_dos_30min"] = candidatos["tempo_condicoes_reais_min"] <= config.LIMITE_TEMPO_MINUTOS
    return candidatos


def gerar_instancias():
    """
    Executa todos os passos e grava instâncias, resultados e resumo.

    Devolve:
        DataFrame: resumo de todas as instâncias.
    """
    mensagem("=" * 70)
    mensagem(f"INSTÂNCIAS DE DOENTES — tamanhos {config.INSTANCIAS_TAMANHOS}")
    mensagem("=" * 70)
    maximo = max(config.INSTANCIAS_TAMANHOS)
    gerador = np.random.default_rng(config.INSTANCIAS_SEMENTE)
    ficheiro_doentes = PASTA / "doentes_todos.csv"
    pasta_matriz = PASTA / "matriz_completa"

    # Reutilizar doentes e matriz já calculados (poupa pedidos e quota).
    # Para gerar tudo de novo: python instancias_doentes/gerar_instancias.py --novo
    if "--novo" not in sys.argv and ficheiro_doentes.exists() and (pasta_matriz / "tempos_fluxo_livre_min.csv").exists():
        mensagem("   A reutilizar doentes e matriz completa já calculados (use --novo para gerar de novo).")
        selecionados = pd.read_csv(ficheiro_doentes, sep=";", decimal=",", dtype={"codigo_postal": str},
                                   keep_default_na=False)
        selecionados = selecionados.head(maximo)
        matriz = (pd.read_csv(pasta_matriz / "tempos_fluxo_livre_min.csv", sep=";", decimal=",", index_col=0),
                  pd.read_csv(pasta_matriz / "distancias_km.csv", sep=";", decimal=",", index_col=0),
                  pd.read_csv(pasta_matriz / "encaixe_na_rede.csv", sep=";", decimal=","))
        candidatos, rejeitados = selecionados, None
        return processar_instancias(selecionados, matriz, candidatos, rejeitados)

    subseccoes = ler_subseccoes_elegiveis()
    mensagem(f"   Subsecções a ≤ {config.LIMITE_TEMPO_MINUTOS} min com população 65+: {len(subseccoes)} "
             f"({int(subseccoes['peso'].sum()):,} residentes com 65+ anos)".replace(",", " "))

    # 2-5. Sortear, ligar à rua, morada, confirmar os 30 min (com substituições)
    quantidade = int(maximo * (1 + config.INSTANCIAS_CANDIDATOS_EXTRA))
    candidatos = sortear_candidatos(subseccoes, quantidade, gerador)
    candidatos = confirmar_30_minutos(candidatos)
    rejeitados = int((~candidatos["dentro_dos_30min"]).sum())
    mensagem(f"   Candidatos: {len(candidatos)} | a > {config.LIMITE_TEMPO_MINUTOS} min (substituídos): {rejeitados}")
    selecionados = candidatos[candidatos["dentro_dos_30min"]].head(maximo).reset_index(drop=True)
    if len(selecionados) < maximo:
        raise RuntimeError(f"Só {len(selecionados)} candidatos válidos; aumente INSTANCIAS_CANDIDATOS_EXTRA.")
    selecionados.insert(0, "id_doente", [f"P{i:03d}" for i in range(1, maximo + 1)])
    selecionados.to_csv(PASTA / "doentes_todos.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig")

    # 6. Uma só matriz completa (hospital + todos os doentes), guardada para reutilizar
    matriz = calcular_matriz(selecionados)
    pasta_matriz.mkdir(exist_ok=True)
    opcoes = {"sep": ";", "decimal": ",", "encoding": "utf-8-sig"}
    matriz[0].round(4).to_csv(pasta_matriz / "tempos_fluxo_livre_min.csv", **opcoes)
    matriz[1].round(4).to_csv(pasta_matriz / "distancias_km.csv", **opcoes)
    matriz[2].to_csv(pasta_matriz / "encaixe_na_rede.csv", index=False, **opcoes)
    return processar_instancias(selecionados, matriz, candidatos, rejeitados)


def processar_instancias(selecionados, matriz, candidatos, rejeitados):
    """
    Passo 7: grava cada instância (primeiros N doentes) e corre a Parte B com a
    sub-matriz correspondente; no fim grava o resumo.

    Parâmetros:
        selecionados (DataFrame): todos os doentes (P001...).
        matriz (tuple): (tempos, distancias, encaixe) da matriz completa.
        candidatos (DataFrame): candidatos sorteados (para os metadados).
        rejeitados (int ou None): candidatos substituídos por estarem a > 30 min.

    Devolve:
        DataFrame: resumo das instâncias.
    """
    # 7. Instâncias encaixadas
    colunas_entrada = ["id_doente", "morada", "codigo_postal", "localidade", "concelho", "latitude", "longitude"]
    resumo = []
    for tamanho in config.INSTANCIAS_TAMANHOS:
        nome = f"instancia_{tamanho:03d}"
        instancia = selecionados.head(tamanho)
        ficheiro = PASTA / f"{nome}.csv"
        instancia[colunas_entrada].to_csv(ficheiro, sep=";", index=False, encoding="utf-8-sig")
        pasta = PASTA / "resultados" / nome
        executar_matriz_doentes(ficheiro, pasta_resultados=pasta, matriz_pre_calculada=matriz,
                                desenhar_percursos=tamanho <= 20)
        tabela = pd.read_csv(pasta / "tabela_doentes.csv", sep=";", decimal=",")
        verificacoes = pd.read_csv(pasta / "verificacoes.csv", sep=";")
        reais = aplicar_condicoes_reais(matriz[0]).loc[["HOSPITAL"] + instancia["id_doente"].tolist(),
                                                       ["HOSPITAL"] + instancia["id_doente"].tolist()]
        resumo.append({
            "instancia": nome, "doentes": tamanho,
            "doentes_a_30min": int(tabela["dentro_dos_30min"].sum()),
            "matriz": f"{tamanho + 1} × {tamanho + 1}",
            "km_medio_hospital_doente": round(tabela["distancia_hospital_doente_km"].mean(), 2),
            "min_medio_hospital_doente_reais": round(tabela["tempo_hospital_doente_condicoes_reais_min"].mean(), 2),
            "min_maximo_hospital_doente_reais": round(tabela["tempo_hospital_doente_condicoes_reais_min"].max(), 2),
            "min_medio_entre_doentes_reais": round(reais.iloc[1:, 1:].to_numpy()[
                ~np.eye(tamanho, dtype=bool)].mean(), 2),
            "concelhos": ", ".join(sorted(instancia["municipio_bgri"].unique())),
            "verificacoes_matriz": "todas OK" if verificacoes["resultado"].isin(["OK", "INFO"]).all()
            else "; ".join(verificacoes.loc[~verificacoes["resultado"].isin(["OK", "INFO"]), "verificacao"]),
            "violacoes_triangulares_sem_transito": verificacoes.loc[
                verificacoes["verificacao"].str.contains("sem trânsito"), "valor"].str.split(" ").str[0].iloc[0],
        })

    resumo = pd.DataFrame(resumo)
    resumo.to_csv(PASTA / "resumo_instancias.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig")
    registar_metadados("instancias_doentes", {
        "tamanhos": config.INSTANCIAS_TAMANHOS, "semente": config.INSTANCIAS_SEMENTE,
        "peso": config.INSTANCIAS_VARIAVEL_PESO, "routing": descricao_motor(),
        "candidatos_sorteados": len(candidatos), "candidatos_substituidos_mais_30min": rejeitados,
        "matriz_completa": "instancias_doentes/matriz_completa/ (hospital + todos os doentes)",
        "nota": "Doentes fictícios em pontos de ruas reais do OpenStreetMap (sem número de porta).",
    })
    mensagem("-" * 70)
    for linha in resumo.drop(columns=["concelhos"]).to_string(index=False).splitlines():
        mensagem("   " + linha)
    mensagem(f"Instâncias gravadas em: {PASTA.relative_to(config.PASTA_PROJETO)}/")
    return resumo


if __name__ == "__main__":
    gerar_instancias()
