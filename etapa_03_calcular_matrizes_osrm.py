"""
ETAPA 3 — Calcular distâncias e tempos de viagem na rede rodoviária (OSRM)
===========================================================================

OBJETIVO
--------
Para cada centroide de subsecção, calcular com o OSRM (rede OpenStreetMap):
    * hospital  → domicílio : tempo (min) e distância (km)  — "IDA"
    * domicílio → hospital  : tempo (min) e distância (km)  — "REGRESSO"

Os dois sentidos são pedidos SEPARADAMENTE, porque não são necessariamente
iguais (ruas de sentido único, acessos a autoestradas, rotundas...).

COMO FUNCIONA O SERVIÇO /table DO OSRM
---------------------------------------
Envia-se uma lista de coordenadas: a primeira é o hospital e as seguintes são
até 99 centroides. Com o parâmetro "sources=0" obtém-se a linha da matriz
"hospital → todos"; com "destinations=0" obtém-se a coluna "todos → hospital".
O OSRM "encaixa" (snapping) cada coordenada na estrada mais próxima e indica
a distância desse encaixe — útil para detetar locais longe da rede.

RETOMAR UMA EXECUÇÃO INTERROMPIDA
---------------------------------
Os resultados são gravados bloco a bloco em dados/processados/resultados_routing.csv.
Se o programa for interrompido (falha de rede, Ctrl+C), ao executar outra vez
só são pedidas as subsecções que ainda faltam.

RESULTADOS
----------
    resultados/matrizes/matriz_tempos_minutos.csv       (ida e regresso)
    resultados/matrizes/matriz_distancias_km.csv        (ida e regresso)
    resultados/matrizes/matrizes_ida_regresso.xlsx      (as duas, em Excel)

EXECUTAR SÓ ESTA ETAPA (depois da etapa 2)
------------------------------------------
    python etapa_03_calcular_matrizes_osrm.py
(Demora cerca de 5–10 minutos com o servidor público do OSRM.)
"""

import time
from datetime import datetime

import geopandas as gpd
import pandas as pd
import requests

import config
from utilitarios import mensagem, registar_metadados, verificar_ficheiro_existe


def pedir_tabela_osrm(coordenadas, sources=None, destinations=None):
    """
    Faz um pedido ao serviço /table do OSRM, com novas tentativas em caso de erro.

    Parâmetros:
        coordenadas (list[tuple]): lista de (longitude, latitude).
            ATENÇÃO: o OSRM usa a ordem longitude,latitude!
        sources (str ou None): índices das origens (ex.: "0"); None = todas.
        destinations (str ou None): índices dos destinos; None = todos.

    Devolve:
        dict: resposta JSON do OSRM (com "durations", "distances",
        "sources", "destinations").

    Erros:
        RuntimeError se o pedido falhar em todas as tentativas.
    """
    texto_coordenadas = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coordenadas)
    url = f"{config.OSRM_URL}/table/v1/{config.OSRM_PERFIL}/{texto_coordenadas}"
    parametros = {"annotations": "duration,distance"}
    if sources is not None:
        parametros["sources"] = sources
    if destinations is not None:
        parametros["destinations"] = destinations

    ultimo_erro = None
    for tentativa in range(1, config.OSRM_TENTATIVAS + 1):
        try:
            resposta = requests.get(url, params=parametros, timeout=config.OSRM_TIMEOUT_S,
                                    headers=config.CABECALHOS_HTTP)
            if resposta.status_code == 429:
                raise requests.RequestException("demasiados pedidos (429)")
            dados = resposta.json()
            if dados.get("code") != "Ok":
                raise requests.RequestException(f"OSRM respondeu {dados.get('code')}: "
                                                f"{dados.get('message')}")
            return dados
        except (requests.RequestException, ValueError) as erro:
            ultimo_erro = erro
            espera = 2 ** tentativa
            mensagem(f"      ERRO na API OSRM ({tentativa}/{config.OSRM_TENTATIVAS}): "
                     f"{erro}. Nova tentativa em {espera} s.")
            time.sleep(espera)
    raise RuntimeError(f"Falha definitiva no OSRM: {ultimo_erro}")


