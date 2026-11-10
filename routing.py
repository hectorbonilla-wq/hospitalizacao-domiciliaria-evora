"""
routing.py — Pedidos de matrizes de tempos/distâncias (OpenRouteService ou OSRM)
=================================================================================

Este ficheiro esconde as diferenças entre os dois serviços de routing que o
projeto pode usar. As etapas só chamam a função pedir_matriz(), que devolve
SEMPRE o mesmo formato, seja qual for o motor escolhido em config.MOTOR_ROUTING:

    {
      "durations":    [[segundos, ...], ...],   # linha = origem, coluna = destino
      "distances":    [[metros, ...], ...],
      "sources":      [{"location": [lon, lat], "distance": metros_ate_estrada}, ...],
      "destinations": [{"location": [lon, lat], "distance": metros_ate_estrada}, ...],
    }

MOTORES
-------
  * "ors"  — OpenRouteService (api.openrouteservice.org), rede OpenStreetMap,
             perfil "driving-car". Precisa de uma chave pessoal (gratuita), lida
             do ficheiro chave_openrouteservice.txt ou da variável de ambiente
             ORS_API_KEY. Até ~3500 percursos por pedido; quota diária limitada.
  * "osrm" — servidor público do OSRM, sem chave, até 100 pontos por pedido.

Nenhum dos dois tem trânsito em tempo real: ambos usam velocidades típicas por
tipo de via do OpenStreetMap.
"""

import os
import time

import requests

import config
from utilitarios import mensagem


# ---------------------------------------------------------------------------
# Chave do OpenRouteService
# ---------------------------------------------------------------------------
def ler_chave_ors():
    """
    Lê a chave do OpenRouteService.

    Procura primeiro a variável de ambiente ORS_API_KEY e depois o ficheiro
    chave_openrouteservice.txt na pasta do projeto (este ficheiro está no
    .gitignore e NUNCA deve ser enviado para o GitHub).

    Devolve:
        str ou None: a chave, ou None se não existir.
    """
    chave = os.environ.get("ORS_API_KEY", "").strip()
    if chave:
        return chave
    ficheiro = config.PASTA_PROJETO / "chave_openrouteservice.txt"
    if ficheiro.exists():
        return ficheiro.read_text(encoding="utf-8").strip() or None
    return None


def motor_em_uso():
    """
    Indica o motor de routing que vai ser usado.

    Se config.MOTOR_ROUTING for "ors" mas não houver chave, usa o OSRM e avisa.

    Devolve:
        str: "ors" ou "osrm".
    """
    if config.MOTOR_ROUTING == "ors" and not ler_chave_ors():
        mensagem("   AVISO: sem chave do OpenRouteService (chave_openrouteservice.txt ou "
                 "ORS_API_KEY). A usar o OSRM público.")
        return "osrm"
    return config.MOTOR_ROUTING


def descricao_motor():
    """
    Texto que descreve o motor em uso (para relatórios e metadados).

    Devolve:
        str: ex. "OpenRouteService (driving-car) — https://api.openrouteservice.org".
    """
    if motor_em_uso() == "ors":
        return f"OpenRouteService ({config.ORS_PERFIL}) — {config.ORS_URL}"
    return f"OSRM ({config.OSRM_PERFIL}) — {config.OSRM_URL}"


def nome_motor():
    """
    Nome curto do motor em uso, para legendas.

    Devolve:
        str: "OpenRouteService" ou "OSRM".
    """
    return "OpenRouteService" if motor_em_uso() == "ors" else "OSRM"


def nome_servico_isocrona():
    """
    Nome do serviço que desenha a isócrona (o ORS tem isócronas; o OSRM não,
    e nesse caso usa-se o Valhalla).

    Devolve:
        str: "OpenRouteService" ou "Valhalla".
    """
    return "OpenRouteService" if motor_em_uso() == "ors" else "Valhalla"


