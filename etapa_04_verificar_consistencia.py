"""
ETAPA 4 — Verificar a consistência dos tempos e distâncias de viagem
=====================================================================

OBJETIVO
--------
Confirmar que os resultados do OSRM fazem sentido antes de os usar.

VERIFICAÇÕES REALIZADAS
-----------------------
  1. Estado do cálculo: quantas subsecções têm rota, quantas não têm
     ligação à rede, quantas têm erro da API ou coordenadas inválidas.
  2. Encaixe na rede: centroides muito afastados da estrada mais próxima.
  3. Velocidade média implícita (distância ÷ tempo): valores abaixo de
     3 km/h ou acima de 130 km/h indicam um problema.
  4. Distância por estrada ≥ distância em linha reta (entre os pontos
     encaixados na estrada): se não, há um erro.
  5. Assimetria ida/regresso: quantifica as diferenças entre os dois sentidos
     (é normal haver algumas; não se assume simetria).
  6. Desigualdade triangular: para uma AMOSTRA de subsecções, calcula-se a
     matriz quadrada completa (todos-para-todos) e confirma-se que
         tempo(A→C) ≤ tempo(A→B) + tempo(B→C)
     para todos os trios A, B, C. Num cálculo de caminhos mais curtos esta
     regra tem de se verificar (com pequena folga para arredondamentos).
  7. Diagonal da matriz: o tempo de um ponto para si próprio deve ser 0.

RESULTADOS
----------
    resultados/relatorios/verificacoes_consistencia.csv
    resultados/relatorios/problemas_por_subseccao.csv
    resultados/matrizes/matriz_amostra_tempos_minutos.csv     (quadrada)
    resultados/matrizes/matriz_amostra_distancias_km.csv      (quadrada)

EXECUTAR SÓ ESTA ETAPA (depois da etapa 3)
------------------------------------------
    python etapa_04_verificar_consistencia.py
"""

import geopandas as gpd
import numpy as np
import pandas as pd

import config
from etapa_03_calcular_matrizes_osrm import pedir_tabela_osrm
from utilitarios import mensagem, registar_metadados, verificar_ficheiro_existe


def contar_violacoes_triangulares(matriz, tolerancia):
    """
    Conta quantos trios (i, j, k) violam a desigualdade triangular:
        matriz[i, k] > matriz[i, j] + matriz[j, k] + tolerancia

    Parâmetros:
        matriz (numpy.ndarray): matriz quadrada de tempos (ou distâncias).
        tolerancia (float): folga permitida, nas mesmas unidades da matriz.

    Devolve:
        tuple (int, int, float): nº de violações, nº de trios testados e
        a maior violação encontrada (0 se não houver).
    """
    n = matriz.shape[0]
    violacoes = 0
    maior_excesso = 0.0
    for j in range(n):
        # Para cada ponto intermédio j, compara todos os pares (i, k) de uma vez:
        # caminho_via_j[i, k] = matriz[i, j] + matriz[j, k]
        caminho_via_j = matriz[:, j][:, None] + matriz[j, :][None, :]
        excesso = matriz - caminho_via_j
        violacoes += int((excesso > tolerancia).sum())
        maior_excesso = max(maior_excesso, float(np.nanmax(excesso)))
    return violacoes, n ** 3, max(maior_excesso, 0.0)


def distancia_linha_reta_km(lat1, lon1, lat2, lon2):
    """
    Distância em linha reta (fórmula de Haversine) entre dois pontos.

    Parâmetros:
        lat1, lon1, lat2, lon2 (float ou arrays): coordenadas em graus.

    Devolve:
        float ou array: distância em quilómetros.
    """
    raio_terra_km = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * raio_terra_km * np.arcsin(np.sqrt(a))


