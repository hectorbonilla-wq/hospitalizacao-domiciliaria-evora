"""
utilitarios.py — Pequenas funções usadas por várias etapas
===========================================================

Aqui ficam funções simples e reutilizáveis:
  * escrever mensagens de progresso (no ecrã e no ficheiro de registo);
  * registar metadados (datas, versões, parâmetros) para reprodutibilidade;
  * descarregar ficheiros da Internet com novas tentativas em caso de erro;
  * calcular a "impressão digital" (SHA-256) de um ficheiro.
"""

import hashlib
import json
import time
from datetime import datetime

import requests

import config


def mensagem(texto):
    """
    Mostra uma mensagem de progresso no ecrã e guarda-a no ficheiro de registo.

    Parâmetros:
        texto (str): a mensagem a mostrar.

    Devolve:
        Nada. (A mensagem fica escrita em registo/execucao.log.)
    """
    hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{hora}] {texto}"
    print(linha, flush=True)
    config.PASTA_REGISTO.mkdir(parents=True, exist_ok=True)
    with open(config.FICHEIRO_LOG, "a", encoding="utf-8") as ficheiro:
        ficheiro.write(linha + "\n")


def ler_metadados():
    """
    Lê o ficheiro de metadados da execução (JSON).

    Devolve:
        dict: dicionário com os metadados já registados (vazio se não existir).
    """
    if config.FICHEIRO_METADADOS.exists():
        with open(config.FICHEIRO_METADADOS, encoding="utf-8") as ficheiro:
            return json.load(ficheiro)
    return {}


def registar_metadados(seccao, dados):
    """
    Acrescenta ou substitui uma secção no ficheiro de metadados.

    Cada etapa chama esta função para documentar o que fez (data de recolha,
    URL das fontes, parâmetros...). Assim, o estudo pode ser reproduzido.

    Parâmetros:
        seccao (str): nome da secção (ex.: "etapa_01_fontes_ine").
        dados (dict): informação a guardar nessa secção.

    Devolve:
        Nada.
    """
    metadados = ler_metadados()
    dados = dict(dados)
    dados["registado_em"] = datetime.now().isoformat(timespec="seconds")
    metadados[seccao] = dados
    config.PASTA_REGISTO.mkdir(parents=True, exist_ok=True)
    with open(config.FICHEIRO_METADADOS, "w", encoding="utf-8") as ficheiro:
        json.dump(metadados, ficheiro, ensure_ascii=False, indent=2)


def calcular_sha256(caminho_ficheiro):
    """
    Calcula o código SHA-256 de um ficheiro (uma espécie de "impressão digital").

    Se o INE alterar um ficheiro, o código muda; serve para confirmar que
    duas pessoas usaram exatamente os mesmos dados.

    Parâmetros:
        caminho_ficheiro (Path): ficheiro a analisar.

    Devolve:
        str: código hexadecimal com 64 caracteres.
    """
    resumo = hashlib.sha256()
    with open(caminho_ficheiro, "rb") as ficheiro:
        for bloco in iter(lambda: ficheiro.read(1024 * 1024), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def descarregar_ficheiro(url, destino, tentativas=4):
    """
    Descarrega um ficheiro da Internet, com novas tentativas se a ligação falhar.

    Se o ficheiro já existir na pasta de destino, NÃO é descarregado outra vez
    (poupa tempo; apague o ficheiro se quiser forçar um novo download).

    Parâmetros:
        url (str): endereço do ficheiro.
        destino (Path): caminho onde o ficheiro será guardado.
        tentativas (int): número máximo de tentativas.

    Devolve:
        Path: o caminho do ficheiro descarregado.

    Erros:
        RuntimeError se todas as tentativas falharem.
    """
    if destino.exists() and destino.stat().st_size > 0:
        mensagem(f"   Já existe, não é descarregado de novo: {destino.name}")
        return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    ficheiro_temporario = destino.with_suffix(destino.suffix + ".parcial")

    for tentativa in range(1, tentativas + 1):
        try:
            mensagem(f"   A descarregar ({tentativa}/{tentativas}): {url}")
            with requests.get(url, stream=True, timeout=120,
                              headers=config.CABECALHOS_HTTP) as resposta:
                resposta.raise_for_status()
                with open(ficheiro_temporario, "wb") as ficheiro:
                    for bloco in resposta.iter_content(chunk_size=1024 * 1024):
                        ficheiro.write(bloco)
            ficheiro_temporario.replace(destino)
            tamanho_mb = destino.stat().st_size / 1e6
            mensagem(f"   Concluído: {destino.name} ({tamanho_mb:.1f} MB)")
            return destino
        except requests.RequestException as erro:
            espera = 2 ** tentativa
            mensagem(f"   ERRO de ligação: {erro}. Nova tentativa em {espera} s.")
            time.sleep(espera)

    raise RuntimeError(
        f"Não foi possível descarregar {url} após {tentativas} tentativas. "
        "Verifique a ligação à Internet ou se o endereço do INE mudou."
    )


def verificar_ficheiro_existe(caminho, etapa_anterior):
    """
    Confirma que um ficheiro produzido por uma etapa anterior existe.

    Parâmetros:
        caminho (Path): ficheiro necessário.
        etapa_anterior (str): nome do script que o cria (para a mensagem).

    Erros:
        FileNotFoundError com uma explicação clara, se o ficheiro não existir.
    """
    if not caminho.exists():
        raise FileNotFoundError(
            f"Ficheiro em falta: {caminho}\n"
            f"Execute primeiro: python {etapa_anterior}"
        )
