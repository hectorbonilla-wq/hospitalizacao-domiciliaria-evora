"""
ETAPA 3 — Calcular distâncias e tempos de viagem na rede rodoviária
(OpenRouteService ou OSRM, ambos sobre a rede OpenStreetMap — ver config.MOTOR_ROUTING)
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
from routing import (descricao_motor, motor_em_uso, pedir_matriz, pontos_por_pedido,
                     ponto_mais_proximo_na_estrada)
from utilitarios import mensagem, registar_metadados, verificar_ficheiro_existe


def calcular_bloco(bloco):
    """
    Calcula ida e regresso entre o hospital e um bloco de subsecções.

    Parâmetros:
        bloco (DataFrame): até pontos_por_pedido() linhas com
        "id_subseccao", "latitude" e "longitude".

    Devolve:
        list[dict]: um dicionário por subsecção com tempos, distâncias,
        distância de encaixe na estrada e estado do cálculo.
    """
    hospital = (config.HOSPITAL_LONGITUDE, config.HOSPITAL_LATITUDE)
    coordenadas = [hospital] + list(zip(bloco["longitude"], bloco["latitude"]))
    agora = datetime.now().isoformat(timespec="seconds")

    try:
        ida = pedir_matriz(coordenadas, sources=[0])             # 1 linha: hospital → todos
        regresso = pedir_matriz(coordenadas, destinations=[0])   # 1 coluna: todos → hospital
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
        local_encaixe = ida["destinations"][posicao].get("location") or [None, None]

        if tempo_ida is None or tempo_regresso is None:
            estado = "sem_rota"
            observacao = "O motor de routing não encontrou percurso (local sem ligação à rede)."
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


def recalcular_sem_rota(routing, subseccoes):
    """
    Segunda tentativa para as subsecções sem rota.

    O OpenRouteService só liga um ponto à rede se houver uma estrada a menos de
    ~350 m; em zonas rurais alguns centroides ficam mais longe. Para esses,
    procura-se o ponto da estrada mais próximo (OSRM /nearest, rede OSM) e
    recalcula-se a ida e o regresso a partir desse ponto. A distância entre o
    centroide e a estrada fica registada (o tempo desse troço não é contado).

    Parâmetros:
        routing (DataFrame): resultados da primeira passagem.
        subseccoes (DataFrame): tabela da etapa 2.

    Devolve:
        DataFrame: routing atualizado.
    """
    sem_rota = routing[routing["estado_routing"] == "sem_rota"]
    if sem_rota.empty:
        return routing
    mensagem(f"   {len(sem_rota)} subsecções sem ligação direta à rede: a ligar à estrada mais próxima...")
    coordenadas = subseccoes.set_index("id_subseccao").loc[sem_rota["id_subseccao"], ["longitude", "latitude"]]
    pontos = []
    for id_subseccao, (lon, lat) in coordenadas.iterrows():
        estrada = ponto_mais_proximo_na_estrada(lon, lat)
        if estrada:
            pontos.append((id_subseccao, estrada))
    if not pontos:
        return routing
    lista = [(config.HOSPITAL_LONGITUDE, config.HOSPITAL_LATITUDE)] + [(e[0], e[1]) for _, e in pontos]
    try:
        ida = pedir_matriz(lista, sources=[0])
        regresso = pedir_matriz(lista, destinations=[0])
    except RuntimeError as erro:
        mensagem(f"   AVISO: segunda tentativa falhou ({erro}).")
        return routing
    routing = routing.set_index("id_subseccao")
    for posicao, (id_subseccao, (lon, lat, distancia)) in enumerate(pontos, start=1):
        tempo_ida, tempo_regresso = ida["durations"][0][posicao], regresso["durations"][posicao][0]
        if tempo_ida is None or tempo_regresso is None:
            continue
        routing.loc[id_subseccao, ["tempo_ida_min", "distancia_ida_km", "tempo_regresso_min",
                                   "distancia_regresso_km", "distancia_ate_estrada_m",
                                   "longitude_na_estrada", "latitude_na_estrada"]] = [
            round(tempo_ida / 60, 2), round(ida["distances"][0][posicao] / 1000, 3),
            round(tempo_regresso / 60, 2), round(regresso["distances"][posicao][0] / 1000, 3),
            round(distancia, 1), lon, lat]
        routing.loc[id_subseccao, "estado_routing"] = (
            "ok_afastado_da_rede" if distancia > config.DISTANCIA_MAXIMA_ATE_ESTRADA_M else "ok_reencaixado")
        routing.loc[id_subseccao, "observacao"] = (
            f"Centroide a {distancia:.0f} m da estrada; calculado a partir do ponto da estrada mais "
            "próximo (o tempo desse troço não está incluído).")
    resolvidas = int((routing.loc[[p[0] for p in pontos], "estado_routing"] != "sem_rota").sum())
    mensagem(f"   Resolvidas na segunda tentativa: {resolvidas} de {len(sem_rota)}")
    return routing.reset_index()


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
    mensagem("ETAPA 3 — Distâncias e tempos de viagem na rede rodoviária (OpenStreetMap)")
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

    tamanho_bloco = pontos_por_pedido()
    total_blocos = (len(em_falta) + tamanho_bloco - 1) // tamanho_bloco
    mensagem(f"   Motor de routing: {descricao_motor()}")
    mensagem(f"   Subsecções a calcular: {len(em_falta)} em {total_blocos} blocos "
             f"de até {tamanho_bloco} (2 pedidos por bloco: ida e regresso).")

    novos = []
    for numero in range(total_blocos):
        inicio = numero * tamanho_bloco
        bloco = em_falta.iloc[inicio:inicio + tamanho_bloco]
        novos.extend(calcular_bloco(bloco))
        if (numero + 1) % 10 == 0 or numero + 1 == total_blocos or tamanho_bloco > 500:
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
    routing = recalcular_sem_rota(routing, subseccoes)
    routing.to_csv(config.FICHEIRO_ROUTING, index=False)

    contagem = routing["estado_routing"].value_counts().to_dict()
    mensagem(f"   Estados do cálculo: {contagem}")
    exportar_matrizes(routing, subseccoes)

    registar_metadados("etapa_03_routing", {
        "servico": descricao_motor(),
        "motor": motor_em_uso(),
        "servidor": config.ORS_URL if motor_em_uso() == "ors" else config.OSRM_URL,
        "perfil": config.ORS_PERFIL if motor_em_uso() == "ors" else config.OSRM_PERFIL,
        "rede_rodoviaria": "OpenStreetMap (versão carregada no servidor à data do cálculo)",
        "hospital_na_rede": obter_informacao_hospital(),
        "pontos_por_pedido": tamanho_bloco,
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