def calcular_bloco(bloco):
    """
    Calcula ida e regresso entre o hospital e um bloco de subsecções.

    Parâmetros:
        bloco (DataFrame): até OSRM_PONTOS_POR_PEDIDO linhas com
        "id_subseccao", "latitude" e "longitude".

    Devolve:
        list[dict]: um dicionário por subsecção com tempos, distâncias,
        distância de encaixe na estrada e estado do cálculo.
    """
    hospital = (config.HOSPITAL_LONGITUDE, config.HOSPITAL_LATITUDE)
    coordenadas = [hospital] + list(zip(bloco["longitude"], bloco["latitude"]))
    agora = datetime.now().isoformat(timespec="seconds")

    try:
        ida = pedir_tabela_osrm(coordenadas, sources="0")             # 1 linha
        time.sleep(config.OSRM_PAUSA_ENTRE_PEDIDOS_S)
        regresso = pedir_tabela_osrm(coordenadas, destinations="0")   # 1 coluna
        time.sleep(config.OSRM_PAUSA_ENTRE_PEDIDOS_S)
    except RuntimeError as erro:
        # Não interrompe o estudo: as subsecções ficam marcadas com o erro.
        return [{"id_subseccao": i, "estado_routing": "erro_api", "observacao": str(erro),
                 "data_calculo": agora} for i in bloco["id_subseccao"]]

    resultados = []
    for posicao, id_subseccao in enumerate(bloco["id_subseccao"], start=1):
        tempo_ida = ida["durations"][0][posicao]
        distancia_ida = ida["distances"][0][posicao]
        tempo_regresso = regresso["durations"][posicao][0]
        distancia_regresso = regresso["distances"][posicao][0]
        encaixe = ida["destinations"][posicao].get("distance")
        local_encaixe = ida["destinations"][posicao].get("location", [None, None])

        if tempo_ida is None or tempo_regresso is None:
            estado = "sem_rota"
            observacao = "O OSRM não encontrou percurso (local sem ligação à rede)."
        elif encaixe is not None and encaixe > config.DISTANCIA_MAXIMA_ATE_ESTRADA_M:
            estado = "ok_afastado_da_rede"
            observacao = (f"Centroide a {encaixe:.0f} m da estrada mais próxima; o tempo "
                          "desse troço não está incluído.")
        else:
            estado = "ok"
            observacao = ""

        resultados.append({
            "id_subseccao": id_subseccao,
            "tempo_ida_min": None if tempo_ida is None else round(tempo_ida / 60, 2),
            "distancia_ida_km": None if distancia_ida is None else round(distancia_ida / 1000, 3),
            "tempo_regresso_min": None if tempo_regresso is None else round(tempo_regresso / 60, 2),
            "distancia_regresso_km": None if distancia_regresso is None else round(distancia_regresso / 1000, 3),
            "distancia_ate_estrada_m": None if encaixe is None else round(encaixe, 1),
            "longitude_na_estrada": local_encaixe[0],
            "latitude_na_estrada": local_encaixe[1],
            "estado_routing": estado,
            "observacao": observacao,
            "data_calculo": agora,
        })
    return resultados


def obter_informacao_hospital():
    """
    Pergunta ao OSRM onde o hospital "encaixa" na rede rodoviária.

    Devolve:
        dict: nome da rua, coordenadas na estrada e distância de encaixe (m).
    """
    url = (f"{config.OSRM_URL}/nearest/v1/{config.OSRM_PERFIL}/"
           f"{config.HOSPITAL_LONGITUDE},{config.HOSPITAL_LATITUDE}")
    try:
        dados = requests.get(url, timeout=30, headers=config.CABECALHOS_HTTP).json()
        ponto = dados["waypoints"][0]
        return {"rua": ponto.get("name"), "coordenadas_na_estrada": ponto.get("location"),
                "distancia_encaixe_m": round(ponto.get("distance", 0), 1),
                "data_version_osrm": dados.get("data_version")}
    except (requests.RequestException, ValueError, KeyError, IndexError) as erro:
        return {"erro": str(erro)}


def exportar_matrizes(routing, subseccoes):
    """
    Exporta as matrizes de tempos e distâncias (ida e regresso) em CSV e Excel.

    Formato: uma linha por subsecção; colunas "HOSPITAL → domicílio" e
    "domicílio → HOSPITAL". É a matriz completa origem-destino entre o
    hospital e todas as subsecções, nos dois sentidos.

    Parâmetros:
        routing (DataFrame): resultados do OSRM.
        subseccoes (DataFrame): tabela da etapa 2 (para a designação).

    Devolve:
        Nada (grava os ficheiros em resultados/matrizes/).
    """
    tabela = subseccoes[["id_subseccao", "designacao"]].merge(routing, on="id_subseccao", how="left")
    tempos = tabela[["id_subseccao", "designacao", "tempo_ida_min", "tempo_regresso_min"]].rename(
        columns={"tempo_ida_min": "HOSPITAL_para_domicilio_min",
                 "tempo_regresso_min": "domicilio_para_HOSPITAL_min"})
    distancias = tabela[["id_subseccao", "designacao", "distancia_ida_km",
                         "distancia_regresso_km"]].rename(
        columns={"distancia_ida_km": "HOSPITAL_para_domicilio_km",
                 "distancia_regresso_km": "domicilio_para_HOSPITAL_km"})
    tempos["diferenca_regresso_menos_ida_min"] = (tempos["domicilio_para_HOSPITAL_min"]
                                                  - tempos["HOSPITAL_para_domicilio_min"]).round(2)
    distancias["diferenca_regresso_menos_ida_km"] = (distancias["domicilio_para_HOSPITAL_km"]
                                                     - distancias["HOSPITAL_para_domicilio_km"]).round(3)

    config.PASTA_MATRIZES.mkdir(parents=True, exist_ok=True)
    opcoes = {"index": False, "encoding": "utf-8-sig", "sep": ";", "decimal": ","}
    tempos.to_csv(config.PASTA_MATRIZES / "matriz_tempos_minutos.csv", **opcoes)
    distancias.to_csv(config.PASTA_MATRIZES / "matriz_distancias_km.csv", **opcoes)
    with pd.ExcelWriter(config.PASTA_MATRIZES / "matrizes_ida_regresso.xlsx") as excel:
        tempos.to_excel(excel, sheet_name="tempos_minutos", index=False)
        distancias.to_excel(excel, sheet_name="distancias_km", index=False)
        routing.to_excel(excel, sheet_name="dados_routing_completos", index=False)
    mensagem("   Matrizes exportadas para resultados/matrizes/")


