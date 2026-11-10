"""
ETAPA 1 — Descarregar os dados oficiais do INE (BGRI 2021 + Censos 2021)
=========================================================================

OBJETIVO
--------
Obter, automaticamente e diretamente do portal do INE, os ficheiros oficiais:

  1. BGRI 2021 (GeoPackage) — polígonos das subsecções estatísticas
     (referência geográfica principal). Cada ficheiro regional também traz
     as variáveis dos Censos 2021 associadas a cada polígono.
  2. Ficheiro Síntese dos Censos 2021 por SUBSECÇÃO (Excel) — referência
     estatística da população residente (resultados definitivos), com as
     designações do município e da freguesia.
  3. Ficheiro Síntese por SECÇÃO (Excel) — só é usado se faltar informação
     ao nível da subsecção (nível geográfico imediatamente superior).
  4. Dicionário de variáveis (CSV) — confirma o significado de cada coluna.

COMO FUNCIONA
-------------
  a) Lê a página de downloads do INE e procura, no seu código HTML, os
     endereços dos ficheiros (assim, não inventamos endereços).
  b) Descarrega cada ficheiro para dados/entrada/ (se ainda não existir).
  c) Descompacta os ficheiros .zip.
  d) Regista a data de recolha, os URL e a "impressão digital" (SHA-256)
     de cada ficheiro em registo/metadados_execucao.json.

EXECUTAR SÓ ESTA ETAPA
----------------------
    python etapa_01_descarregar_dados_ine.py
"""

import re
import zipfile
from datetime import datetime

import requests

import config
from utilitarios import (calcular_sha256, descarregar_ficheiro, mensagem,
                         registar_metadados)


def obter_links_da_pagina_ine():
    """
    Lê a página de downloads do INE e extrai os endereços dos ficheiros .zip
    da BGRI 2021 e do Ficheiro Síntese.

    Devolve:
        tuple (str, list[str]): o URL da página que respondeu e a lista de
        caminhos relativos encontrados (ex.: "download/filesGPG/2021/...zip").
        Se nenhuma página responder, devolve (None, []).
    """
    for url_pagina in config.INE_PAGINAS_DOWNLOAD:
        try:
            mensagem(f"   A ler a página do INE: {url_pagina}")
            resposta = requests.get(url_pagina, timeout=60,
                                    headers=config.CABECALHOS_HTTP)
            if resposta.status_code != 200:
                mensagem(f"   A página respondeu com o código "
                         f"{resposta.status_code}; a tentar a seguinte.")
                continue
            # Procura textos do tipo  'download/filesGPG/2021/....zip'
            # ou '2021FicheiroSintese/....zip' dentro do HTML.
            padrao = r"(download/filesGPG/2021/[\w/]+\.zip|2021FicheiroSintese/[\w]+\.zip)"
            links = sorted(set(re.findall(padrao, resposta.text)))
            if links:
                mensagem(f"   Encontrados {len(links)} ficheiros na página.")
                return url_pagina, links
        except requests.RequestException as erro:
            mensagem(f"   ERRO ao ler {url_pagina}: {erro}")
    return None, []


def escolher_ficheiros_a_descarregar(links):
    """
    Escolhe, da lista de links do INE, os ficheiros necessários ao estudo.

    Parâmetros:
        links (list[str]): caminhos relativos encontrados na página do INE.

    Devolve:
        dict: {nome_curto: caminho_relativo} dos ficheiros a descarregar.
    """
    escolhidos = {}
    for regiao in config.REGIOES_BGRI_NUTS2:
        procurado = f"download/filesGPG/2021/nuts2/BGRI21_{regiao}.zip"
        if procurado in links:
            escolhidos[f"BGRI21_{regiao}"] = procurado
        else:
            # O link não apareceu na página: usa-se o padrão de nomes
            # observado no portal do INE e regista-se o aviso.
            mensagem(f"   AVISO: {procurado} não consta da página; "
                     "a tentar o endereço pelo padrão habitual do INE.")
            escolhidos[f"BGRI21_{regiao}"] = procurado

    for nome, caminho in [("FS_SUBSECCAO", config.INE_FICHEIRO_SINTESE_SUBSECCAO),
                          ("FS_SECCAO", config.INE_FICHEIRO_SINTESE_SECCAO)]:
        if caminho not in links:
            mensagem(f"   AVISO: {caminho} não consta da página; "
                     "a tentar o endereço habitual.")
        escolhidos[nome] = caminho

    escolhidos["DICIONARIO"] = config.INE_DICIONARIO_VARIAVEIS
    return escolhidos


