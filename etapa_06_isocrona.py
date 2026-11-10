"""
ETAPA 6 — Isócrona rodoviária de 30 minutos (área de cobertura)
================================================================

OBJETIVO
--------
Desenhar a área que se alcança de automóvel, a partir do hospital, em 30
minutos. Esta área chama-se ISÓCRONA ("igual tempo").

DUAS REPRESENTAÇÕES (complementares)
------------------------------------
  A) Isócrona calculada pelo Valhalla (outro motor de routing sobre a mesma
     rede OpenStreetMap). O OSRM não calcula isócronas, por isso usamos o
     Valhalla APENAS para a representação visual. Como os dois motores usam
     velocidades ligeiramente diferentes, a fronteira pode não coincidir
     exatamente com a classificação do OSRM.
  B) União dos polígonos das subsecções ELEGÍVEIS (classificadas com o OSRM).
     É a área de cobertura totalmente coerente com a classificação.

Se o Valhalla falhar, o programa continua apenas com a representação B.

Também se calcula a concordância entre os dois motores: % de centroides
elegíveis (OSRM) que ficam dentro da isócrona do Valhalla.

RESULTADOS
----------
    resultados/geojson/isocrona_30min.geojson
    resultados/geojson/area_subseccoes_elegiveis.geojson

EXECUTAR SÓ ESTA ETAPA (depois da etapa 5)
------------------------------------------
    python etapa_06_isocrona.py
"""

import time

import geopandas as gpd
import requests
from shapely.geometry import shape

import config
from routing import ler_chave_ors, motor_em_uso
from utilitarios import mensagem, registar_metadados, verificar_ficheiro_existe


def pedir_isocrona_valhalla(minutos):
    """
    Pede ao Valhalla a isócrona de "minutos" a partir do hospital.

    Parâmetros:
        minutos (int): tempo da isócrona.

    Devolve:
        GeoDataFrame ou None: polígono da isócrona (WGS84), ou None se falhar.
    """
    pedido = {
        "locations": [{"lat": config.HOSPITAL_LATITUDE, "lon": config.HOSPITAL_LONGITUDE}],
        "costing": config.VALHALLA_PERFIL,
        "contours": [{"time": minutos}],
        "polygons": True,
        "denoise": 0.5,
        "generalize": 50,
    }
    url = f"{config.VALHALLA_URL}/isochrone"
    for tentativa in range(1, 4):
        try:
            # O pedido é enviado em JSON no corpo de um POST (o servidor
            # público recusa o JSON passado no endereço com o erro 400).
            resposta = requests.post(url, json=pedido, timeout=120,
                                     headers=config.CABECALHOS_HTTP)
            resposta.raise_for_status()
            dados = resposta.json()
            geometria = shape(dados["features"][0]["geometry"])
            return gpd.GeoDataFrame({"minutos": [minutos], "motor": ["Valhalla"]},
                                    geometry=[geometria], crs=config.CRS_WGS84)
        except (requests.RequestException, ValueError, KeyError, IndexError) as erro:
            mensagem(f"   ERRO no Valhalla ({tentativa}/3): {erro}")
            time.sleep(2 ** tentativa)
    return None


def pedir_isocrona_ors(minutos):
    """
    Pede ao OpenRouteService a isócrona de "minutos" a partir do hospital.
    É o MESMO motor usado na classificação (etapa 3), por isso a isócrona e a
    classificação das subsecções são coerentes entre si.

    Parâmetros:
        minutos (int): tempo da isócrona.

    Devolve:
        GeoDataFrame ou None: polígono da isócrona (WGS84), ou None se falhar.
    """
    pedido = {"locations": [[config.HOSPITAL_LONGITUDE, config.HOSPITAL_LATITUDE]],
              "range": [minutos * 60], "range_type": "time", "smoothing": 5}
    cabecalhos = {"Authorization": ler_chave_ors(), "Content-Type": "application/json"}
    for tentativa in range(1, 4):
        try:
            resposta = requests.post(f"{config.ORS_URL}/v2/isochrones/{config.ORS_PERFIL}",
                                     json=pedido, headers=cabecalhos, timeout=120)
            resposta.raise_for_status()
            geometria = shape(resposta.json()["features"][0]["geometry"])
            return gpd.GeoDataFrame({"minutos": [minutos], "motor": ["OpenRouteService"]},
                                    geometry=[geometria], crs=config.CRS_WGS84)
        except (requests.RequestException, ValueError, KeyError, IndexError) as erro:
            mensagem(f"   ERRO no OpenRouteService ({tentativa}/3): {erro}")
            time.sleep(2 ** tentativa)
    return None


