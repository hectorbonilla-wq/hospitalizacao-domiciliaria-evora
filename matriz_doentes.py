"""
PARTE B — Doentes identificados pela MORADA: geocodificação, tempos ao
hospital e matriz quadrada dos doentes a ≤ 30 minutos
=======================================================================

PARA QUE SERVE
--------------
A Parte A (etapas 1 a 9) responde à pergunta "quantas pessoas vivem a 30 min
do hospital?". Esta Parte B serve o dia a dia do serviço:

    "Tenho estes doentes, com estas moradas. Quais estão a 30 minutos ou
     menos do hospital? E quanto tempo demora ir de cada um a cada outro?"

PASSOS
------
  1. LER o ficheiro de doentes (identificador + morada).
  2. GEOCODIFICAR: converter cada morada em latitude/longitude com o
     Nominatim (OpenStreetMap), procurando só em Portugal. Guarda-se o
     endereço encontrado e a precisão (número de porta, rua, localidade...).
     Se a morada completa não for encontrada, tenta-se só "código postal +
     localidade" e marca-se a precisão como mais baixa.
  3. VALIDAR: coordenadas dentro do território português (BGRI 2021).
  4. CALCULAR com o OSRM (rede OpenStreetMap) os tempos e distâncias entre o
     hospital e TODOS os doentes, nos dois sentidos, separadamente.
  5. CONDIÇÕES REAIS (estimativa): tempo_real = fluxo_livre × fator + acesso
     (parâmetros em config.py). A regra dos 30 min usa este tempo real.
  6. SELECIONAR os doentes a ≤ 30 min (hospital → doente, condições reais).
  7. MATRIZ QUADRADA: hospital + doentes selecionados, todos para todos.
     A LINHA é a ORIGEM e a COLUNA é o DESTINO; as linhas e as colunas têm a
     mesma ordem; a diagonal é 0; A→B e B→A são calculados separadamente.
  8. VERIFICAR (sem rotas em falta, diagonal 0, desigualdade triangular,
     assimetria, pontos em Portugal) e EXPORTAR (CSV, Excel, mapa HTML).

FICHEIRO DE ENTRADA (CSV, separador ";")
----------------------------------------
    id_doente;morada;codigo_postal;localidade
    D01;Rua 5 de Outubro;7000-854;Évora

Colunas opcionais: latitude;longitude — se estiverem preenchidas, a morada
não é geocodificada (útil quando já se tem o GPS do domicílio).

PRIVACIDADE (IMPORTANTE)
------------------------
Moradas de doentes são dados pessoais de saúde (RGPD). Na geocodificação, as
moradas são ENVIADAS para o servidor Nominatim definido em config.py. Não
coloque nomes, diagnósticos ou outros dados no ficheiro — só um código e a
morada. Para doentes reais, confirme com o Encarregado de Proteção de Dados
ou use um Nominatim instalado na instituição. Os ficheiros de doentes e os
seus resultados NÃO vão para o GitHub (.gitignore), exceto o exemplo.

COMO EXECUTAR
-------------
    python matriz_doentes.py                                  # exemplo
    python matriz_doentes.py doentes/os_meus_doentes.csv      # o seu ficheiro

Resultados em: resultados/doentes/<nome_do_ficheiro>/
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import folium
import geopandas as gpd
import numpy as np
import pandas as pd
import requests

import config
from etapa_02_preparar_subseccoes import validar_coordenadas
from etapa_03_calcular_matrizes_osrm import pedir_tabela_osrm
from etapa_04_verificar_consistencia import contar_violacoes_triangulares
from utilitarios import mensagem

PASTA_DOENTES = config.PASTA_PROJETO / "doentes"
FICHEIRO_EXEMPLO = PASTA_DOENTES / "doentes_exemplo.csv"
FICHEIRO_CACHE_GEOCODIFICACAO = PASTA_DOENTES / "cache_geocodificacao.csv"
MAXIMO_DOENTES = 99   # hospital + 99 doentes = 100 pontos (um pedido ao OSRM público)

# Tipos de resultado do Nominatim e a precisão correspondente
PRECISAO_POR_TIPO = {
    "house": "número de porta", "building": "edifício", "amenity": "edifício/equipamento",
    "place": "número de porta", "residential": "rua", "road": "rua", "pedestrian": "rua",
    "square": "rua/praça", "primary": "rua", "secondary": "rua", "tertiary": "rua",
    "unclassified": "rua", "living_street": "rua", "service": "rua",
    "postcode": "código postal", "neighbourhood": "bairro", "suburb": "bairro",
    "hamlet": "localidade", "village": "localidade", "town": "localidade",
    "city": "localidade", "municipality": "concelho",
}
# Precisão baixa: mostra um aviso. Precisão insuficiente: o doente é EXCLUÍDO
# (um ponto no centro da vila pode estar a vários km do domicílio real).
PRECISAO_BAIXA = {"código postal", "bairro", "desconhecida"}
PRECISAO_INSUFICIENTE = {"localidade", "concelho"}


# ---------------------------------------------------------------------------
# 1. Ler o ficheiro de doentes
# ---------------------------------------------------------------------------
def ler_doentes(caminho):
    """
    Lê o ficheiro CSV de doentes.

    Parâmetros:
        caminho (Path): CSV com id_doente, morada, codigo_postal, localidade
        (e, opcionalmente, latitude e longitude).

    Devolve:
        DataFrame: uma linha por doente (latitude/longitude numéricas ou vazias).

    Erros:
        ValueError se faltarem colunas, houver identificadores repetidos ou
        doentes a mais.
    """
    doentes = pd.read_csv(caminho, sep=None, engine="python", dtype=str,
                          encoding="utf-8-sig", keep_default_na=False)
    doentes.columns = [c.strip().lower() for c in doentes.columns]
    if "id_doente" not in doentes.columns:
        raise ValueError("Falta a coluna obrigatória 'id_doente'.")
    if "morada" not in doentes.columns and not {"latitude", "longitude"} <= set(doentes.columns):
        raise ValueError("O ficheiro precisa da coluna 'morada' (ou de 'latitude' e 'longitude').")
    for coluna in ["morada", "codigo_postal", "localidade", "latitude", "longitude"]:
        if coluna not in doentes.columns:
            doentes[coluna] = ""
        doentes[coluna] = doentes[coluna].str.strip()

    doentes["id_doente"] = doentes["id_doente"].str.strip()
    repetidos = doentes.loc[doentes["id_doente"].duplicated(), "id_doente"].tolist()
    if repetidos:
        raise ValueError(f"Identificadores de doente repetidos: {repetidos}")
    if len(doentes) > MAXIMO_DOENTES:
        raise ValueError(f"O ficheiro tem {len(doentes)} doentes; o máximo é {MAXIMO_DOENTES}.")

    # Coordenadas já conhecidas (aceita vírgula decimal: 38,5689)
    for coluna in ["latitude", "longitude"]:
        doentes[coluna] = pd.to_numeric(doentes[coluna].str.replace(",", ".", regex=False),
                                        errors="coerce")
    return doentes


# ---------------------------------------------------------------------------
# 2. Geocodificar as moradas
# ---------------------------------------------------------------------------
def texto_da_morada(linha):
    """
    Junta morada, código postal e localidade num só texto de pesquisa.

    Parâmetros:
        linha (pandas.Series): uma linha do ficheiro de doentes.

    Devolve:
        str: ex. "Rua 5 de Outubro, 7000-854 Évora".
    """
    fim = " ".join(p for p in [linha["codigo_postal"], linha["localidade"]] if p)
    return ", ".join(p for p in [linha["morada"], fim] if p)


def pesquisar_nominatim(texto):
    """
    Pergunta ao Nominatim (OpenStreetMap) as coordenadas de um texto,
    procurando apenas em Portugal.

    Parâmetros:
        texto (str): morada a pesquisar.

    Devolve:
        dict ou None: latitude, longitude, endereço encontrado e tipo; None se
        não encontrar.

    Erros:
        RuntimeError se o serviço falhar repetidamente.
    """
    parametros = {"q": texto, "format": "jsonv2", "countrycodes": "pt", "limit": 1}
    for tentativa in range(1, 4):
        try:
            resposta = requests.get(f"{config.GEOCODIFICACAO_URL}/search", params=parametros,
                                    headers=config.GEOCODIFICACAO_CABECALHOS, timeout=30)
            time.sleep(config.GEOCODIFICACAO_PAUSA_S)   # regra: máx. 1 pedido/segundo
            resposta.raise_for_status()
            resultados = resposta.json()
            if not resultados:
                return None
            r = resultados[0]
            return {"latitude": float(r["lat"]), "longitude": float(r["lon"]),
                    "endereco_encontrado": r.get("display_name", ""),
                    "tipo": r.get("addresstype") or r.get("type", "")}
        except (requests.RequestException, ValueError) as erro:
            mensagem(f"      ERRO no Nominatim ({tentativa}/3): {erro}")
            time.sleep(2 ** tentativa)
    raise RuntimeError("O serviço de geocodificação não respondeu.")


def geocodificar(doentes):
    """
    Obtém as coordenadas de cada doente a partir da morada.

    Ordem: (1) coordenadas já preenchidas no ficheiro; (2) cache local de
    pesquisas anteriores; (3) Nominatim com a morada completa; (4) Nominatim só
    com "código postal + localidade" (precisão baixa).

    Parâmetros:
        doentes (DataFrame): resultado de ler_doentes().

    Devolve:
        DataFrame: com latitude, longitude, endereco_encontrado,
        precisao_geocodificacao e fonte_coordenadas.
    """
    cache = {}
    if FICHEIRO_CACHE_GEOCODIFICACAO.exists():
        tabela_cache = pd.read_csv(FICHEIRO_CACHE_GEOCODIFICACAO, sep=";", dtype=str, keep_default_na=False)
        cache = {l["pesquisa"]: l for _, l in tabela_cache.iterrows()}

    doentes = doentes.copy()
    doentes["endereco_pesquisado"] = doentes.apply(texto_da_morada, axis=1)
    doentes["endereco_encontrado"] = ""
    doentes["precisao_geocodificacao"] = ""
    doentes["fonte_coordenadas"] = ""

    a_pesquisar = doentes["latitude"].isna() | doentes["longitude"].isna()
    if a_pesquisar.any():
        mensagem(f"   A geocodificar {int(a_pesquisar.sum())} moradas em {config.GEOCODIFICACAO_URL} "
                 "(as moradas são enviadas a este serviço — ver PRIVACIDADE no início do ficheiro)")
    doentes.loc[~a_pesquisar, "fonte_coordenadas"] = "coordenadas indicadas no ficheiro"
    doentes.loc[~a_pesquisar, "precisao_geocodificacao"] = "indicada pelo utilizador"

    novos_cache = []
    for indice in doentes.index[a_pesquisar]:
        linha = doentes.loc[indice]
        tentativas = [(linha["endereco_pesquisado"], "morada completa")]
        alternativa = " ".join(p for p in [linha["codigo_postal"], linha["localidade"]] if p)
        if alternativa and alternativa != linha["endereco_pesquisado"]:
            tentativas.append((alternativa, "só código postal e localidade"))

        encontrado, como = None, ""
        for texto, descricao in tentativas:
            if not texto:
                continue
            if texto in cache:
                c = cache[texto]
                encontrado = None if c["latitude"] == "" else {
                    "latitude": float(c["latitude"]), "longitude": float(c["longitude"]),
                    "endereco_encontrado": c["endereco_encontrado"], "tipo": c["tipo"]}
            else:
                encontrado = pesquisar_nominatim(texto)
                registo = {"pesquisa": texto, "latitude": "", "longitude": "",
                           "endereco_encontrado": "", "tipo": "",
                           "data": datetime.now().isoformat(timespec="seconds")}
                if encontrado:
                    registo.update({k: str(v) for k, v in encontrado.items()})
                cache[texto] = registo
                novos_cache.append(registo)
            if encontrado:
                como = descricao
                break

        if encontrado is None:
            doentes.loc[indice, "precisao_geocodificacao"] = "morada não encontrada"
            mensagem(f"   NÃO ENCONTRADA {linha['id_doente']}: {linha['endereco_pesquisado']}")
            continue
        precisao = PRECISAO_POR_TIPO.get(encontrado["tipo"], "desconhecida")
        if como != "morada completa" and precisao not in PRECISAO_INSUFICIENTE:
            precisao = "código postal"
        doentes.loc[indice, ["latitude", "longitude"]] = [encontrado["latitude"], encontrado["longitude"]]
        doentes.loc[indice, "endereco_encontrado"] = encontrado["endereco_encontrado"]
        doentes.loc[indice, "precisao_geocodificacao"] = precisao
        doentes.loc[indice, "fonte_coordenadas"] = f"Nominatim/OpenStreetMap ({como})"
        aviso = ""
        if precisao in PRECISAO_BAIXA:
            aviso = "  <- precisão baixa, confirme a morada"
        if precisao in PRECISAO_INSUFICIENTE:
            aviso = "  <- só encontrou a localidade: SERÁ EXCLUÍDO"
        mensagem(f"   {linha['id_doente']}: {encontrado['latitude']:.6f}, {encontrado['longitude']:.6f} "
                 f"[{precisao}]{aviso}")

    if novos_cache:
        PASTA_DOENTES.mkdir(exist_ok=True)
        pd.DataFrame(list(cache.values())).to_csv(FICHEIRO_CACHE_GEOCODIFICACAO, sep=";",
                                                  index=False, encoding="utf-8-sig")
    return doentes


# ---------------------------------------------------------------------------
# 3. Validar as coordenadas (dentro de Portugal)
# ---------------------------------------------------------------------------
def validar_doentes(doentes):
    """
    Confirma que cada doente tem coordenadas válidas em território português.

    Parâmetros:
        doentes (DataFrame): resultado de geocodificar().

    Devolve:
        DataFrame: o mesmo, com a coluna "estado" preenchida para os
        doentes com problemas ("" = sem problemas).
    """
    doentes = doentes.copy()
    doentes["estado"] = ""
    doentes.loc[doentes["precisao_geocodificacao"] == "morada não encontrada", "estado"] = "morada não encontrada"
    insuficiente = doentes["precisao_geocodificacao"].isin(PRECISAO_INSUFICIENTE)
    doentes.loc[insuficiente, "estado"] = ("morada não localizada com precisão (só a localidade) — "
                                           "corrija a morada ou indique latitude/longitude")
    plausivel = np.array([validar_coordenadas(la, lo) for la, lo in
                          zip(doentes["latitude"], doentes["longitude"])])
    doentes.loc[~plausivel & (doentes["estado"] == ""), "estado"] = "coordenadas inválidas"

    if config.FICHEIRO_TERRITORIO.exists():
        territorio = gpd.read_file(config.FICHEIRO_TERRITORIO).to_crs(config.CRS_WGS84).geometry.iloc[0]
        pontos = gpd.GeoSeries(gpd.points_from_xy(doentes["longitude"], doentes["latitude"]),
                               crs=config.CRS_WGS84)
        fora = (~pontos.within(territorio)).values & (doentes["estado"] == "").values
        doentes.loc[fora, "estado"] = "fora da área de estudo / de Portugal"
    for _, linha in doentes[doentes["estado"] != ""].iterrows():
        mensagem(f"   EXCLUÍDO {linha['id_doente']}: {linha['estado']}")
    return doentes


# ---------------------------------------------------------------------------
# 4 e 5. Matriz OSRM e condições reais
# ---------------------------------------------------------------------------
def calcular_matriz_osrm(doentes):
    """
    Pede ao OSRM a matriz completa (hospital + doentes, todos para todos).

    Parâmetros:
        doentes (DataFrame): doentes com coordenadas válidas.

    Devolve:
        tuple (DataFrame, DataFrame, DataFrame): tempos em fluxo livre (min),
        distâncias (km) e encaixe de cada ponto na rede. Índice e colunas:
        "HOSPITAL" seguido dos id_doente, pela mesma ordem.
    """
    etiquetas = ["HOSPITAL"] + doentes["id_doente"].tolist()
    coordenadas = [(config.HOSPITAL_LONGITUDE, config.HOSPITAL_LATITUDE)]
    coordenadas += list(zip(doentes["longitude"], doentes["latitude"]))
    mensagem(f"   A pedir ao OSRM a matriz {len(etiquetas)} × {len(etiquetas)} (rede OpenStreetMap)...")
    resposta = pedir_tabela_osrm(coordenadas)
    tempos = pd.DataFrame(resposta["durations"], index=etiquetas, columns=etiquetas, dtype=float) / 60
    distancias = pd.DataFrame(resposta["distances"], index=etiquetas, columns=etiquetas, dtype=float) / 1000
    encaixe = pd.DataFrame({
        "ponto": etiquetas,
        "distancia_ate_estrada_m": [round(p.get("distance", 0), 1) for p in resposta["sources"]],
        "rua_mais_proxima": [p.get("name", "") for p in resposta["sources"]],
        "longitude_na_estrada": [p["location"][0] for p in resposta["sources"]],
        "latitude_na_estrada": [p["location"][1] for p in resposta["sources"]],
    })
    return tempos, distancias, encaixe


def aplicar_condicoes_reais(tempos_fluxo_livre):
    """
    Converte tempos de fluxo livre em tempos estimados em condições reais:

        tempo_real = tempo_fluxo_livre × FATOR_TRANSITO + TEMPO_ACESSO

    O tempo de acesso (estacionar e chegar à porta) não se soma na diagonal
    (de um ponto para si próprio o tempo continua a ser 0).

    Parâmetros:
        tempos_fluxo_livre (DataFrame): matriz em minutos.

    Devolve:
        DataFrame: matriz em minutos, em condições reais (estimativa).
    """
    reais = tempos_fluxo_livre * config.CONDICOES_REAIS_FATOR_TRANSITO + config.CONDICOES_REAIS_TEMPO_ACESSO_MIN
    valores = reais.to_numpy(copy=True)
    np.fill_diagonal(valores, 0.0)
    return pd.DataFrame(valores, index=reais.index, columns=reais.columns)


# ---------------------------------------------------------------------------
# 6. Tabela por doente e seleção dos doentes a ≤ 30 min
# ---------------------------------------------------------------------------
def tabela_por_doente(doentes, tempos_livre, tempos_reais, distancias, encaixe):
    """
    Uma linha por doente: morada, coordenadas, km e minutos de/para o hospital
    e se cumpre os 30 minutos (em condições reais estimadas).

    Parâmetros:
        doentes (DataFrame): todos os doentes (com "estado").
        tempos_livre, tempos_reais, distancias, encaixe: resultados da matriz.

    Devolve:
        DataFrame: tabela por doente.
    """
    tabela = doentes.copy()
    for coluna in ["distancia_hospital_doente_km", "tempo_hospital_doente_fluxo_livre_min",
                   "tempo_hospital_doente_condicoes_reais_min", "distancia_doente_hospital_km",
                   "tempo_doente_hospital_fluxo_livre_min", "tempo_doente_hospital_condicoes_reais_min",
                   "distancia_ate_estrada_m"]:
        tabela[coluna] = np.nan
    calculados = tabela["estado"] == ""
    ids = tabela.loc[calculados, "id_doente"]
    tabela.loc[calculados, "distancia_hospital_doente_km"] = distancias.loc["HOSPITAL", ids].values
    tabela.loc[calculados, "tempo_hospital_doente_fluxo_livre_min"] = tempos_livre.loc["HOSPITAL", ids].values
    tabela.loc[calculados, "tempo_hospital_doente_condicoes_reais_min"] = tempos_reais.loc["HOSPITAL", ids].values
    tabela.loc[calculados, "distancia_doente_hospital_km"] = distancias.loc[ids, "HOSPITAL"].values
    tabela.loc[calculados, "tempo_doente_hospital_fluxo_livre_min"] = tempos_livre.loc[ids, "HOSPITAL"].values
    tabela.loc[calculados, "tempo_doente_hospital_condicoes_reais_min"] = tempos_reais.loc[ids, "HOSPITAL"].values
    tabela.loc[calculados, "distancia_ate_estrada_m"] = encaixe.set_index("ponto").loc[ids, "distancia_ate_estrada_m"].values

    sem_rota = calculados & tabela["tempo_hospital_doente_fluxo_livre_min"].isna()
    tabela.loc[sem_rota, "estado"] = "sem rota na rede rodoviária"
    dentro = tabela["tempo_hospital_doente_condicoes_reais_min"] <= config.LIMITE_TEMPO_MINUTOS
    tabela["dentro_dos_30min"] = dentro
    tabela.loc[(tabela["estado"] == "") & dentro, "estado"] = f"incluído (≤ {config.LIMITE_TEMPO_MINUTOS} min)"
    tabela.loc[(tabela["estado"] == "") & ~dentro, "estado"] = f"excluído (> {config.LIMITE_TEMPO_MINUTOS} min)"
    tabela["tempo_hospital_doente_fluxo_livre_min"] = tabela["tempo_hospital_doente_fluxo_livre_min"].round(2)
    for coluna in tabela.columns:
        if coluna.endswith("_min") or coluna.endswith("_km"):
            tabela[coluna] = tabela[coluna].astype(float).round(2 if coluna.endswith("_min") else 3)
    return tabela


# ---------------------------------------------------------------------------
# 7 e 8. Matriz quadrada, verificações e exportação
# ---------------------------------------------------------------------------
def matriz_quadrada(matriz, ids_incluidos):
    """
    Extrai a matriz quadrada do hospital + doentes incluídos.

    Como cada percurso mais rápido de A para B não depende dos outros pontos,
    basta "recortar" a matriz completa: as linhas e as colunas ficam com a
    mesma ordem (HOSPITAL primeiro, depois os doentes pela ordem do ficheiro).

    Parâmetros:
        matriz (DataFrame): matriz completa.
        ids_incluidos (list[str]): doentes a manter.

    Devolve:
        DataFrame: matriz quadrada (N+1) × (N+1).
    """
    ordem = ["HOSPITAL"] + list(ids_incluidos)
    return matriz.loc[ordem, ordem]


def verificar_matriz_quadrada(tempos_reais, tempos_livre, distancias, encaixe):
    """
    Verifica se a matriz quadrada está bem estabelecida.

    Parâmetros:
        tempos_reais, tempos_livre, distancias (DataFrame): matrizes quadradas.
        encaixe (DataFrame): encaixe de cada ponto na rede.

    Devolve:
        DataFrame: uma linha por verificação.
    """
    linhas = []

    def registar(nome, ok, valor, falha="AVISO"):
        """Acrescenta e mostra uma verificação (função interna)."""
        estado = "OK" if ok else falha
        linhas.append({"verificacao": nome, "resultado": estado, "valor": str(valor)})
        mensagem(f"   [{estado:^7}] {nome}: {valor}")

    t = tempos_reais.to_numpy()
    n = t.shape[0]
    registar("Matriz quadrada (nº linhas = nº colunas)", t.shape[0] == t.shape[1], f"{n} × {t.shape[1]}", "ERRO")
    registar("Mesma ordem nas linhas e nas colunas",
             list(tempos_reais.index) == list(tempos_reais.columns), "HOSPITAL + doentes", "ERRO")
    registar("Sem pares em falta (todas as rotas calculadas)", not np.isnan(t).any(),
             int(np.isnan(t).sum()), "ERRO")
    registar("Diagonal = 0", np.all(np.diag(t) == 0), f"{np.abs(np.diag(t)).max():.2f} min", "ERRO")
    registar("Tempos e distâncias fora da diagonal > 0",
             (tempos_livre.to_numpy()[~np.eye(n, dtype=bool)] > 0).all()
             and (distancias.to_numpy()[~np.eye(n, dtype=bool)] > 0).all(), "")
    violacoes, trios, excesso = contar_violacoes_triangulares(
        np.nan_to_num(tempos_livre.to_numpy(), nan=1e9), config.TOLERANCIA_TRIANGULAR_S / 60)
    registar("Desigualdade triangular (tempos)", violacoes == 0,
             f"{violacoes} violações em {trios} trios")
    assimetria = np.nanmax(np.abs(tempos_livre.to_numpy() - tempos_livre.to_numpy().T))
    registar("Assimetria máxima A→B vs B→A (não se assume simetria)", True, f"{assimetria:.2f} min")
    afastados = encaixe.loc[encaixe["distancia_ate_estrada_m"] > config.DISTANCIA_MAXIMA_ATE_ESTRADA_M, "ponto"]
    registar(f"Pontos a mais de {config.DISTANCIA_MAXIMA_ATE_ESTRADA_M} m da estrada", afastados.empty,
             ", ".join(afastados) if len(afastados) else 0)
    if config.FICHEIRO_TERRITORIO.exists():
        territorio = gpd.read_file(config.FICHEIRO_TERRITORIO).to_crs(config.CRS_PORTUGAL).geometry.iloc[0]
        pontos = gpd.GeoSeries(gpd.points_from_xy(encaixe["longitude_na_estrada"],
                                                  encaixe["latitude_na_estrada"]),
                               crs=config.CRS_WGS84).to_crs(config.CRS_PORTUGAL)
        fora = int((~pontos.within(territorio.buffer(100))).sum())
        registar("Pontos de encaixe na estrada fora de Portugal", fora == 0, fora, "ERRO")
    return pd.DataFrame(linhas)


def lista_de_pares(tempos_livre, tempos_reais, distancias):
    """
    Converte as matrizes quadradas numa lista "origem → destino".

    Parâmetros:
        tempos_livre, tempos_reais, distancias (DataFrame): matrizes quadradas.

    Devolve:
        DataFrame: uma linha por par (origem ≠ destino).
    """
    pares = distancias.stack(future_stack=True).rename("distancia_km").to_frame()
    pares["tempo_fluxo_livre_min"] = tempos_livre.stack(future_stack=True)
    pares["tempo_condicoes_reais_min"] = tempos_reais.stack(future_stack=True)
    pares.index.names = ["origem", "destino"]
    pares = pares.reset_index()
    return pares[pares["origem"] != pares["destino"]].round(3)


def criar_mapa(tabela, destino):
    """
    Mapa HTML com o hospital, os doentes (verde = incluído, laranja = excluído)
    e a isócrona de 30 min da Parte A.

    Parâmetros:
        tabela (DataFrame): tabela por doente.
        destino (Path): ficheiro HTML a criar.
    """
    mapa = folium.Map(location=[config.HOSPITAL_LATITUDE, config.HOSPITAL_LONGITUDE],
                      zoom_start=10, control_scale=True)
    if config.FICHEIRO_ISOCRONA.exists():
        folium.GeoJson(gpd.read_file(config.FICHEIRO_ISOCRONA), name="Isócrona 30 min (Valhalla, fluxo livre)",
                       style_function=lambda f: {"color": "#2c7fb8", "weight": 2, "fillOpacity": 0.05,
                                                 "dashArray": "6 4"}).add_to(mapa)
    folium.Marker([config.HOSPITAL_LATITUDE, config.HOSPITAL_LONGITUDE], tooltip="HOSPITAL",
                  popup=config.HOSPITAL_MORADA, icon=folium.Icon(color="red", icon="plus-sign")).add_to(mapa)
    for _, d in tabela.dropna(subset=["latitude", "longitude"]).iterrows():
        cor = "#1a9850" if d["dentro_dos_30min"] else "#d95f02"
        texto = (f"<b>{d['id_doente']}</b> — {d['estado']}<br>{d['endereco_pesquisado']}<br>"
                 f"<small>Encontrado: {d['endereco_encontrado']} [{d['precisao_geocodificacao']}]</small><br>"
                 f"Hospital → doente: {d['distancia_hospital_doente_km']} km; "
                 f"{d['tempo_hospital_doente_fluxo_livre_min']} min (fluxo livre), "
                 f"{d['tempo_hospital_doente_condicoes_reais_min']} min (condições reais)<br>"
                 f"Doente → hospital: {d['distancia_doente_hospital_km']} km; "
                 f"{d['tempo_doente_hospital_condicoes_reais_min']} min (condições reais)")
        icone = folium.DivIcon(html=f'<div style="background:{cor};color:white;border-radius:12px;'
                                    f'padding:2px 6px;font:bold 12px Arial;white-space:nowrap;'
                                    f'border:1px solid white;display:inline-block">{d["id_doente"]}</div>')
        folium.Marker([d["latitude"], d["longitude"]], icon=icone, tooltip=d["id_doente"],
                      popup=folium.Popup(texto, max_width=350)).add_to(mapa)
    folium.LayerControl().add_to(mapa)
    mapa.save(destino)


def exportar(pasta, tabela, quadradas, completas, pares, encaixe, verificacoes):
    """
    Grava todos os resultados (CSV, Excel e mapa).

    Parâmetros:
        pasta (Path): pasta de destino.
        tabela (DataFrame): tabela por doente.
        quadradas (dict): matrizes quadradas dos doentes incluídos.
        completas (dict): matrizes de todos os doentes geocodificados.
        pares, encaixe, verificacoes (DataFrame): restantes resultados.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    opcoes = {"encoding": "utf-8-sig", "sep": ";", "decimal": ","}
    colunas = ["id_doente", "morada", "codigo_postal", "localidade", "endereco_pesquisado",
               "endereco_encontrado",
               "precisao_geocodificacao", "fonte_coordenadas", "latitude", "longitude", "estado",
               "dentro_dos_30min", "distancia_hospital_doente_km", "tempo_hospital_doente_fluxo_livre_min",
               "tempo_hospital_doente_condicoes_reais_min", "distancia_doente_hospital_km",
               "tempo_doente_hospital_fluxo_livre_min", "tempo_doente_hospital_condicoes_reais_min",
               "distancia_ate_estrada_m"]
    tabela = tabela[colunas]
    tabela.to_csv(pasta / "tabela_doentes.csv", index=False, **opcoes)
    quadradas["distancias_km"].round(3).to_csv(pasta / "matriz_quadrada_distancias_km.csv", **opcoes)
    quadradas["tempos_condicoes_reais_min"].round(2).to_csv(
        pasta / "matriz_quadrada_tempos_condicoes_reais_min.csv", **opcoes)
    quadradas["tempos_fluxo_livre_min"].round(2).to_csv(
        pasta / "matriz_quadrada_tempos_fluxo_livre_min.csv", **opcoes)
    pares.to_csv(pasta / "lista_pares_origem_destino.csv", index=False, **opcoes)
    verificacoes.to_csv(pasta / "verificacoes.csv", index=False, encoding="utf-8-sig", sep=";")

    parametros = pd.DataFrame({
        "parametro": ["data_calculo", "hospital", "hospital_latitude", "hospital_longitude",
                      "limite_minutos", "regra", "routing", "rede_rodoviaria", "geocodificacao",
                      "fator_transito", "tempo_acesso_min", "leitura_das_matrizes"],
        "valor": [datetime.now().isoformat(timespec="seconds"), config.HOSPITAL_MORADA,
                  config.HOSPITAL_LATITUDE, config.HOSPITAL_LONGITUDE, config.LIMITE_TEMPO_MINUTOS,
                  "incluído se tempo hospital → doente em condições reais ≤ limite",
                  f"OSRM {config.OSRM_URL} (perfil {config.OSRM_PERFIL})", "OpenStreetMap",
                  f"Nominatim {config.GEOCODIFICACAO_URL}", config.CONDICOES_REAIS_FATOR_TRANSITO,
                  config.CONDICOES_REAIS_TEMPO_ACESSO_MIN,
                  "linha = ORIGEM, coluna = DESTINO; condições reais = fluxo livre × fator + acesso "
                  "(estimativa, não é trânsito medido)"]})
    with pd.ExcelWriter(pasta / "matrizes_doentes.xlsx") as excel:
        tabela.to_excel(excel, sheet_name="doentes", index=False)
        quadradas["distancias_km"].round(3).to_excel(excel, sheet_name="quadrada_km")
        quadradas["tempos_condicoes_reais_min"].round(2).to_excel(excel, sheet_name="quadrada_min_reais")
        quadradas["tempos_fluxo_livre_min"].round(2).to_excel(excel, sheet_name="quadrada_min_fluxo_livre")
        pares.to_excel(excel, sheet_name="lista_pares", index=False)
        completas["distancias_km"].round(3).to_excel(excel, sheet_name="todos_geocod_km")
        completas["tempos_condicoes_reais_min"].round(2).to_excel(excel, sheet_name="todos_geocod_min_reais")
        encaixe.to_excel(excel, sheet_name="encaixe_na_rede", index=False)
        verificacoes.to_excel(excel, sheet_name="verificacoes", index=False)
        parametros.to_excel(excel, sheet_name="parametros", index=False)
    criar_mapa(tabela, pasta / "mapa_doentes.html")


