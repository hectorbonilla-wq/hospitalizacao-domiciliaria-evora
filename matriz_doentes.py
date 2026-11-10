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
  4. CALCULAR com o OpenRouteService (ou OSRM, ver config.MOTOR_ROUTING), sobre
     a rede OpenStreetMap, os tempos e distâncias entre o
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
import unicodedata
from datetime import datetime
from pathlib import Path

import folium
from folium import plugins
import geopandas as gpd
import numpy as np
import pandas as pd
import requests

import config
from etapa_02_preparar_subseccoes import validar_coordenadas
from routing import descricao_motor, ler_chave_ors, nome_motor, obter_percurso, pedir_matriz
from etapa_04_verificar_consistencia import contar_violacoes_triangulares, distancia_linha_reta_km
from utilitarios import mensagem

PASTA_DOENTES = config.PASTA_PROJETO / "doentes"
FICHEIRO_EXEMPLO = PASTA_DOENTES / "doentes_exemplo.csv"
FICHEIRO_CACHE_GEOCODIFICACAO = PASTA_DOENTES / "cache_geocodificacao.csv"
# Máximo de doentes por ficheiro. Matrizes grandes são pedidas em blocos
# (ver calcular_matriz); 200 doentes = 201 × 201 = 40 401 percursos
# (12 pedidos ao OpenRouteService, que gastam quota diária).
MAXIMO_DOENTES_ORS = 200
MAXIMO_DOENTES_OSRM = 200

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
    maximo = MAXIMO_DOENTES_ORS if nome_motor() == "OpenRouteService" else MAXIMO_DOENTES_OSRM
    if len(doentes) > maximo:
        raise ValueError(f"O ficheiro tem {len(doentes)} doentes; o máximo é {maximo}. Divida o ficheiro.")

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
    Pergunta ao Nominatim (OpenStreetMap) as coordenadas de uma morada (só Portugal).

    Parâmetros:
        texto (str): morada a pesquisar.

    Devolve:
        dict ou None: latitude, longitude, endereco_encontrado, tipo, codigo_postal.
    """
    parametros = {"q": texto, "format": "jsonv2", "countrycodes": "pt", "limit": 1, "addressdetails": 1}
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
            tipo = r.get("addresstype") or r.get("type", "")
            return {"latitude": float(r["lat"]), "longitude": float(r["lon"]),
                    "endereco_encontrado": r.get("display_name", ""),
                    "precisao": PRECISAO_POR_TIPO.get(tipo, "desconhecida"),
                    "codigo_postal": (r.get("address") or {}).get("postcode", "")}
        except (requests.RequestException, ValueError) as erro:
            mensagem(f"      ERRO no Nominatim ({tentativa}/3): {erro}")
            time.sleep(2 ** tentativa)
    return None


# Precisão a partir da "camada" (layer) devolvida pelo geocodificador do OpenRouteService
PRECISAO_POR_CAMADA_ORS = {
    "address": "número de porta", "venue": "edifício/equipamento", "street": "rua",
    "postalcode": "código postal", "neighbourhood": "bairro", "borough": "bairro",
    "locality": "localidade", "localadmin": "localidade", "county": "concelho",
    "macrocounty": "concelho", "region": "concelho",
}


def pesquisar_ors(texto):
    """
    Pergunta ao geocodificador do OpenRouteService (Pelias, dados OpenStreetMap
    e outros abertos) as coordenadas de uma morada, só em Portugal.

    Parâmetros:
        texto (str): morada a pesquisar.

    Devolve:
        dict ou None: latitude, longitude, endereco_encontrado, precisao, codigo_postal.
    """
    chave = ler_chave_ors()
    if not chave:
        return None
    parametros = {"text": texto, "boundary.country": "PRT", "size": 1}
    for tentativa in range(1, 4):
        try:
            resposta = requests.get(f"{config.ORS_URL}/geocode/search", params=parametros,
                                    headers={"Authorization": chave}, timeout=30)
            time.sleep(1.0)
            resposta.raise_for_status()
            resultados = resposta.json().get("features", [])
            if not resultados:
                return None
            r = resultados[0]
            propriedades = r["properties"]
            lon, lat = r["geometry"]["coordinates"]
            return {"latitude": float(lat), "longitude": float(lon),
                    "endereco_encontrado": propriedades.get("label", ""),
                    "precisao": PRECISAO_POR_CAMADA_ORS.get(propriedades.get("layer", ""), "desconhecida"),
                    "codigo_postal": propriedades.get("postalcode", "")}
        except (requests.RequestException, ValueError, KeyError) as erro:
            mensagem(f"      ERRO no geocodificador do OpenRouteService ({tentativa}/3): {erro}")
            time.sleep(2 ** tentativa)
    return None


def pesquisar_com_cache(servico, texto, cache, novos):
    """
    Pesquisa uma morada num serviço, reutilizando resultados anteriores (cache).

    Parâmetros:
        servico (str): "ors" ou "nominatim".
        texto (str): morada.
        cache (dict): resultados anteriores {chave: dict}.
        novos (list): lista onde se acrescentam os resultados novos (para gravar).

    Devolve:
        dict ou None: resultado da pesquisa.
    """
    chave = f"{servico}|{texto}"
    if chave in cache:
        c = cache[chave]
        if c.get("latitude", "") in ("", None) or pd.isna(c.get("latitude")):
            return None
        return {"latitude": float(c["latitude"]), "longitude": float(c["longitude"]),
                "endereco_encontrado": c.get("endereco_encontrado", ""), "precisao": c.get("precisao", ""),
                "codigo_postal": "" if pd.isna(c.get("codigo_postal", "")) else str(c.get("codigo_postal", ""))}
    resultado = pesquisar_ors(texto) if servico == "ors" else pesquisar_nominatim(texto)
    registo = {"pesquisa": chave, "latitude": "", "longitude": "", "endereco_encontrado": "",
               "precisao": "", "codigo_postal": "", "data": datetime.now().isoformat(timespec="seconds")}
    if resultado:
        registo.update({k: str(v) for k, v in resultado.items()})
    cache[chave] = registo
    novos.append(registo)
    return resultado


def geocodificar(doentes):
    """
    Converte a morada de cada doente em coordenadas, com DOIS serviços
    independentes, para se poder confirmar o resultado:

      1. geocodificador do OpenRouteService (principal, se houver chave);
      2. Nominatim/OpenStreetMap (confirmação; principal se não houver chave).

    Para cada serviço tenta-se a morada completa e, se falhar, só "código
    postal + localidade" (precisão "código postal").

    Parâmetros:
        doentes (DataFrame): resultado de ler_doentes().

    Devolve:
        DataFrame: com latitude, longitude, endereço encontrado, precisão,
        fonte, coordenadas do 2.º serviço e distância entre os dois (m).
    """
    cache = {}
    if FICHEIRO_CACHE_GEOCODIFICACAO.exists():
        tabela_cache = pd.read_csv(FICHEIRO_CACHE_GEOCODIFICACAO, sep=";", dtype=str, keep_default_na=False)
        if "precisao" in tabela_cache.columns:   # formato atual
            cache = {l["pesquisa"]: l.to_dict() for _, l in tabela_cache.iterrows()}

    servicos = ["ors", "nominatim"] if ler_chave_ors() else ["nominatim"]
    nomes = {"ors": "OpenRouteService", "nominatim": "Nominatim/OpenStreetMap"}
    doentes = doentes.copy()
    doentes["endereco_pesquisado"] = doentes.apply(texto_da_morada, axis=1)
    for coluna in ["endereco_encontrado", "precisao_geocodificacao", "fonte_coordenadas",
                   "codigo_postal_encontrado", "latitude_confirmacao", "longitude_confirmacao",
                   "diferenca_entre_servicos_m"]:
        doentes[coluna] = np.nan if coluna in ("latitude_confirmacao", "longitude_confirmacao",
                                               "diferenca_entre_servicos_m") else ""

    a_pesquisar = doentes["latitude"].isna() | doentes["longitude"].isna()
    if a_pesquisar.any():
        mensagem(f"   A geocodificar {int(a_pesquisar.sum())} moradas com: "
                 f"{' + '.join(nomes[s] for s in servicos)} "
                 "(as moradas são enviadas a estes serviços — ver PRIVACIDADE)")
    doentes.loc[~a_pesquisar, "fonte_coordenadas"] = "coordenadas indicadas no ficheiro"
    doentes.loc[~a_pesquisar, "precisao_geocodificacao"] = "indicada pelo utilizador"

    novos = []
    candidatos_por_doente = {}
    for indice in doentes.index[a_pesquisar]:
        linha = doentes.loc[indice]
        textos = [(linha["endereco_pesquisado"], "morada completa")]
        alternativa = " ".join(p for p in [linha["codigo_postal"], linha["localidade"]] if p)
        if alternativa and alternativa != linha["endereco_pesquisado"]:
            textos.append((alternativa, "só código postal e localidade"))

        resultados = {}
        for servico in servicos:
            for texto, como in textos:
                if not texto:
                    continue
                encontrado = pesquisar_com_cache(servico, texto, cache, novos)
                if encontrado:
                    if como != "morada completa" and encontrado["precisao"] not in PRECISAO_INSUFICIENTE:
                        encontrado["precisao"] = "código postal"
                    encontrado["como"] = como
                    resultados[servico] = encontrado
                    break

        if not resultados:
            doentes.loc[indice, "precisao_geocodificacao"] = "morada não encontrada"
            mensagem(f"   NÃO ENCONTRADA {linha['id_doente']}: {linha['endereco_pesquisado']}")
            continue

        # Guardam-se TODOS os candidatos; a escolha é feita em verificar_moradas(),
        # que confirma qual deles fica no concelho/freguesia e código postal indicados.
        candidatos = []
        for servico, r in resultados.items():
            r = dict(r)
            r["servico"] = nomes[servico]
            candidatos.append(r)
        candidatos_por_doente[linha["id_doente"]] = candidatos

    if novos:
        PASTA_DOENTES.mkdir(exist_ok=True)
        pd.DataFrame(list(cache.values())).to_csv(FICHEIRO_CACHE_GEOCODIFICACAO, sep=";",
                                                  index=False, encoding="utf-8-sig")
    doentes["candidatos"] = [candidatos_por_doente.get(i, []) for i in doentes["id_doente"]]
    return doentes


def normalizar(texto):
    """
    Põe um texto em minúsculas e sem acentos, para comparar nomes de lugares
    (ex.: "Évora" e "EVORA" ficam iguais).

    Parâmetros:
        texto (str): texto original.

    Devolve:
        str: texto normalizado.
    """
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(texto.lower().replace("-", " ").split())


def localizar_na_bgri(latitude, longitude, subseccoes):
    """
    Indica em que subsecção, freguesia e concelho (BGRI 2021) cai um ponto.

    Parâmetros:
        latitude, longitude (float): coordenadas.
        subseccoes (GeoDataFrame): subsecções da área de estudo (WGS84).

    Devolve:
        dict: id_subseccao, freguesia, municipio ("" se o ponto não cair em nenhuma).
    """
    from shapely.geometry import Point
    ponto = Point(longitude, latitude)
    candidatas = subseccoes.iloc[list(subseccoes.sindex.query(ponto, predicate="within"))]
    if candidatas.empty:
        return {"id_subseccao": "", "freguesia": "", "municipio": ""}
    linha = candidatas.iloc[0]
    return {"id_subseccao": linha["id_subseccao"], "freguesia": linha["freguesia"],
            "municipio": linha["municipio"]}


def avaliar_candidato(linha, candidato, subseccoes):
    """
    Avalia se um resultado de geocodificação corresponde à morada indicada.

    Parâmetros:
        linha (pandas.Series): dados do doente (localidade, código postal).
        candidato (dict): resultado de um serviço (latitude, longitude, precisão...).
        subseccoes (GeoDataFrame): subsecções da BGRI.

    Devolve:
        dict: o candidato com bgri (dict), problemas (list[str]) e pontuação.
    """
    bgri = localizar_na_bgri(candidato["latitude"], candidato["longitude"], subseccoes)
    problemas = []
    localidade_ok = True
    localidade = normalizar(linha["localidade"])
    if bgri["municipio"] == "":
        problemas.append("ponto fora da área de estudo da BGRI")
        localidade_ok = False
    elif (localidade and localidade not in normalizar(f"{bgri['municipio']} {bgri['freguesia']}")
          and not (linha.get("concelho") and normalizar(linha["concelho"]) == normalizar(bgri["municipio"]))):
        # (se o ficheiro tiver a coluna opcional "concelho", basta o concelho coincidir:
        #  aldeias como "Valverde" não são nomes de freguesia)
        problemas.append(f"localidade '{linha['localidade']}' não coincide com "
                         f"{bgri['freguesia']} ({bgri['municipio']})")
        localidade_ok = False
    cp_indicado = str(linha["codigo_postal"])[:4]
    cp_encontrado = str(candidato.get("codigo_postal") or "")[:4]
    cp_ok = not (len(cp_indicado) == 4 and len(cp_encontrado) == 4 and cp_indicado != cp_encontrado)
    if not cp_ok:
        problemas.append(f"código postal {linha['codigo_postal']} ≠ encontrado {candidato['codigo_postal']}")
    if candidato["precisao"] in PRECISAO_INSUFICIENTE:
        problemas.append("só foi encontrada a localidade")
    ordem = ["número de porta", "edifício/equipamento", "edifício", "rua", "rua/praça",
             "código postal", "bairro", "desconhecida", "localidade", "concelho"]
    rank = ordem.index(candidato["precisao"]) if candidato["precisao"] in ordem else 99
    # Pontuação: primeiro a localidade certa, depois o código postal, depois a precisão
    return dict(candidato, bgri=bgri, problemas=problemas,
                pontuacao=(not localidade_ok, not cp_ok, rank))


def verificar_moradas(doentes):
    """
    REVISÃO DAS MORADAS: para cada doente, escolhe e confirma as coordenadas.

    Cada morada foi procurada em dois serviços (OpenRouteService e Nominatim).
    Para cada resultado verifica-se:
      1. CONCELHO/FREGUESIA: o ponto é colocado na subsecção da BGRI 2021 que o
         contém; a LOCALIDADE do ficheiro tem de corresponder ao nome do
         concelho ou da freguesia (há ruas com o mesmo nome em muitas terras!);
      2. CÓDIGO POSTAL: os 4 primeiros dígitos (CP4) têm de coincidir com os do
         código postal devolvido, quando o serviço o devolve;
      3. PRECISÃO: pelo menos rua ou código postal.
    Fica o resultado que passa mais verificações (em empate, o mais preciso).
    Se os dois serviços passarem, mede-se a distância entre eles (confirmação).

    Parâmetros:
        doentes (DataFrame): resultado de geocodificar().

    Devolve:
        DataFrame: com coordenadas escolhidas, concelho_bgri, freguesia_bgri,
        subseccao_bgri, verificacao_morada e morada_confirmada.
    """
    doentes = doentes.copy()
    for coluna in ["concelho_bgri", "freguesia_bgri", "subseccao_bgri", "verificacao_morada"]:
        doentes[coluna] = ""
    doentes["morada_confirmada"] = False
    if not config.FICHEIRO_SUBSECCOES.exists():
        mensagem("   (Sem BGRI preparada: execute a Parte A para verificar concelho/freguesia.)")
        return doentes
    subseccoes = gpd.read_file(config.FICHEIRO_SUBSECCOES,
                               columns=["id_subseccao", "municipio", "freguesia"]).to_crs(config.CRS_WGS84)
    nomes = {"OpenRouteService": "ORS", "Nominatim/OpenStreetMap": "Nominatim"}

    for indice, linha in doentes.iterrows():
        candidatos = linha.get("candidatos") or []
        if not candidatos:
            # Coordenadas indicadas no ficheiro (ou morada não encontrada)
            if pd.notna(linha["latitude"]) and pd.notna(linha["longitude"]):
                candidatos = [{"latitude": linha["latitude"], "longitude": linha["longitude"],
                               "precisao": linha["precisao_geocodificacao"], "codigo_postal": "",
                               "endereco_encontrado": "", "servico": "ficheiro", "como": "coordenadas"}]
            else:
                continue
        avaliados = sorted((avaliar_candidato(linha, c, subseccoes) for c in candidatos),
                           key=lambda c: c["pontuacao"])
        escolhido = avaliados[0]
        problemas = list(escolhido["problemas"])
        doentes.loc[indice, ["latitude", "longitude"]] = [escolhido["latitude"], escolhido["longitude"]]
        doentes.loc[indice, "endereco_encontrado"] = escolhido["endereco_encontrado"]
        doentes.loc[indice, "precisao_geocodificacao"] = escolhido["precisao"]
        doentes.loc[indice, "codigo_postal_encontrado"] = escolhido.get("codigo_postal", "")
        if escolhido["servico"] != "ficheiro":
            doentes.loc[indice, "fonte_coordenadas"] = f"{escolhido['servico']} ({escolhido['como']})"
        doentes.loc[indice, ["concelho_bgri", "freguesia_bgri", "subseccao_bgri"]] = [
            escolhido["bgri"]["municipio"], escolhido["bgri"]["freguesia"], escolhido["bgri"]["id_subseccao"]]

        notas = []
        for outro in avaliados[1:]:
            distancia = 1000 * distancia_linha_reta_km(escolhido["latitude"], escolhido["longitude"],
                                                       outro["latitude"], outro["longitude"])
            doentes.loc[indice, ["latitude_confirmacao", "longitude_confirmacao"]] = [outro["latitude"],
                                                                                      outro["longitude"]]
            doentes.loc[indice, "diferenca_entre_servicos_m"] = round(distancia)
            if outro["precisao"] in PRECISAO_INSUFICIENTE and distancia > config.GEOCODIFICACAO_DISTANCIA_MAX_CENTRO_M:
                # O outro serviço só encontrou o CENTRO da localidade: se o ponto escolhido
                # fica longe desse centro, pode ser uma rua com o mesmo nome noutra terra
                # do mesmo concelho (ex.: Praça da República de Alcáçovas vs. Viana do Alentejo).
                problemas.append(f"fica a {distancia / 1000:.1f} km do centro de '{linha['localidade']}' "
                                 "— confirme se é a localidade certa")
            elif outro["problemas"]:
                notas.append(f"{nomes.get(outro['servico'], outro['servico'])} rejeitado "
                             f"({outro['problemas'][0]})")
            elif distancia > config.GEOCODIFICACAO_DIFERENCA_MAXIMA_M:
                problemas.append(f"os dois serviços diferem {distancia:.0f} m — confirme o número de porta")

        doentes.loc[indice, "verificacao_morada"] = ("OK" if not problemas else "; ".join(problemas)) + (
            f" | {'; '.join(notas)}" if notas else "")
        doentes.loc[indice, "morada_confirmada"] = not problemas
        origem = nomes.get(escolhido["servico"], escolhido["servico"])
        if problemas:
            mensagem(f"   VERIFICAR {linha['id_doente']}: {'; '.join(problemas)}")
        else:
            mensagem(f"   OK {linha['id_doente']}: {escolhido['bgri']['freguesia']} "
                     f"({escolhido['bgri']['municipio']}) [{escolhido['precisao']}, {origem}]"
                     + (f" — {'; '.join(notas)}" if notas else ""))
    return doentes.drop(columns=["candidatos"], errors="ignore")


def validar_doentes(doentes):
    """
    Decide que doentes entram no cálculo. São EXCLUÍDOS (com o motivo):
      * morada não encontrada;
      * só a localidade foi encontrada (precisão insuficiente);
      * coordenadas inválidas ou fora de Portugal / da área de estudo;
      * localidade que não coincide com o concelho/freguesia onde o ponto caiu
        (sinal forte de que o geocodificador encontrou outro lugar).
    Os outros avisos (código postal, diferença entre serviços) ficam na coluna
    "verificacao_morada" para o utilizador confirmar, mas não excluem.

    Parâmetros:
        doentes (DataFrame): resultado de verificar_moradas().

    Devolve:
        DataFrame: o mesmo, com a coluna "estado" ("" = entra no cálculo).
    """
    doentes = doentes.copy()
    doentes["estado"] = ""
    nao_encontrada = doentes["precisao_geocodificacao"] == "morada não encontrada"
    doentes.loc[nao_encontrada, "estado"] = "morada não encontrada"
    insuficiente = doentes["precisao_geocodificacao"].isin(PRECISAO_INSUFICIENTE)
    doentes.loc[insuficiente, "estado"] = ("morada não localizada com precisão (só a localidade) — "
                                           "corrija a morada ou indique latitude/longitude")
    plausivel = np.array([validar_coordenadas(la, lo) for la, lo in
                          zip(doentes["latitude"], doentes["longitude"])])
    doentes.loc[~plausivel & (doentes["estado"] == ""), "estado"] = "coordenadas inválidas"
    fora = (doentes["concelho_bgri"] == "") & (doentes["estado"] == "")
    doentes.loc[fora, "estado"] = "fora da área de estudo / de Portugal"
    # Só conta o resultado ESCOLHIDO (o texto depois de " | " descreve o candidato rejeitado)
    problemas_escolhido = doentes["verificacao_morada"].str.split(" | ", regex=False).str[0]
    coordenadas_do_ficheiro = doentes["fonte_coordenadas"].str.startswith("coordenadas indicadas", na=False)
    outro_lugar = (problemas_escolhido.str.contains("não coincide", na=False) & (doentes["estado"] == "")
                   & ~coordenadas_do_ficheiro)   # com GPS indicado, é só um aviso
    doentes.loc[outro_lugar, "estado"] = ("localizado noutro concelho/freguesia — confirme a morada "
                                          "ou indique latitude/longitude")
    for _, linha in doentes[doentes["estado"] != ""].iterrows():
        mensagem(f"   EXCLUÍDO {linha['id_doente']}: {linha['estado']}")
    return doentes


def calcular_matriz(doentes):
    """
    Pede ao motor de routing (OpenRouteService ou OSRM, rede OpenStreetMap) a
    matriz completa (hospital + doentes, todos para todos).

    Se a matriz for grande demais para um só pedido (OpenRouteService: até
    3500 percursos por pedido), é pedida em BLOCOS DE LINHAS (grupos de
    origens para todos os destinos) e os blocos são juntados no fim.

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
    n = len(etiquetas)
    maximo_percursos = 3500 if nome_motor() == "OpenRouteService" else 10000
    linhas_por_pedido = max(1, maximo_percursos // n)
    blocos = [list(range(i, min(i + linhas_por_pedido, n))) for i in range(0, n, linhas_por_pedido)]
    mensagem(f"   A pedir ao {nome_motor()} a matriz {n} × {n} (rede OpenStreetMap) "
             f"em {len(blocos)} pedido(s)...")

    duracoes, distancias_m, origens = [], [], []
    for bloco in blocos:
        resposta = pedir_matriz(coordenadas, sources=bloco if len(blocos) > 1 else None)
        duracoes += resposta["durations"]
        distancias_m += resposta["distances"]
        origens += resposta["sources"]
    tempos = pd.DataFrame(duracoes, index=etiquetas, columns=etiquetas, dtype=float) / 60
    distancias = pd.DataFrame(distancias_m, index=etiquetas, columns=etiquetas, dtype=float) / 1000
    encaixe = pd.DataFrame({
        "ponto": etiquetas,
        "distancia_ate_estrada_m": [round(p.get("distance") or 0, 1) for p in origens],
        "rua_mais_proxima": [p.get("name", "") for p in origens],
        "longitude_na_estrada": [(p.get("location") or [None, None])[0] for p in origens],
        "latitude_na_estrada": [(p.get("location") or [None, None])[1] for p in origens],
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
    # Desigualdade triangular: ir de A a C diretamente não deve demorar mais do
    # que ir de A a C passando por B. Testa-se primeiro a matriz usada no
    # planeamento (condições reais, que inclui o tempo de paragem em B).
    violacoes, trios, excesso = contar_violacoes_triangulares(
        np.nan_to_num(t, nan=1e9), config.TOLERANCIA_TRIANGULAR_S / 60)
    registar("Desigualdade triangular (tempos em condições reais)", violacoes == 0,
             f"{violacoes} violações em {trios} trios (maior excesso {excesso:.2f} min)")
    violacoes_l, _, excesso_l = contar_violacoes_triangulares(
        np.nan_to_num(tempos_livre.to_numpy(), nan=1e9), config.TOLERANCIA_TRIANGULAR_S / 60)
    linhas.append({"verificacao": "Desigualdade triangular (tempos sem trânsito)",
                   "resultado": "OK" if violacoes_l == 0 else "INFO",
                   "valor": f"{violacoes_l} violações em {trios} trios (maior excesso {excesso_l:.2f} min)"
                            + ("" if violacoes_l == 0 else
                               " — normal entre pontos muito próximos: num ponto de paragem pode-se "
                               "inverter a marcha, o que não é permitido a meio de uma rua; na "
                               "matriz em condições reais o tempo de paragem anula este efeito")})
    mensagem(f"   [{linhas[-1]['resultado']:^7}] {linhas[-1]['verificacao']}: {linhas[-1]['valor'][:90]}")
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


def icone_doente(id_doente, minutos, cor):
    """
    Cria o símbolo de um doente: um ponto colorido com a etiqueta "E01 · 7 min".
    O ponto fica exatamente nas coordenadas do doente.

    Parâmetros:
        id_doente (str): identificador.
        minutos (float): tempo hospital → doente (condições reais).
        cor (str): cor (verde = incluído, laranja = excluído).

    Devolve:
        folium.DivIcon: símbolo para usar num folium.Marker.
    """
    html = (f'<div style="display:flex;align-items:center;white-space:nowrap;">'
            f'<span style="width:12px;height:12px;border-radius:50%;background:{cor};'
            f'border:2px solid white;box-shadow:0 0 2px #333;"></span>'
            f'<span style="margin-left:3px;background:{cor};color:white;border-radius:3px;'
            f'padding:0 4px;font:bold 11px Arial;box-shadow:0 1px 2px rgba(0,0,0,.4);">'
            f'{id_doente} · {minutos:.0f} min</span></div>')
    return folium.DivIcon(html=html, icon_size=(110, 16), icon_anchor=(8, 8))


def criar_mapa(tabela, destino, desenhar_percursos=True):
    """
    Mapa HTML (fundo OpenStreetMap) com o hospital, os doentes e os percursos.

      * verde   = doente incluído (≤ 30 min), com o percurso real desde o hospital;
      * laranja = doente excluído por estar a mais de 30 min;
      * doentes muito próximos uns dos outros aparecem AGRUPADOS num círculo
        com o número de doentes; clique no círculo (ou aproxime) para os ver;
      * os doentes sem localização fiável NÃO são desenhados (seria enganador)
        e ficam listados na caixa do canto inferior esquerdo;
      * a caixa inclui uma tabela com km e minutos de todos os doentes.

    Parâmetros:
        tabela (DataFrame): tabela por doente.
        destino (Path): ficheiro HTML a criar.
    """
    mapa = folium.Map(location=[config.HOSPITAL_LATITUDE, config.HOSPITAL_LONGITUDE],
                      zoom_start=11, control_scale=True, tiles=None)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(mapa)

    if config.FICHEIRO_ISOCRONA.exists():
        isocrona = gpd.read_file(config.FICHEIRO_ISOCRONA)
        servico_iso = isocrona["motor"].iloc[0] if "motor" in isocrona.columns else "isócrona"
        folium.GeoJson(isocrona,
                       name=f"Isócrona {config.LIMITE_TEMPO_MINUTOS} min ({servico_iso}, sem trânsito)",
                       style_function=lambda f: {"color": "#2c7fb8", "weight": 1.5, "opacity": 0.8,
                                                 "fillColor": "#2c7fb8", "fillOpacity": 0.10},
                       tooltip=f"Isócrona de {config.LIMITE_TEMPO_MINUTOS} min (referência)").add_to(mapa)

    desenhados = tabela[tabela["tempo_hospital_doente_fluxo_livre_min"].notna()]
    nao_desenhados = tabela[tabela["tempo_hospital_doente_fluxo_livre_min"].isna()]
    hospital = (config.HOSPITAL_LATITUDE, config.HOSPITAL_LONGITUDE)

    camada_percursos = folium.FeatureGroup(name=f"Percursos hospital → doente ({nome_motor()}/OSM)").add_to(mapa)
    # Agrupamento automático: deixa de agrupar a partir do zoom 16 (ruas visíveis)
    grupo_doentes = plugins.MarkerCluster(name="Doentes", options={
        "disableClusteringAtZoom": 16, "maxClusterRadius": 35, "spiderfyOnMaxZoom": True}).add_to(mapa)

    for _, d in desenhados.iterrows():
        incluido = bool(d["dentro_dos_30min"])
        cor = "#1a9850" if incluido else "#d95f02"
        texto = (f"<b>{d['id_doente']}</b> — {d['estado']}<br>{d['endereco_pesquisado']}<br>"
                 f"<small>Localizado em: {d['endereco_encontrado']}<br>"
                 f"Precisão: {d['precisao_geocodificacao']} · {d['fonte_coordenadas']}<br>"
                 f"BGRI: {d['freguesia_bgri']} ({d['concelho_bgri']})<br>"
                 f"Verificação da morada: <b>{d['verificacao_morada']}</b></small><br><br>"
                 f"<b>Hospital → doente:</b> {d['distancia_hospital_doente_km']} km · "
                 f"{d['tempo_hospital_doente_condicoes_reais_min']} min (condições reais) · "
                 f"{d['tempo_hospital_doente_fluxo_livre_min']} min (sem trânsito)<br>"
                 f"<b>Doente → hospital:</b> {d['distancia_doente_hospital_km']} km · "
                 f"{d['tempo_doente_hospital_condicoes_reais_min']} min (condições reais) · "
                 f"{d['tempo_doente_hospital_fluxo_livre_min']} min (sem trânsito)")
        if incluido and desenhar_percursos:
            percurso = obter_percurso(hospital, (d["latitude"], d["longitude"]))
            if percurso:
                folium.PolyLine(percurso, color=cor, weight=3, opacity=0.55,
                                tooltip=f"Hospital → {d['id_doente']}: "
                                        f"{d['tempo_hospital_doente_condicoes_reais_min']} min").add_to(camada_percursos)
        folium.Marker([d["latitude"], d["longitude"]],
                      icon=icone_doente(d["id_doente"], d["tempo_hospital_doente_condicoes_reais_min"], cor),
                      tooltip=f"{d['id_doente']}: {d['endereco_pesquisado']}",
                      popup=folium.Popup(texto, max_width=380)).add_to(grupo_doentes)

    folium.Marker(hospital, tooltip="Hospital do Espírito Santo de Évora", z_index_offset=-1000,
                  popup=folium.Popup(f"<b>{config.HOSPITAL_NOME}</b><br>{config.HOSPITAL_MORADA}", max_width=300),
                  icon=folium.DivIcon(icon_size=(22, 22), icon_anchor=(11, 11),
                                      html='<div style="width:22px;height:22px;border-radius:4px;'
                                           'background:#c0392b;color:white;font:bold 15px Arial;'
                                           'text-align:center;line-height:22px;border:2px solid white;'
                                           'box-shadow:0 0 3px #333;">H</div>')).add_to(mapa)

    # Caixa: legenda + tabela de km/minutos + doentes não representados
    linhas = "".join(
        f"<tr><td style='color:{'#1a9850' if d['dentro_dos_30min'] else '#d95f02'};font-weight:bold'>"
        f"{d['id_doente']}</td><td align='right'>{d['distancia_hospital_doente_km']:.1f}</td>"
        f"<td align='right'>{d['tempo_hospital_doente_condicoes_reais_min']:.1f}</td>"
        f"<td align='right'>{d['tempo_doente_hospital_condicoes_reais_min']:.1f}</td></tr>"
        for _, d in desenhados.iterrows())
    lista = "".join(f"<li>{d['id_doente']}: {d['estado']}</li>" for _, d in nao_desenhados.iterrows())
    caixa_nao = (f"<b>Não representados:</b><ul style='margin:2px 0 0 16px;padding:0'>{lista}</ul>"
                 if lista else "")
    legenda = f"""
    <div style="position:fixed;bottom:40px;left:10px;z-index:9999;background:rgba(255,255,255,0.95);
                padding:8px 10px;border:1px solid #999;border-radius:6px;font:12px Arial;
                max-width:300px;max-height:55%;overflow:auto;">
      <b>Doentes — Hospitalização Domiciliária (HESE)</b><br>
      <span style="background:#c0392b;color:white;padding:0 4px;border-radius:3px;font-weight:bold">H</span> Hospital
      &nbsp; <span style="color:#1a9850;font-size:15px">&#9679;</span> ≤ {config.LIMITE_TEMPO_MINUTOS} min
      &nbsp; <span style="color:#d95f02;font-size:15px">&#9679;</span> &gt; {config.LIMITE_TEMPO_MINUTOS} min<br>
      <span style="color:#1a9850">&#9473;&#9473;</span> percurso real (rede OpenStreetMap)<br>
      <small>Círculo com número = doentes próximos agrupados (clique para abrir).</small>
      <table style="border-collapse:collapse;margin-top:4px;font-size:11px;width:100%">
        <tr style="border-bottom:1px solid #ccc"><th align="left">Doente</th><th>km</th>
            <th>H→D min</th><th>D→H min</th></tr>{linhas}
      </table>
      <small>Minutos em condições reais estimadas (fluxo livre × {config.CONDICOES_REAIS_FATOR_TRANSITO}
      + {config.CONDICOES_REAIS_TEMPO_ACESSO_MIN} min).</small><br>{caixa_nao}
    </div>"""
    mapa.get_root().html.add_child(folium.Element(legenda))

    # Enquadrar: hospital + doentes desenhados; margem maior à esquerda (caixa)
    pontos = [list(hospital)] + desenhados[["latitude", "longitude"]].values.tolist()
    mapa.fit_bounds(pontos, padding_top_left=(320, 40), padding_bottom_right=(40, 40))
    folium.LayerControl(collapsed=False).add_to(mapa)
    mapa.save(destino)


def exportar(pasta, tabela, quadradas, completas, pares, encaixe, verificacoes, desenhar_percursos=True):
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
               "endereco_encontrado", "codigo_postal_encontrado", "concelho_bgri", "freguesia_bgri",
               "subseccao_bgri", "verificacao_morada", "morada_confirmada",
               "latitude_confirmacao", "longitude_confirmacao", "diferenca_entre_servicos_m",
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
                  descricao_motor(), "OpenStreetMap",
                  ("OpenRouteService geocode + Nominatim (confirmação)" if ler_chave_ors()
                   else f"Nominatim {config.GEOCODIFICACAO_URL}"), config.CONDICOES_REAIS_FATOR_TRANSITO,
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
    criar_mapa(tabela, pasta / "mapa_doentes.html", desenhar_percursos)


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
def executar_matriz_doentes(caminho=FICHEIRO_EXEMPLO, pasta_resultados=None, matriz_pre_calculada=None,
                            desenhar_percursos=None):
    """
    Executa a Parte B completa para um ficheiro de doentes.

    Parâmetros:
        caminho (Path): ficheiro CSV de doentes.
        pasta_resultados (Path ou None): onde gravar os resultados; por omissão
            resultados/doentes/<nome_do_ficheiro>/.
        matriz_pre_calculada (tuple ou None): (tempos, distancias, encaixe) já
            calculados para um conjunto MAIOR que inclua estes doentes (com os
            mesmos id_doente e coordenadas). Evita repetir pedidos ao routing:
            a matriz destes doentes é extraída dessa matriz maior.
        desenhar_percursos (bool ou None): desenhar no mapa o percurso de cada
            doente (1 pedido por doente). None = só se houver até 20 doentes.

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
    doentes = validar_doentes(verificar_moradas(geocodificar(doentes)))
    validos = doentes[doentes["estado"] == ""]
    if validos.empty:
        raise ValueError("Nenhum doente com coordenadas válidas.")

    # 4-5. Matriz completa (todos os geocodificados) e condições reais
    if matriz_pre_calculada is not None:
        ordem = ["HOSPITAL"] + validos["id_doente"].tolist()
        tempos_todos, distancias_todas, encaixe_todos = matriz_pre_calculada
        tempos_livre = tempos_todos.loc[ordem, ordem]
        distancias = distancias_todas.loc[ordem, ordem]
        encaixe = encaixe_todos.set_index("ponto").loc[ordem].reset_index()
        mensagem(f"   Matriz {len(ordem)} × {len(ordem)} extraída da matriz já calculada (sem novos pedidos).")
    else:
        tempos_livre, distancias, encaixe = calcular_matriz(validos)
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
    pasta = Path(pasta_resultados) if pasta_resultados else (
        config.PASTA_PROJETO / "resultados" / "doentes" / caminho.stem)
    completas = {"distancias_km": distancias, "tempos_condicoes_reais_min": tempos_reais}
    if desenhar_percursos is None:
        desenhar_percursos = len(incluidos) <= 20
    exportar(pasta, tabela, quadradas, completas, pares, encaixe, verificacoes, desenhar_percursos)

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
    mensagem(f"PARTE B concluída. Resultados em: {pasta.resolve().relative_to(config.PASTA_PROJETO)}/")
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