def executar_etapa_3():
    """
    Executa a etapa 3: calcula (ou retoma) o routing de todas as subsecções
    e exporta as matrizes.

    Devolve:
        DataFrame: resultados de routing (uma linha por subsecção).
    """
    mensagem("=" * 70)
    mensagem("ETAPA 3 — Distâncias e tempos de viagem na rede rodoviária (OSRM)")
    mensagem("=" * 70)

    subseccoes = pd.DataFrame(gpd.read_file(config.FICHEIRO_SUBSECCOES).drop(columns="geometry"))
    subseccoes["id_subseccao"] = subseccoes["id_subseccao"].astype(str)

    # Coordenadas inválidas não são enviadas ao OSRM
    invalidas = subseccoes[~subseccoes["coordenada_valida"]]
    validas = subseccoes[subseccoes["coordenada_valida"]]

    # Retomar: ver quais já foram calculadas com sucesso
    ja_calculadas = pd.DataFrame()
    if config.FICHEIRO_ROUTING.exists():
        ja_calculadas = pd.read_csv(config.FICHEIRO_ROUTING, dtype={"id_subseccao": str})
        ja_calculadas = ja_calculadas[ja_calculadas["estado_routing"] != "erro_api"]
        mensagem(f"   Encontrados {len(ja_calculadas)} resultados anteriores (serão reutilizados).")
    em_falta = validas[~validas["id_subseccao"].isin(ja_calculadas.get("id_subseccao", []))]

    total_blocos = (len(em_falta) + config.OSRM_PONTOS_POR_PEDIDO - 1) // config.OSRM_PONTOS_POR_PEDIDO
    mensagem(f"   Subsecções a calcular: {len(em_falta)} em {total_blocos} blocos "
             f"de até {config.OSRM_PONTOS_POR_PEDIDO}.")

    novos = []
    for numero in range(total_blocos):
        inicio = numero * config.OSRM_PONTOS_POR_PEDIDO
        bloco = em_falta.iloc[inicio:inicio + config.OSRM_PONTOS_POR_PEDIDO]
        novos.extend(calcular_bloco(bloco))
        if (numero + 1) % 10 == 0 or numero + 1 == total_blocos:
            mensagem(f"   Progresso: bloco {numero + 1}/{total_blocos}")
            # gravação intermédia, para poder retomar
            parcial = pd.concat([ja_calculadas, pd.DataFrame(novos)], ignore_index=True)
            parcial.to_csv(config.FICHEIRO_ROUTING, index=False)

    routing = pd.concat([ja_calculadas, pd.DataFrame(novos)], ignore_index=True)
    if len(invalidas):
        routing = pd.concat([routing, pd.DataFrame({
            "id_subseccao": invalidas["id_subseccao"], "estado_routing": "coordenada_invalida",
            "observacao": "Coordenadas fora de Portugal Continental ou em falta."})],
            ignore_index=True)
    routing = routing.drop_duplicates("id_subseccao", keep="last")
    routing.to_csv(config.FICHEIRO_ROUTING, index=False)

    contagem = routing["estado_routing"].value_counts().to_dict()
    mensagem(f"   Estados do cálculo: {contagem}")
    exportar_matrizes(routing, subseccoes)

    registar_metadados("etapa_03_routing", {
        "servico": "OSRM (Open Source Routing Machine) — serviço /table",
        "servidor": config.OSRM_URL,
        "perfil": config.OSRM_PERFIL,
        "rede_rodoviaria": "OpenStreetMap (versão carregada no servidor à data do cálculo)",
        "hospital_na_rede": obter_informacao_hospital(),
        "pontos_por_pedido": config.OSRM_PONTOS_POR_PEDIDO,
        "pausa_entre_pedidos_s": config.OSRM_PAUSA_ENTRE_PEDIDOS_S,
        "distancia_maxima_ate_estrada_m": config.DISTANCIA_MAXIMA_ATE_ESTRADA_M,
        "sentidos_calculados": ["hospital → domicílio", "domicílio → hospital"],
        "estados": contagem,
        "data_calculo_inicio": routing["data_calculo"].min(),
        "data_calculo_fim": routing["data_calculo"].max(),
        "nota": "Tempos em condições de tráfego livre (sem trânsito em tempo real).",
    })
    mensagem("ETAPA 3 concluída.")
    return routing


if __name__ == "__main__":
    verificar_ficheiro_existe(config.FICHEIRO_SUBSECCOES, "etapa_02_preparar_subseccoes.py")
    executar_etapa_3()
