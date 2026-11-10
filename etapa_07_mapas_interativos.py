"""
ETAPA 7 — Mapas interativos (HTML)
===================================

OBJETIVO
--------
Criar mapas que se abrem em qualquer navegador (Chrome, Firefox, Edge...),
sem precisar de Python, para explorar os resultados.

MAPA 1 — resultados/mapas/mapa_centroides.html
    * Hospital (ícone vermelho).
    * Um círculo por subsecção, no centroide do polígono:
        verde  = elegível (≤ 30 min);   cinzento/laranja = não elegível.
      O tamanho do círculo cresce com a população residente.
    * Isócrona de 30 minutos (OpenRouteService ou Valhalla) e área das subsecções elegíveis.
    * Clicar num círculo mostra: identificador, designação, população,
      tempo e distância (ida e regresso) e classificação.
    * Caixa de pesquisa pelo identificador da subsecção.

MAPA 2 — resultados/mapas/mapa_poligonos_bgri.html
    * Polígonos das subsecções da BGRI 2021 coloridos pela elegibilidade.
    * Camada alternativa com a densidade populacional (hab./km²).
    * Isócrona, hospital e os mesmos dados ao clicar em cada polígono.

Use o controlo de camadas (canto superior direito) para ligar/desligar camadas.

EXECUTAR SÓ ESTA ETAPA (depois das etapas 5 e 6)
------------------------------------------------
    python etapa_07_mapas_interativos.py
"""

import branca.colormap as cm
import folium
import geopandas as gpd
import numpy as np
import shapely
from folium import plugins

import config
from routing import nome_motor, nome_servico_isocrona
from utilitarios import mensagem, registar_metadados, verificar_ficheiro_existe

COR_ELEGIVEL = "#1a9850"
COR_NAO_ELEGIVEL = "#e6550d"
COR_NAO_ELEGIVEL_SUAVE = "#8c8c8c"  # cinzento: não tapa o fundo OpenStreetMap
COR_ISOCRONA = "#2c7fb8"

# Campos mostrados ao clicar numa localização, e respetivas etiquetas
CAMPOS_POPUP = ["id_subseccao", "designacao", "populacao_residente",
                "tempo_hospital_domicilio_min", "distancia_hospital_domicilio_km",
                "tempo_domicilio_hospital_min", "distancia_domicilio_hospital_km",
                "elegibilidade", "estado_routing", "latitude", "longitude"]
ETIQUETAS_POPUP = ["Subsecção (BGRI 2021)", "Designação", "População residente (Censos 2021)",
                   "Tempo hospital → domicílio (min)", "Distância hospital → domicílio (km)",
                   "Tempo domicílio → hospital (min)", "Distância domicílio → hospital (km)",
                   "Classificação", "Estado do routing", "Latitude (centroide)",
                   "Longitude (centroide)"]