def descompactar(caminho_zip):
    """
    Descompacta um ficheiro .zip para uma pasta com o mesmo nome.

    Parâmetros:
        caminho_zip (Path): ficheiro .zip.

    Devolve:
        list[dict]: nome, tamanho e data interna de cada ficheiro extraído.
    """
    pasta_destino = caminho_zip.with_suffix("")
    pasta_destino.mkdir(exist_ok=True)
    conteudo = []
    with zipfile.ZipFile(caminho_zip) as arquivo:
        for info in arquivo.infolist():
            # Os ficheiros do INE foram compactados em Windows e os nomes com
            # acentos (ex.: "Secção") vêm na codificação antiga CP850.
            # O Python lê-os como CP437; corrigimos para obter o nome certo.
            nome_correto = info.filename
            if not info.flag_bits & 0x800:  # 0x800 = nome já está em UTF-8
                try:
                    nome_correto = info.filename.encode("cp437").decode("cp850")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            destino = pasta_destino / nome_correto
            if not destino.exists():
                with arquivo.open(info) as origem, open(destino, "wb") as saida:
                    saida.write(origem.read())
            conteudo.append({
                "ficheiro": nome_correto,
                "tamanho_bytes": info.file_size,
                "data_no_zip": datetime(*info.date_time).isoformat(),
            })
    return conteudo


def executar_etapa_1():
    """
    Executa a etapa 1 completa: encontra, descarrega e descompacta os
    ficheiros do INE e regista os metadados.

    Devolve:
        dict: {nome_curto: pasta_descompactada} para uso nas etapas seguintes.
    """
    mensagem("=" * 70)
    mensagem("ETAPA 1 — Descarregar dados oficiais do INE (BGRI 2021 / Censos 2021)")
    mensagem("=" * 70)

    pagina, links = obter_links_da_pagina_ine()
    if not links:
        mensagem("   AVISO: não foi possível ler a página do INE. "
                 "Serão usados os endereços habituais (padrão do portal).")
    ficheiros = escolher_ficheiros_a_descarregar(links)

    registo_fontes = []
    pastas = {}
    for nome_curto, caminho_relativo in ficheiros.items():
        url = config.INE_URL_BASE + caminho_relativo
        destino = config.PASTA_ENTRADA / caminho_relativo.split("/")[-1]
        try:
            descarregar_ficheiro(url, destino)
        except RuntimeError as erro:
            if nome_curto == "FS_SECCAO":
                # O ficheiro por secção é apenas um recurso de reserva.
                mensagem(f"   AVISO: {erro} (ficheiro de reserva; continua-se)")
                continue
            raise
        informacao = {
            "nome": nome_curto,
            "url": url,
            "ficheiro_local": str(destino.relative_to(config.PASTA_PROJETO)),
            "tamanho_bytes": destino.stat().st_size,
            "sha256": calcular_sha256(destino),
        }
        if destino.suffix == ".zip":
            informacao["conteudo"] = descompactar(destino)
            pastas[nome_curto] = destino.with_suffix("")
        else:
            pastas[nome_curto] = destino
        registo_fontes.append(informacao)

    registar_metadados("etapa_01_fontes_ine", {
        "data_recolha": datetime.now().isoformat(timespec="seconds"),
        "pagina_download_utilizada": pagina,
        "fonte": "INE — Censos 2021 (resultados definitivos) e BGRI 2021",
        "ficheiros": registo_fontes,
    })
    mensagem("ETAPA 1 concluída. Ficheiros em: dados/entrada/")
    return pastas


if __name__ == "__main__":
    executar_etapa_1()