def construir_matriz_amostra(routing, subseccoes):
    """
    Sorteia uma amostra de subsecções com rota válida, pede ao OSRM a matriz
    quadrada completa (hospital + amostra, todos-para-todos) e exporta-a.

    Parâmetros:
        routing (DataFrame): resultados da etapa 3.
        subseccoes (DataFrame): tabela da etapa 2.

    Devolve:
        tuple (ndarray, ndarray, list[str]) ou None: matriz de tempos (s),
        matriz de distâncias (m) e etiquetas das linhas/colunas.
    """
    com_rota = routing[routing["estado_routing"].str.startswith("ok")]
    tamanho = min(config.TAMANHO_AMOSTRA_TRIANGULAR, len(com_rota))
    amostra = com_rota.sample(n=tamanho, random_state=config.SEMENTE_ALEATORIA)
    amostra = amostra.merge(subseccoes[["id_subseccao", "latitude", "longitude"]], on="id_subseccao")

    coordenadas = [(config.HOSPITAL_LONGITUDE, config.HOSPITAL_LATITUDE)]
    coordenadas += list(zip(amostra["longitude"], amostra["latitude"]))
    etiquetas = ["HOSPITAL"] + list(amostra["id_subseccao"])
    try:
        resposta = pedir_tabela_osrm(coordenadas)  # sem sources/destinations = todos
    except RuntimeError as erro:
        mensagem(f"   AVISO: não foi possível obter a matriz da amostra ({erro}).")
        return None

    tempos = np.array(resposta["durations"], dtype=float)
    distancias = np.array(resposta["distances"], dtype=float)
    opcoes = {"encoding": "utf-8-sig", "sep": ";", "decimal": ","}
    pd.DataFrame(tempos / 60, index=etiquetas, columns=etiquetas).round(2).to_csv(
        config.PASTA_MATRIZES / "matriz_amostra_tempos_minutos.csv", **opcoes)
    pd.DataFrame(distancias / 1000, index=etiquetas, columns=etiquetas).round(3).to_csv(
        config.PASTA_MATRIZES / "matriz_amostra_distancias_km.csv", **opcoes)
    mensagem(f"   Matriz quadrada da amostra ({len(etiquetas)}×{len(etiquetas)}) exportada.")
    return tempos, distancias, etiquetas