def criar_mapa_base():
    """
    Cria um mapa vazio centrado no hospital, com dois fundos à escolha.

    Devolve:
        folium.Map: o mapa.
    """
    mapa = folium.Map(location=[config.HOSPITAL_LATITUDE, config.HOSPITAL_LONGITUDE],
                      zoom_start=10, tiles=None, prefer_canvas=True, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(mapa)
    # Imagem de satélite: útil para ver onde estão realmente as casas
    # dentro de cada subsecção (e comparar com a posição do centroide).
    folium.TileLayer("Esri.WorldImagery", name="Satélite (Esri)", show=False).add_to(mapa)
    plugins.Fullscreen().add_to(mapa)
    return mapa


def adicionar_hospital(mapa):
    """
    Coloca o marcador do hospital no mapa.

    Parâmetros:
        mapa (folium.Map): mapa onde desenhar.
    """
    folium.Marker(
        [config.HOSPITAL_LATITUDE, config.HOSPITAL_LONGITUDE],
        tooltip="Hospital do Espírito Santo de Évora",
        popup=folium.Popup(f"<b>{config.HOSPITAL_NOME}</b><br>{config.HOSPITAL_MORADA}<br>"
                           f"Lat {config.HOSPITAL_LATITUDE}, Lon {config.HOSPITAL_LONGITUDE}",
                           max_width=300),
        icon=folium.Icon(color="red", icon="plus-sign"),
    ).add_to(mapa)


def adicionar_areas_cobertura(mapa, mostrar_area_elegivel=True):
    """
    Desenha a isócrona (se existir) e a área das subsecções elegíveis.

    Parâmetros:
        mapa (folium.Map): mapa onde desenhar.
        mostrar_area_elegivel (bool): se a camada da área elegível começa visível.
    """
    if config.FICHEIRO_ISOCRONA.exists():
        isocrona = gpd.read_file(config.FICHEIRO_ISOCRONA)
        folium.GeoJson(
            isocrona, name=f"Isócrona {config.LIMITE_TEMPO_MINUTOS} min ({nome_servico_isocrona()})",
            style_function=lambda f: {"color": COR_ISOCRONA, "weight": 1.5, "opacity": 0.9,
                                      "fillColor": COR_ISOCRONA, "fillOpacity": 0.12},
            tooltip=f"Isócrona rodoviária de {config.LIMITE_TEMPO_MINUTOS} min ({nome_servico_isocrona()}/OSM)",
        ).add_to(mapa)
    area = gpd.read_file(config.PASTA_GEOJSON / "area_subseccoes_elegiveis.geojson")
    folium.GeoJson(
        area, name=f"Área das subsecções elegíveis ({nome_motor()})", show=mostrar_area_elegivel,
        style_function=lambda f: {"color": COR_ELEGIVEL, "weight": 2, "fillOpacity": 0.06},
        tooltip=f"União das subsecções com tempo ≤ {config.LIMITE_TEMPO_MINUTOS} min ({nome_motor()})",
    ).add_to(mapa)


def adicionar_legenda(mapa, texto_extra=""):
    """
    Acrescenta uma legenda fixa no canto inferior esquerdo.

    Parâmetros:
        mapa (folium.Map): mapa onde desenhar.
        texto_extra (str): linhas HTML adicionais.
    """
    html = f"""
    <div style="position: fixed; bottom: 55px; left: 10px; z-index: 9999; background: rgba(255,255,255,0.93);
                padding: 10px 12px; border: 1px solid #999; border-radius: 6px;
                font: 13px Arial, sans-serif; max-width: 300px;">
      <b>Hospitalização Domiciliária — HESE Évora</b><br>
      <span style="color:{COR_ELEGIVEL};">&#9679;</span> Elegível (≤ {config.LIMITE_TEMPO_MINUTOS} min)<br>
      <span style="color:{COR_NAO_ELEGIVEL_SUAVE};">&#9679;</span> Não elegível (&gt; {config.LIMITE_TEMPO_MINUTOS} min)<br>
      <span style="background:{COR_ISOCRONA};opacity:0.35;">&nbsp;&nbsp;&nbsp;&nbsp;</span> Isócrona {config.LIMITE_TEMPO_MINUTOS} min ({nome_servico_isocrona()})<br>
      {texto_extra}
      <small>População: INE, Censos 2021 / BGRI 2021. Rede: © OpenStreetMap.
      Tempos: {nome_motor()} (rede OpenStreetMap), sem trânsito. Pontos = centroides (aproximação).</small>
    </div>"""
    mapa.get_root().html.add_child(folium.Element(html))


def enquadrar_na_area_elegivel(mapa):
    """
    Ajusta a vista inicial do mapa à área das subsecções elegíveis (com margem),
    para que a zona de cobertura apareça logo ao abrir o mapa.

    Parâmetros:
        mapa (folium.Map): mapa a enquadrar.
    """
    area = gpd.read_file(config.PASTA_GEOJSON / "area_subseccoes_elegiveis.geojson")
    oeste, sul, leste, norte = area.total_bounds
    mapa.fit_bounds([[sul, oeste], [norte, leste]], padding=(30, 30))


def criar_mapa_centroides(centroides):
    """
    Constrói o MAPA 1 (centroides) e grava-o em HTML.

    Parâmetros:
        centroides (GeoDataFrame): pontos da etapa 5.

    Devolve:
        Path: caminho do ficheiro HTML criado.
    """
    mapa = criar_mapa_base()
    adicionar_areas_cobertura(mapa, mostrar_area_elegivel=False)

    # Raio do círculo proporcional à raiz quadrada da população (mín. 2 px)
    centroides = centroides.copy()
    centroides["raio"] = (2 + np.sqrt(centroides["populacao_residente"]) / 4).clip(upper=9).round(1)

    for classe, cor, visivel, opacidade in [("elegível", COR_ELEGIVEL, True, 0.75),
                                            ("não elegível", COR_NAO_ELEGIVEL_SUAVE, True, 0.35)]:
        grupo = centroides[centroides["elegibilidade"] == classe]
        camada = folium.GeoJson(
            grupo[CAMPOS_POPUP + ["raio", "geometry"]],
            name=f"Centroides — {classe} ({len(grupo)})", show=visivel,
            marker=folium.CircleMarker(radius=4, weight=0.5, fill=True),
            style_function=lambda f, cor=cor, opacidade=opacidade: {
                "color": "white", "weight": 0.5, "fillColor": cor, "fillOpacity": opacidade,
                "radius": f["properties"]["raio"]},
            tooltip=folium.GeoJsonTooltip(fields=["designacao", "tempo_hospital_domicilio_min"],
                                          aliases=["", "Tempo (min):"]),
            popup=folium.GeoJsonPopup(fields=CAMPOS_POPUP, aliases=ETIQUETAS_POPUP, max_width=400),
        )
        camada.add_to(mapa)
        if classe == "elegível":
            camada_pesquisa = camada

    plugins.Search(layer=camada_pesquisa, search_label="id_subseccao", geom_type="Point",
                   placeholder="Pesquisar subsecção elegível (11 dígitos)",
                   collapsed=False, search_zoom=15).add_to(mapa)
    adicionar_hospital(mapa)
    adicionar_legenda(mapa, "Tamanho do círculo ∝ população residente<br>")
    folium.LayerControl(collapsed=False).add_to(mapa)

    enquadrar_na_area_elegivel(mapa)
    destino = config.PASTA_MAPAS / "mapa_centroides.html"
    mapa.save(destino)
    return destino


def criar_mapa_poligonos(poligonos):
    """
    Constrói o MAPA 2 (polígonos BGRI 2021) e grava-o em HTML.

    Os polígonos são simplificados (tolerância de 10 m) apenas para o mapa
    ficar mais leve; os cálculos usam sempre a geometria original.

    Parâmetros:
        poligonos (GeoDataFrame): polígonos da etapa 5 (WGS84).

    Devolve:
        Path: caminho do ficheiro HTML criado.
    """
    metricos = poligonos.to_crs(config.CRS_PORTUGAL)
    poligonos = poligonos.copy()
    poligonos["area_km2"] = (metricos.area / 1e6).round(4)
    poligonos["densidade_hab_km2"] = (poligonos["populacao_residente"] /
                                      poligonos["area_km2"].where(poligonos["area_km2"] > 0)).round(1).fillna(0)
    # Simplificar (10 m) e arredondar as coordenadas a 5 casas decimais (~1 m)
    # só para o ficheiro HTML ficar mais leve.
    poligonos["geometry"] = shapely.set_precision(
        metricos.geometry.simplify(10).to_crs(config.CRS_WGS84).values, 0.00001)

    mapa = criar_mapa_base()
    campos = CAMPOS_POPUP + ["densidade_hab_km2"]
    etiquetas = ETIQUETAS_POPUP + ["Densidade (hab./km²)"]

    folium.GeoJson(
        poligonos[campos + ["geometry"]], name="Subsecções — elegibilidade",
        style_function=lambda f: {
            "color": COR_ELEGIVEL if f["properties"]["elegibilidade"] == "elegível" else "#999999",
            "weight": 0.6 if f["properties"]["elegibilidade"] == "elegível" else 0.3,
            "opacity": 0.8 if f["properties"]["elegibilidade"] == "elegível" else 0.4,
            "fillColor": COR_ELEGIVEL if f["properties"]["elegibilidade"] == "elegível" else "#bbbbbb",
            "fillOpacity": 0.35 if f["properties"]["elegibilidade"] == "elegível" else 0.03},
        highlight_function=lambda f: {"weight": 2, "color": "black"},
        tooltip=folium.GeoJsonTooltip(fields=["designacao", "populacao_residente"],
                                      aliases=["", "Residentes:"]),
        popup=folium.GeoJsonPopup(fields=campos, aliases=etiquetas, max_width=400),
    ).add_to(mapa)

    # Densidade populacional em escala logarítmica (muitas subsecções têm 0)
    escala = cm.LinearColormap(["#ffffcc", "#fd8d3c", "#800026"], vmin=0, vmax=4,
                               caption="Densidade populacional — log10(hab./km² + 1)")
    folium.GeoJson(
        poligonos[campos + ["geometry"]], name="Subsecções — densidade populacional", show=False,
        style_function=lambda f: {
            "color": "#777", "weight": 0.2, "fillOpacity": 0.55,
            "fillColor": escala(min(4, np.log10(f["properties"]["densidade_hab_km2"] + 1)))},
        tooltip=folium.GeoJsonTooltip(fields=["designacao", "densidade_hab_km2"],
                                      aliases=["", "hab./km²:"]),
        popup=folium.GeoJsonPopup(fields=campos, aliases=etiquetas, max_width=400),
    ).add_to(mapa)
    escala.add_to(mapa)

    adicionar_areas_cobertura(mapa, mostrar_area_elegivel=False)
    adicionar_hospital(mapa)
    adicionar_legenda(mapa, "Polígonos: subsecções estatísticas BGRI 2021<br>")
    folium.LayerControl(collapsed=False).add_to(mapa)

    enquadrar_na_area_elegivel(mapa)
    destino = config.PASTA_MAPAS / "mapa_poligonos_bgri.html"
    mapa.save(destino)
    return destino


def executar_etapa_7():
    """
    Executa a etapa 7: cria os dois mapas HTML.

    Devolve:
        list[Path]: ficheiros criados.
    """
    mensagem("=" * 70)
    mensagem("ETAPA 7 — Mapas interativos")
    mensagem("=" * 70)
    config.PASTA_MAPAS.mkdir(parents=True, exist_ok=True)
    centroides = gpd.read_file(config.PASTA_GEOJSON / "subseccoes_centroides.geojson")
    poligonos = gpd.read_file(config.PASTA_GEOJSON / "subseccoes_poligonos.geojson")

    ficheiros = [criar_mapa_centroides(centroides), criar_mapa_poligonos(poligonos)]
    for ficheiro in ficheiros:
        mensagem(f"   Mapa criado: {ficheiro.relative_to(config.PASTA_PROJETO)} "
                 f"({ficheiro.stat().st_size / 1e6:.1f} MB)")
    registar_metadados("etapa_07_mapas", {
        "ficheiros": [str(f.relative_to(config.PASTA_PROJETO)) for f in ficheiros],
        "biblioteca": f"folium {folium.__version__}",
        "simplificacao_poligonos_m": 10,
    })
    mensagem("ETAPA 7 concluída. Abra os ficheiros .html num navegador.")
    return ficheiros


if __name__ == "__main__":
    verificar_ficheiro_existe(config.PASTA_GEOJSON / "subseccoes_centroides.geojson",
                              "etapa_05_classificar_elegibilidade.py")
    executar_etapa_7()