def pontos_por_pedido():
    """
    Nº máximo de subsecções por pedido, conforme o motor.

    Devolve:
        int: pontos por pedido (sem contar com o hospital).
    """
    return config.ORS_PONTOS_POR_PEDIDO if motor_em_uso() == "ors" else config.OSRM_PONTOS_POR_PEDIDO


# ---------------------------------------------------------------------------
# Pedido de matriz
# ---------------------------------------------------------------------------
def pedir_matriz(coordenadas, sources=None, destinations=None):
    """
    Pede uma matriz de tempos e distâncias ao motor configurado.

    Parâmetros:
        coordenadas (list[tuple]): lista de (longitude, latitude).
        sources (list[int] ou None): índices das origens; None = todas.
        destinations (list[int] ou None): índices dos destinos; None = todos.

    Devolve:
        dict: no formato comum descrito no início deste ficheiro.

    Erros:
        RuntimeError se o pedido falhar em todas as tentativas.
    """
    if motor_em_uso() == "ors":
        return _pedir_matriz_ors(coordenadas, sources, destinations)
    return _pedir_matriz_osrm(coordenadas, sources, destinations)


def _pedir_matriz_ors(coordenadas, sources, destinations):
    """Implementação para o OpenRouteService (ver pedir_matriz)."""
    corpo = {"locations": [[round(lon, 6), round(lat, 6)] for lon, lat in coordenadas],
             "metrics": ["duration", "distance"], "units": "m"}
    if sources is not None:
        corpo["sources"] = list(sources)
    if destinations is not None:
        corpo["destinations"] = list(destinations)
    cabecalhos = {"Authorization": ler_chave_ors(), "Content-Type": "application/json"}
    url = f"{config.ORS_URL}/v2/matrix/{config.ORS_PERFIL}"

    ultimo_erro = None
    for tentativa in range(1, config.OSRM_TENTATIVAS + 1):
        try:
            resposta = requests.post(url, json=corpo, headers=cabecalhos, timeout=300)
            restantes = resposta.headers.get("X-Ratelimit-Remaining")
            if resposta.status_code == 429:
                raise requests.RequestException("quota/limite de pedidos atingido (429)")
            if resposta.status_code in (401, 403):
                raise RuntimeError("Chave do OpenRouteService inválida ou sem permissão (erro "
                                   f"{resposta.status_code}).")
            if resposta.status_code != 200:
                raise requests.RequestException(f"erro {resposta.status_code}: {resposta.text[:200]}")
            dados = resposta.json()
            time.sleep(config.ORS_PAUSA_ENTRE_PEDIDOS_S)
            if restantes is not None and int(restantes) < 5:
                mensagem(f"      AVISO: restam {restantes} pedidos de matriz na quota do OpenRouteService.")
            # Converter para o formato comum (igual ao do OSRM)
            def pontos(lista):
                return [{"location": (p or {}).get("location"), "distance": (p or {}).get("snapped_distance")}
                        for p in lista]
            return {"durations": dados["durations"], "distances": dados["distances"],
                    "sources": pontos(dados["sources"]), "destinations": pontos(dados["destinations"])}
        except (requests.RequestException, ValueError, KeyError) as erro:
            ultimo_erro = erro
            espera = 5 * 2 ** tentativa
            mensagem(f"      ERRO no OpenRouteService ({tentativa}/{config.OSRM_TENTATIVAS}): {erro}. "
                     f"Nova tentativa em {espera} s.")
            time.sleep(espera)
    raise RuntimeError(f"Falha definitiva no OpenRouteService: {ultimo_erro}")