def pedir_isocrona(minutos):
    """
    Escolhe o serviço de isócronas conforme o motor de routing em uso.

    Parâmetros:
        minutos (int): tempo da isócrona.

    Devolve:
        tuple (GeoDataFrame ou None, str): isócrona e nome do serviço usado.
    """
    if motor_em_uso() == "ors":
        return pedir_isocrona_ors(minutos), "OpenRouteService"
    return pedir_isocrona_valhalla(minutos), "Valhalla"


def versao_valhalla():
    """
    Lê a versão do Valhalla e a data dos dados OSM carregados no servidor.

    Devolve:
        dict: versão e data (ou o erro, se o servidor não responder).
    """
    try:
        estado = requests.get(f"{config.VALHALLA_URL}/status", timeout=30,
                              headers=config.CABECALHOS_HTTP).json()
        data = estado.get("tileset_last_modified")
        return {"versao": estado.get("version"),
                "dados_osm_modificados_em": time.strftime("%Y-%m-%d", time.gmtime(data)) if data else None}
    except (requests.RequestException, ValueError) as erro:
        return {"erro": str(erro)}


def executar_etapa_6():
    """
    Executa a etapa 6: obtém a isócrona e a área das subsecções elegíveis.

    Devolve:
        tuple (GeoDataFrame ou None, GeoDataFrame): isócrona Valhalla e área elegível.
    """
    mensagem("=" * 70)
    mensagem(f"ETAPA 6 — Isócrona de {config.LIMITE_TEMPO_MINUTOS} minutos")
    mensagem("=" * 70)

    poligonos = gpd.read_file(config.PASTA_GEOJSON / "subseccoes_poligonos.geojson")
    elegiveis = poligonos[poligonos["elegibilidade"] == "elegível"]

    # B) União das subsecções elegíveis (sempre disponível)
    area = elegiveis.to_crs(config.CRS_PORTUGAL).geometry.buffer(1).union_all()
    area_elegivel = gpd.GeoDataFrame(
        {"descricao": [f"União das subsecções elegíveis ({motor_em_uso().upper()} ≤ {config.LIMITE_TEMPO_MINUTOS} min)"],
         "area_km2": [round(area.area / 1e6, 1)]},
        geometry=[area], crs=config.CRS_PORTUGAL).to_crs(config.CRS_WGS84)
    area_elegivel.to_file(config.PASTA_GEOJSON / "area_subseccoes_elegiveis.geojson", driver="GeoJSON")
    mensagem(f"   Área das subsecções elegíveis: {area_elegivel['area_km2'].iloc[0]} km²")

    # A) Isócrona (OpenRouteService se for o motor em uso; senão Valhalla)
    isocrona, servico = pedir_isocrona(config.LIMITE_TEMPO_MINUTOS)
    concordancia = None
    area_fora_portugal = None
    populacao_valhalla = None
    if isocrona is None:
        mensagem(f"   AVISO: isócrona ({servico}) indisponível; o mapa mostrará só a "
                 "área das subsecções elegíveis.")
        if config.FICHEIRO_ISOCRONA.exists():
            config.FICHEIRO_ISOCRONA.unlink()
    else:
        # Recortar a isócrona pelo território português. Se nenhuma parte da
        # isócrona estiver fora de Portugal, então NENHUM percurso de 30 min
        # passa por Espanha (qualquer ponto de um percurso ≤ 30 min também é
        # alcançável em ≤ 30 min e, por isso, está dentro da isócrona).
        territorio = gpd.read_file(config.FICHEIRO_TERRITORIO).to_crs(config.CRS_PORTUGAL)
        iso_metros = isocrona.to_crs(config.CRS_PORTUGAL)
        area_original = iso_metros.area.iloc[0] / 1e6
        recortada = iso_metros.geometry.iloc[0].intersection(territorio.geometry.iloc[0])
        area_fora_portugal = max(0.0, area_original - recortada.area / 1e6)
        isocrona = gpd.GeoDataFrame({"minutos": [config.LIMITE_TEMPO_MINUTOS], "motor": [servico],
                                     "recortada_por_portugal": [True]},
                                    geometry=[recortada], crs=config.CRS_PORTUGAL).to_crs(config.CRS_WGS84)
        mensagem(f"   Área da isócrona fora de Portugal (removida): {area_fora_portugal:.2f} km²")
        if area_fora_portugal < 0.5:
            mensagem("   OK: nenhum percurso de 30 min a partir do hospital sai de Portugal.")
        area_iso = recortada.area / 1e6
        isocrona["area_km2"] = round(area_iso, 1)
        isocrona.to_file(config.FICHEIRO_ISOCRONA, driver="GeoJSON")
        centroides = gpd.read_file(config.PASTA_GEOJSON / "subseccoes_centroides.geojson")
        eleg = centroides[centroides["elegibilidade"] == "elegível"]
        dentro = eleg.within(isocrona.geometry.iloc[0])
        concordancia = round(100 * dentro.mean(), 1)
        nao_eleg = centroides[centroides["elegibilidade"] != "elegível"]
        dentro_nao = round(100 * nao_eleg.within(isocrona.geometry.iloc[0]).mean(), 1)
        # Indicador de sensibilidade: população cujos centroides ficam dentro
        # da isócrona do Valhalla (outro motor, velocidades mais prudentes).
        populacao_valhalla = int(centroides.loc[centroides.within(isocrona.geometry.iloc[0]),
                                                "populacao_residente"].sum())
        mensagem(f"   Isócrona {servico}: {area_iso:.0f} km²; população com centroide "
                 f"dentro dela: {populacao_valhalla:,}".replace(",", " "))
        mensagem(f"   Concordância: {concordancia} % dos centroides elegíveis ({motor_em_uso().upper()}) "
                 f"estão dentro da isócrona {servico}; {dentro_nao} % dos não elegíveis também.")

    registar_metadados("etapa_06_isocrona", {
        "servico_isocrona": f"{servico} — serviço de isócronas",
        "servidor": config.ORS_URL if servico == "OpenRouteService" else config.VALHALLA_URL,
        "perfil": config.ORS_PERFIL if servico == "OpenRouteService" else config.VALHALLA_PERFIL,
        "valhalla": versao_valhalla() if servico == "Valhalla" else None,
        "isocrona_obtida": isocrona is not None,
        "isocrona_recortada_pelo_territorio_portugues": isocrona is not None,
        "area_isocrona_fora_de_portugal_km2": None if isocrona is None else round(area_fora_portugal, 2),
        "concordancia_centroides_elegiveis_percent": concordancia,
        "populacao_centroides_dentro_isocrona": populacao_valhalla,
        "nota": "A isócrona é ilustrativa; a elegibilidade é determinada pela matriz da etapa 3.",
    })
    mensagem("ETAPA 6 concluída.")
    return isocrona, area_elegivel


if __name__ == "__main__":
    verificar_ficheiro_existe(config.PASTA_GEOJSON / "subseccoes_poligonos.geojson",
                              "etapa_05_classificar_elegibilidade.py")
    executar_etapa_6()