# ---------------------------------------------------------------------------
# Exemplo (doentes FICTÍCIOS em moradas de locais públicos)
# ---------------------------------------------------------------------------
def criar_exemplo():
    """
    Cria doentes/doentes_exemplo.csv com doentes FICTÍCIOS.

    As moradas são de locais públicos (praças, largos, serviços municipais) de
    Évora e concelhos vizinhos, para não usar moradas de pessoas reais.
    Inclui de propósito: um local a mais de 30 min (Estremoz), um junto ao
    limite (Montemor-o-Novo) e uma morada inexistente (para mostrar o erro).

    Devolve:
        Path: ficheiro criado.
    """
    exemplo = pd.DataFrame([
        ["D01", "Praça do Sertório", "7000-651", "Évora"],
        ["D02", "Largo dos Colegiais 2", "7000-803", "Évora"],
        ["D03", "Rua 5 de Outubro", "7000-854", "Évora"],
        ["D04", "Avenida Túlio Espanca", "7005-840", "Évora"],
        ["D05", "Praça do Município", "7040-027", "Arraiolos"],
        ["D06", "Praça da República", "7090-237", "Viana do Alentejo"],
        ["D07", "Largo da Igreja", "", "Nossa Senhora de Machede"],
        ["D08", "Praça da República", "7170-011", "Redondo"],
        ["D09", "Largo do Município", "7050-127", "Montemor-o-Novo"],
        ["D10", "Rossio Marquês de Pombal", "7100-513", "Estremoz"],
        ["D11", "Rua Inexistente 999", "", "Évora"],
    ], columns=["id_doente", "morada", "codigo_postal", "localidade"])
    PASTA_DOENTES.mkdir(exist_ok=True)
    exemplo.to_csv(FICHEIRO_EXEMPLO, index=False, sep=";", encoding="utf-8-sig")
    mensagem(f"   Exemplo criado: {FICHEIRO_EXEMPLO.relative_to(config.PASTA_PROJETO)}")
    return FICHEIRO_EXEMPLO


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------
def executar_matriz_doentes(caminho=FICHEIRO_EXEMPLO):
    """
    Executa a Parte B completa para um ficheiro de doentes.

    Parâmetros:
        caminho (Path): ficheiro CSV de doentes.

    Devolve:
        Path: pasta com os resultados.
    """
    caminho = Path(caminho)
    mensagem("=" * 70)
    mensagem(f"PARTE B — Doentes por morada: {caminho.name}")
    mensagem("=" * 70)
    if not caminho.exists():
        raise FileNotFoundError(f"Não encontrei o ficheiro {caminho}")

    # 1-3. Ler, geocodificar e validar
    doentes = ler_doentes(caminho)
    mensagem(f"   Doentes no ficheiro: {len(doentes)}")
    doentes = validar_doentes(geocodificar(doentes))
    validos = doentes[doentes["estado"] == ""]
    if validos.empty:
        raise ValueError("Nenhum doente com coordenadas válidas.")

    # 4-5. Matriz completa (todos os geocodificados) e condições reais
    tempos_livre, distancias, encaixe = calcular_matriz_osrm(validos)
    tempos_reais = aplicar_condicoes_reais(tempos_livre)
    mensagem(f"   Condições reais (estimativa): fluxo livre × {config.CONDICOES_REAIS_FATOR_TRANSITO} "
             f"+ {config.CONDICOES_REAIS_TEMPO_ACESSO_MIN} min de acesso")

    # 6. Tabela por doente e seleção
    tabela = tabela_por_doente(doentes, tempos_livre, tempos_reais, distancias, encaixe)
    incluidos = tabela.loc[tabela["dentro_dos_30min"], "id_doente"].tolist()
    mensagem(f"   Doentes a ≤ {config.LIMITE_TEMPO_MINUTOS} min (condições reais): {len(incluidos)} "
             f"de {len(tabela)}")
    if not incluidos:
        raise ValueError(f"Nenhum doente a ≤ {config.LIMITE_TEMPO_MINUTOS} min do hospital.")

    # 7. Matriz quadrada dos incluídos
    quadradas = {"distancias_km": matriz_quadrada(distancias, incluidos),
                 "tempos_fluxo_livre_min": matriz_quadrada(tempos_livre, incluidos),
                 "tempos_condicoes_reais_min": matriz_quadrada(tempos_reais, incluidos)}
    encaixe_incluidos = encaixe[encaixe["ponto"].isin(["HOSPITAL"] + incluidos)]
    verificacoes = verificar_matriz_quadrada(quadradas["tempos_condicoes_reais_min"],
                                             quadradas["tempos_fluxo_livre_min"],
                                             quadradas["distancias_km"], encaixe_incluidos)
    pares = lista_de_pares(quadradas["tempos_fluxo_livre_min"], quadradas["tempos_condicoes_reais_min"],
                           quadradas["distancias_km"])

    # 8. Exportar
    pasta = config.PASTA_PROJETO / "resultados" / "doentes" / caminho.stem
    completas = {"distancias_km": distancias, "tempos_condicoes_reais_min": tempos_reais}
    exportar(pasta, tabela, quadradas, completas, pares, encaixe, verificacoes)

    # Mostrar no ecrã
    mensagem("-" * 70)
    resumo = tabela[["id_doente", "estado", "distancia_hospital_doente_km",
                     "tempo_hospital_doente_fluxo_livre_min", "tempo_hospital_doente_condicoes_reais_min"]]
    resumo.columns = ["doente", "estado", "km", "min_livre", "min_reais"]
    for linha in resumo.to_string(index=False).splitlines():
        mensagem("   " + linha)
    mensagem("-" * 70)
    mensagem("   Matriz quadrada — tempos em condições reais (min), linha = origem, coluna = destino:")
    for linha in quadradas["tempos_condicoes_reais_min"].round(1).to_string().splitlines():
        mensagem("   " + linha)
    mensagem("-" * 70)
    mensagem(f"PARTE B concluída. Resultados em: {pasta.relative_to(config.PASTA_PROJETO)}/")
    return pasta


if __name__ == "__main__":
    leitor = argparse.ArgumentParser(description="Doentes por morada: tempos e matriz quadrada")
    leitor.add_argument("ficheiro", nargs="?", default=str(FICHEIRO_EXEMPLO),
                        help="CSV com id_doente;morada;codigo_postal;localidade (por omissão: o exemplo)")
    leitor.add_argument("--criar-exemplo", action="store_true", help="recria o ficheiro de exemplo")
    opcoes = leitor.parse_args()
    try:
        if opcoes.criar_exemplo or (Path(opcoes.ficheiro) == FICHEIRO_EXEMPLO and not FICHEIRO_EXEMPLO.exists()):
            criar_exemplo()
        executar_matriz_doentes(opcoes.ficheiro)
    except (FileNotFoundError, ValueError, RuntimeError) as erro:
        mensagem(f"ERRO: {erro}")
        sys.exit(1)