def executar_etapa_4():
    """
    Executa todas as verificações de consistência e grava os relatórios.

    Devolve:
        DataFrame: tabela com o resultado de cada verificação.
    """
    mensagem("=" * 70)
    mensagem("ETAPA 4 — Verificações de consistência")
    mensagem("=" * 70)

    routing = pd.read_csv(config.FICHEIRO_ROUTING, dtype={"id_subseccao": str})
    subseccoes = pd.DataFrame(gpd.read_file(config.FICHEIRO_SUBSECCOES).drop(columns="geometry"))
    verificacoes = []

    def registar(nome, resultado, valor, explicacao):
        """Acrescenta uma verificação à lista (função interna, só para organizar)."""
        verificacoes.append({"verificacao": nome, "resultado": resultado,
                             "valor": valor, "explicacao": explicacao})
        mensagem(f"   [{resultado:^7}] {nome}: {valor}")

    # 1. Estados do cálculo
    estados = routing["estado_routing"].value_counts().to_dict()
    sem_rota = estados.get("sem_rota", 0) + estados.get("erro_api", 0) + estados.get("coordenada_invalida", 0)
    registar("Subsecções sem tempo de viagem", "OK" if sem_rota == 0 else "AVISO", sem_rota,
             f"Estados: {estados}")

    validos = routing[routing["estado_routing"].str.startswith("ok")].copy()

    # 2. Encaixe na rede
    afastados = int((validos["distancia_ate_estrada_m"] > config.DISTANCIA_MAXIMA_ATE_ESTRADA_M).sum())
    registar("Centroides afastados da estrada (> "
             f"{config.DISTANCIA_MAXIMA_ATE_ESTRADA_M} m)", "OK" if afastados == 0 else "AVISO",
             afastados, f"Distância de encaixe mediana: "
             f"{validos['distancia_ate_estrada_m'].median():.0f} m; máxima: "
             f"{validos['distancia_ate_estrada_m'].max():.0f} m")

    # 2b. Todos os pontos (centroides e pontos de encaixe na estrada) em Portugal
    territorio = gpd.read_file(config.FICHEIRO_TERRITORIO).to_crs(config.CRS_PORTUGAL)
    # tolerância de 100 m para pontos exatamente sobre a linha de fronteira
    limite_portugal = territorio.geometry.iloc[0].buffer(100)
    pontos_estrada = gpd.GeoSeries(gpd.points_from_xy(validos["longitude_na_estrada"],
                                                      validos["latitude_na_estrada"]),
                                   crs=config.CRS_WGS84).to_crs(config.CRS_PORTUGAL)
    fora = ~pontos_estrada.within(limite_portugal).values
    validos["encaixe_em_portugal"] = ~fora
    registar("Pontos de encaixe na estrada fora de Portugal", "OK" if fora.sum() == 0 else "ERRO",
             int(fora.sum()), "Todos os destinos devem estar em território português.")

    # 3. Velocidade média implícita
    for sentido in ["ida", "regresso"]:
        tempo_h = validos[f"tempo_{sentido}_min"] / 60
        velocidade = validos[f"distancia_{sentido}_km"] / tempo_h.where(tempo_h > 0)
        validos[f"velocidade_{sentido}_kmh"] = velocidade
        suspeitas = int(((velocidade < config.VELOCIDADE_MEDIA_MINIMA_KMH) |
                         (velocidade > config.VELOCIDADE_MEDIA_MAXIMA_KMH)).sum())
        registar(f"Velocidades médias implausíveis ({sentido})", "OK" if suspeitas == 0 else "AVISO",
                 suspeitas, f"Mediana: {velocidade.median():.1f} km/h; "
                 f"mín.: {velocidade.min():.1f}; máx.: {velocidade.max():.1f}")

    # 4. Distância por estrada >= distância em linha reta (pontos na estrada)
    reta_km = distancia_linha_reta_km(config.HOSPITAL_LATITUDE, config.HOSPITAL_LONGITUDE,
                                      validos["latitude_na_estrada"], validos["longitude_na_estrada"])
    validos["distancia_linha_reta_km"] = reta_km
    impossiveis = int((validos["distancia_ida_km"] < reta_km - 0.05).sum())
    registar("Distância por estrada menor que em linha reta", "OK" if impossiveis == 0 else "ERRO",
             impossiveis, "Fator de sinuosidade mediano (estrada / linha reta): "
             f"{(validos['distancia_ida_km'] / reta_km).median():.2f}")

    # 5. Assimetria ida/regresso
    diferenca = validos["tempo_regresso_min"] - validos["tempo_ida_min"]
    relativa = diferenca.abs() / validos["tempo_ida_min"].where(validos["tempo_ida_min"] > 0)
    registar("Subsecções com assimetria ida/regresso > 10 %", "INFO",
             int((relativa > 0.10).sum()),
             f"Diferença média (regresso − ida): {diferenca.mean():.2f} min; "
             f"máx. absoluta: {diferenca.abs().max():.2f} min. A assimetria é esperada.")
    mudam = int(((validos["tempo_ida_min"] <= config.LIMITE_TEMPO_MINUTOS) !=
                 (validos["tempo_regresso_min"] <= config.LIMITE_TEMPO_MINUTOS)).sum())
    registar("Subsecções cuja classificação mudaria se se usasse o regresso", "INFO", mudam,
             "A classificação oficial usa o sentido hospital → domicílio.")

    # 6 e 7. Desigualdade triangular e diagonal (matriz quadrada da amostra)
    matriz = construir_matriz_amostra(routing, subseccoes)
    if matriz is not None:
        tempos_s, distancias_m, etiquetas = matriz
        diagonal = float(np.abs(np.diag(tempos_s)).max())
        registar("Diagonal da matriz (tempo de um ponto para si próprio)",
                 "OK" if diagonal == 0 else "ERRO", f"{diagonal:.1f} s", "Deve ser 0.")
        n_viol, n_trios, excesso = contar_violacoes_triangulares(tempos_s, config.TOLERANCIA_TRIANGULAR_S)
        registar("Desigualdade triangular (tempos)", "OK" if n_viol == 0 else "AVISO",
                 f"{n_viol} violações em {n_trios} trios",
                 f"Maior excesso: {excesso:.1f} s (tolerância {config.TOLERANCIA_TRIANGULAR_S} s)")
        n_viol_d, _, excesso_d = contar_violacoes_triangulares(distancias_m, 5.0)
        registar("Desigualdade triangular (distâncias)", "INFO",
                 f"{n_viol_d} violações em {n_trios} trios",
                 "O OSRM minimiza o TEMPO e não a distância; violações nas distâncias "
                 f"podem ocorrer e não são um erro (maior excesso: {excesso_d:.0f} m).")
        # Coerência entre a matriz da amostra e os pedidos da etapa 3
        amostra = pd.DataFrame({"id_subseccao": etiquetas[1:], "tempo_amostra_min": tempos_s[0, 1:] / 60})
        amostra = amostra.merge(routing[["id_subseccao", "tempo_ida_min"]], on="id_subseccao")
        desvio = float((amostra["tempo_amostra_min"] - amostra["tempo_ida_min"]).abs().max())
        registar("Repetibilidade: mesma rota pedida duas vezes", "OK" if desvio < 0.1 else "AVISO",
                 f"{desvio:.2f} min", "Diferença máxima entre a matriz da amostra e a etapa 3.")

    # ---- Guardar ----
    config.PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)
    tabela = pd.DataFrame(verificacoes)
    tabela.to_csv(config.PASTA_RELATORIOS / "verificacoes_consistencia.csv",
                  index=False, encoding="utf-8-sig", sep=";")
    problemas = routing[routing["estado_routing"] != "ok"]
    problemas.to_csv(config.PASTA_RELATORIOS / "problemas_por_subseccao.csv",
                     index=False, encoding="utf-8-sig", sep=";", decimal=",")
    registar_metadados("etapa_04_consistencia", {
        "verificacoes": verificacoes,
        "tamanho_amostra_triangular": config.TAMANHO_AMOSTRA_TRIANGULAR,
        "semente_aleatoria": config.SEMENTE_ALEATORIA,
    })
    mensagem("ETAPA 4 concluída. Relatório: resultados/relatorios/verificacoes_consistencia.csv")
    return tabela


if __name__ == "__main__":
    verificar_ficheiro_existe(config.FICHEIRO_ROUTING, "etapa_03_calcular_matrizes_osrm.py")
    executar_etapa_4()