def _pedir_matriz_osrm(coordenadas, sources, destinations):
    """Implementação para o OSRM (ver pedir_matriz)."""
    texto = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coordenadas)
    url = f"{config.OSRM_URL}/table/v1/{config.OSRM_PERFIL}/{texto}"
    parametros = {"annotations": "duration,distance"}
    if sources is not None:
        parametros["sources"] = ";".join(map(str, sources))
    if destinations is not None:
        parametros["destinations"] = ";".join(map(str, destinations))

    ultimo_erro = None
    for tentativa in range(1, config.OSRM_TENTATIVAS + 1):
        try:
            resposta = requests.get(url, params=parametros, timeout=config.OSRM_TIMEOUT_S,
                                    headers=config.CABECALHOS_HTTP)
            if resposta.status_code == 429:
                raise requests.RequestException("demasiados pedidos (429)")
            dados = resposta.json()
            if dados.get("code") != "Ok":
                raise requests.RequestException(f"OSRM respondeu {dados.get('code')}: {dados.get('message')}")
            time.sleep(config.OSRM_PAUSA_ENTRE_PEDIDOS_S)
            return dados
        except (requests.RequestException, ValueError) as erro:
            ultimo_erro = erro
            espera = 2 ** tentativa
            mensagem(f"      ERRO na API OSRM ({tentativa}/{config.OSRM_TENTATIVAS}): {erro}. "
                     f"Nova tentativa em {espera} s.")
            time.sleep(espera)
    raise RuntimeError(f"Falha definitiva no OSRM: {ultimo_erro}")


# ---------------------------------------------------------------------------
# Estrada mais próxima (para pontos que o ORS não consegue ligar à rede)
# ---------------------------------------------------------------------------
def ponto_mais_proximo_na_estrada(longitude, latitude):
    """
    Encontra o ponto da rede rodoviária (OpenStreetMap) mais próximo de um local.

    O OpenRouteService só liga um ponto à rede se houver uma estrada a menos de
    ~350 m. Para os poucos centroides mais afastados (zonas rurais), pede-se ao
    OSRM (que procura sem limite) o ponto da estrada mais próxima e recalcula-se.

    Parâmetros:
        longitude, latitude (float): local original.

    Devolve:
        tuple (lon, lat, distancia_m) ou None se falhar.
    """
    url = f"{config.OSRM_URL}/nearest/v1/{config.OSRM_PERFIL}/{longitude:.6f},{latitude:.6f}"
    try:
        dados = requests.get(url, timeout=30, headers=config.CABECALHOS_HTTP).json()
        ponto = dados["waypoints"][0]
        time.sleep(config.OSRM_PAUSA_ENTRE_PEDIDOS_S)
        return ponto["location"][0], ponto["location"][1], ponto.get("distance", 0)
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Desenho de um percurso (para os mapas)
# ---------------------------------------------------------------------------
def obter_percurso(origem, destino):
    """
    Devolve o desenho do percurso mais rápido entre dois pontos (só para mapas).

    Parâmetros:
        origem, destino (tuple): (latitude, longitude).

    Devolve:
        list[list[float]] ou None: pontos [lat, lon] do percurso.
    """
    try:
        if motor_em_uso() == "ors":
            resposta = requests.post(
                f"{config.ORS_URL}/v2/directions/{config.ORS_PERFIL}/geojson",
                json={"coordinates": [[origem[1], origem[0]], [destino[1], destino[0]]]},
                headers={"Authorization": ler_chave_ors(), "Content-Type": "application/json"}, timeout=60)
            coordenadas = resposta.json()["features"][0]["geometry"]["coordinates"]
            time.sleep(config.ORS_PAUSA_ENTRE_PEDIDOS_S)
        else:
            resposta = requests.get(
                f"{config.OSRM_URL}/route/v1/{config.OSRM_PERFIL}/{origem[1]},{origem[0]};{destino[1]},{destino[0]}",
                params={"overview": "full", "geometries": "geojson"}, timeout=60, headers=config.CABECALHOS_HTTP)
            coordenadas = resposta.json()["routes"][0]["geometry"]["coordinates"]
            time.sleep(config.OSRM_PAUSA_ENTRE_PEDIDOS_S)
        return [[lat, lon] for lon, lat in coordenadas]
    except (requests.RequestException, ValueError, KeyError, IndexError) as erro:
        mensagem(f"   (Não foi possível desenhar o percurso: {erro})")
        return None
