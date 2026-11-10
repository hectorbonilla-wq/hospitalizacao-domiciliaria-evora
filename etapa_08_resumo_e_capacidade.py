"""
ETAPA 8 — Resumo dos resultados e cenário de capacidade operacional
====================================================================

OBJETIVO
--------
  1. Calcular os indicadores principais do estudo:
       * nº total de subsecções analisadas, elegíveis e não elegíveis;
       * população total analisada e população nas subsecções elegíveis;
       * percentagem de cobertura;
       * estatísticas de tempos e distâncias de viagem.
  2. Mostrar a sensibilidade do resultado ao limite de tempo (27, 30, 33 min...).
  3. Calcular um CENÁRIO ILUSTRATIVO de capacidade operacional diária.

ATENÇÃO — DUAS COISAS DIFERENTES
--------------------------------
  * POPULAÇÃO GEOGRAFICAMENTE ELEGÍVEL: residentes que vivem a ≤ 30 min do
    hospital. É um resultado do estudo, baseado em dados observados (Censos)
    e em tempos calculados (OSRM).
  * CAPACIDADE OPERACIONAL: nº de doentes que as equipas conseguem visitar
    por dia. Depende de pressupostos (nº de equipas, viaturas, duração das
    visitas...) definidos em config.py. NÃO é um dado observado.
  A primeira é muitíssimo maior do que a segunda: só uma pequena fração dos
  residentes precisará, num dado dia, de hospitalização domiciliária.

RESULTADOS
----------
    resultados/relatorios/resumo_resultados.md   (texto legível)
    resultados/relatorios/resumo_resultados.json (para outros programas)
    resultados/relatorios/sensibilidade_limite_tempo.csv
    resultados/relatorios/populacao_elegivel_por_municipio.csv

EXECUTAR SÓ ESTA ETAPA (depois da etapa 5)
------------------------------------------
    python etapa_08_resumo_e_capacidade.py
"""

import json
import math

import numpy as np
import pandas as pd

import config
from utilitarios import ler_metadados, mensagem, registar_metadados, verificar_ficheiro_existe


def media_ponderada(valores, pesos):
    """
    Média ponderada (ex.: tempo médio "por residente").

    Parâmetros:
        valores (Series): valores a resumir (ex.: tempos).
        pesos (Series): pesos (ex.: população residente).

    Devolve:
        float: média ponderada, ou NaN se a soma dos pesos for zero.
    """
    validos = valores.notna()
    if pesos[validos].sum() == 0:
        return float("nan")
    return float(np.average(valores[validos], weights=pesos[validos]))


def estatisticas(serie, pesos):
    """
    Resume uma coluna numérica (mínimo, mediana, média, máximo, média ponderada).

    Parâmetros:
        serie (Series): valores (tempos ou distâncias).
        pesos (Series): população residente, para a média ponderada.

    Devolve:
        dict: estatísticas arredondadas a 2 casas decimais.
    """
    return {"minimo": round(float(serie.min()), 2), "mediana": round(float(serie.median()), 2),
            "media": round(float(serie.mean()), 2), "maximo": round(float(serie.max()), 2),
            "media_ponderada_pela_populacao": round(media_ponderada(serie, pesos), 2)}


def calcular_indicadores(tabela):
    """
    Calcula os indicadores principais do estudo.

    Parâmetros:
        tabela (DataFrame): tabela individual da etapa 5.

    Devolve:
        dict: indicadores (contagens, população, percentagem, estatísticas).
    """
    elegiveis = tabela[tabela["elegibilidade"] == "elegível"]
    nao_elegiveis = tabela[tabela["elegibilidade"] != "elegível"]
    sem_rota = tabela[tabela["tempo_hospital_domicilio_min"].isna()]
    populacao_total = int(tabela["populacao_residente"].sum())
    populacao_elegivel = int(elegiveis["populacao_residente"].sum())
    return {
        "subseccoes_analisadas": len(tabela),
        "subseccoes_elegiveis": len(elegiveis),
        "subseccoes_nao_elegiveis": len(nao_elegiveis),
        "subseccoes_sem_tempo_calculado": len(sem_rota),
        "populacao_sem_tempo_calculado": int(sem_rota["populacao_residente"].sum()),
        "subseccoes_elegiveis_com_populacao": int((elegiveis["populacao_residente"] > 0).sum()),
        "populacao_total_analisada": populacao_total,
        "populacao_residente_abrangida": populacao_elegivel,
        "percentagem_populacao_abrangida": round(100 * populacao_elegivel / populacao_total, 2),
        "subseccoes_proximas_do_limite_27_33min": int(tabela["proximo_do_limite"].sum()),
        "populacao_proxima_do_limite_27_33min": int(
            tabela.loc[tabela["proximo_do_limite"], "populacao_residente"].sum()),
        "tempo_hospital_domicilio_elegiveis_min": estatisticas(
            elegiveis["tempo_hospital_domicilio_min"], elegiveis["populacao_residente"]),
        "tempo_domicilio_hospital_elegiveis_min": estatisticas(
            elegiveis["tempo_domicilio_hospital_min"], elegiveis["populacao_residente"]),
        "distancia_hospital_domicilio_elegiveis_km": estatisticas(
            elegiveis["distancia_hospital_domicilio_km"], elegiveis["populacao_residente"]),
        "distancia_domicilio_hospital_elegiveis_km": estatisticas(
            elegiveis["distancia_domicilio_hospital_km"], elegiveis["populacao_residente"]),
        "tempo_hospital_domicilio_todas_min": estatisticas(
            tabela["tempo_hospital_domicilio_min"], tabela["populacao_residente"]),
        "distancia_hospital_domicilio_todas_km": estatisticas(
            tabela["distancia_hospital_domicilio_km"], tabela["populacao_residente"]),
    }


def analisar_sensibilidade(tabela, limites=(20, 25, 27, 30, 33, 35, 40, 45)):
    """
    Mostra como a população abrangida muda se o limite de tempo mudar.

    Útil para perceber o peso das subsecções perto dos 30 minutos.

    Parâmetros:
        tabela (DataFrame): tabela individual.
        limites (tuple): limites de tempo a testar (minutos).

    Devolve:
        DataFrame: uma linha por limite.
    """
    total = tabela["populacao_residente"].sum()
    linhas = []
    for limite in limites:
        dentro = tabela["tempo_hospital_domicilio_min"] <= limite
        populacao = int(tabela.loc[dentro, "populacao_residente"].sum())
        linhas.append({"limite_min": limite, "subseccoes_elegiveis": int(dentro.sum()),
                       "populacao_abrangida": populacao,
                       "percentagem_populacao_analisada": round(100 * populacao / total, 2)})
    return pd.DataFrame(linhas)


def calcular_capacidade_operacional(indicadores):
    """
    CENÁRIO ILUSTRATIVO: quantos doentes as equipas conseguem visitar por dia.

    Modelo simples de um circuito diário de uma equipa:
        hospital → doente 1 → doente 2 → ... → doente n → hospital
    Tempo total = ida + n × duração da visita + (n − 1) × deslocação entre
                  visitas + regresso  ≤  minutos do turno
    Resolvendo em ordem a n:
        n = (turno − ida − regresso + entre) ÷ (duração + entre)   (arredondado para baixo)

    São calculados dois casos: tempos médios (por residente elegível) e o pior
    caso (domicílio no limite dos 30 min).

    Parâmetros:
        indicadores (dict): resultado de calcular_indicadores().

    Devolve:
        dict: pressupostos usados e resultados do cenário.
    """
    # Cada equipa precisa de uma viatura; uma viatura de 5 lugares (com o
    # condutor) transporta fisicamente até 2 equipas de 2 pessoas, mas então
    # as duas equipas teriam de fazer o mesmo circuito. Assume-se 1 viatura/equipa.
    equipas_operacionais = min(config.CAPACIDADE_NUMERO_EQUIPAS, config.CAPACIDADE_VIATURAS_DISPONIVEIS)
    lugares_ocupados = config.CAPACIDADE_PESSOAS_POR_EQUIPA
    if lugares_ocupados > config.CAPACIDADE_LUGARES_POR_VIATURA:
        raise ValueError("A equipa não cabe na viatura: reveja os pressupostos em config.py.")

    duracao = config.CAPACIDADE_DURACAO_VISITA_MIN
    entre = config.CAPACIDADE_TEMPO_ENTRE_VISITAS_MIN
    turno = config.CAPACIDADE_MINUTOS_TURNO

    def visitas_possiveis(ida, regresso):
        """Nº máximo de visitas num turno, para uma equipa (função interna)."""
        n = (turno - ida - regresso + entre) / (duracao + entre)
        return max(0, math.floor(n))

    ida_media = indicadores["tempo_hospital_domicilio_elegiveis_min"]["media_ponderada_pela_populacao"]
    regresso_medio = indicadores["tempo_domicilio_hospital_elegiveis_min"]["media_ponderada_pela_populacao"]
    cenarios = {}
    for nome, ida, regresso in [("tempos_medios", ida_media, regresso_medio),
                                ("pior_caso_30min", config.LIMITE_TEMPO_MINUTOS, config.LIMITE_TEMPO_MINUTOS)]:
        visitas_equipa = visitas_possiveis(ida, regresso)
        visitas_dia = visitas_equipa * equipas_operacionais
        cenarios[nome] = {
            "tempo_ida_usado_min": round(ida, 1), "tempo_regresso_usado_min": round(regresso, 1),
            "visitas_por_equipa_dia": visitas_equipa,
            "visitas_totais_dia": visitas_dia,
            "doentes_acompanhados_em_simultaneo": visitas_dia // config.CAPACIDADE_VISITAS_POR_DOENTE_DIA,
        }
    return {
        "natureza": "CENÁRIO ILUSTRATIVO baseado em pressupostos — não é um dado observado",
        "pressupostos": {
            "equipas": config.CAPACIDADE_NUMERO_EQUIPAS,
            "composicao_equipa": "1 médico + 1 enfermeiro",
            "viaturas": config.CAPACIDADE_VIATURAS_DISPONIVEIS,
            "lugares_por_viatura_incluindo_condutor": config.CAPACIDADE_LUGARES_POR_VIATURA,
            "equipas_operacionais": equipas_operacionais,
            "minutos_turno": turno, "duracao_visita_min": duracao,
            "deslocacao_entre_visitas_min": entre,
            "visitas_por_doente_dia": config.CAPACIDADE_VISITAS_POR_DOENTE_DIA,
        },
        "cenarios": cenarios,
    }


def escrever_resumo_markdown(indicadores, sensibilidade, capacidade, por_municipio):
    """
    Escreve o resumo legível em Markdown (abre-se em qualquer editor de texto).

    Parâmetros:
        indicadores (dict), sensibilidade (DataFrame), capacidade (dict),
        por_municipio (DataFrame): resultados das outras funções.

    Devolve:
        Path: ficheiro criado.
    """
    def numero(valor):
        return f"{valor:,}".replace(",", " ")

    metadados = ler_metadados()
    fontes = metadados.get("etapa_01_fontes_ine", {})
    routing = metadados.get("etapa_03_routing", {})
    isocrona = metadados.get("etapa_06_isocrona", {})
    t = indicadores["tempo_hospital_domicilio_elegiveis_min"]
    tr = indicadores["tempo_domicilio_hospital_elegiveis_min"]
    d = indicadores["distancia_hospital_domicilio_elegiveis_km"]
    dr = indicadores["distancia_domicilio_hospital_elegiveis_km"]
    cm = capacidade["cenarios"]["tempos_medios"]
    cp = capacidade["cenarios"]["pior_caso_30min"]

    linhas = [
        "# Resumo — População potencialmente abrangida pela Hospitalização Domiciliária",
        "",
        f"**Hospital:** {config.HOSPITAL_NOME}  ",
        f"**Morada:** {config.HOSPITAL_MORADA}  ",
        f"**Coordenadas:** {config.HOSPITAL_LATITUDE}, {config.HOSPITAL_LONGITUDE} "
        "(38º34'07.99\" N, 7º54'11.44\" W)  ",
        f"**Critério:** tempo de viagem de automóvel hospital → domicílio ≤ "
        f"{config.LIMITE_TEMPO_MINUTOS} min  ",
        "**Âmbito territorial:** apenas Portugal (subsecções da BGRI 2021)",
        "",
        "## 1. Resultados principais (dados observados + tempos calculados)",
        "",
        "| Indicador | Valor |",
        "|---|---:|",
        f"| Subsecções estatísticas analisadas | {numero(indicadores['subseccoes_analisadas'])} |",
        f"| Subsecções elegíveis (≤ {config.LIMITE_TEMPO_MINUTOS} min) | {numero(indicadores['subseccoes_elegiveis'])} |",
        f"| Subsecções não elegíveis | {numero(indicadores['subseccoes_nao_elegiveis'])} |",
        f"| Subsecções sem tempo calculado (incluídas nas não elegíveis) | {indicadores['subseccoes_sem_tempo_calculado']} |",
        f"| População residente total analisada (Censos 2021) | {numero(indicadores['populacao_total_analisada'])} |",
        f"| **População residente abrangida (subsecções elegíveis)** | **{numero(indicadores['populacao_residente_abrangida'])}** |",
        f"| **Percentagem da população analisada abrangida** | **{indicadores['percentagem_populacao_abrangida']} %** |",
        f"| Subsecções próximas do limite (27–33 min) | {numero(indicadores['subseccoes_proximas_do_limite_27_33min'])} |",
        f"| População nas subsecções próximas do limite | {numero(indicadores['populacao_proxima_do_limite_27_33min'])} |",
        "",
        "Nota: a \"população total analisada\" é a de todas as subsecções com centroide a ≤ "
        f"{config.RAIO_PRE_SELECAO_KM:.0f} km em linha reta; a percentagem depende desta escolha.",
        "",
        "## 2. Tempos e distâncias de viagem (subsecções elegíveis)",
        "",
        "| Medida | Mínimo | Mediana | Média | Máximo | Média por residente |",
        "|---|---:|---:|---:|---:|---:|",
        f"| Tempo hospital → domicílio (min) | {t['minimo']} | {t['mediana']} | {t['media']} | {t['maximo']} | {t['media_ponderada_pela_populacao']} |",
        f"| Tempo domicílio → hospital (min) | {tr['minimo']} | {tr['mediana']} | {tr['media']} | {tr['maximo']} | {tr['media_ponderada_pela_populacao']} |",
        f"| Distância hospital → domicílio (km) | {d['minimo']} | {d['mediana']} | {d['media']} | {d['maximo']} | {d['media_ponderada_pela_populacao']} |",
        f"| Distância domicílio → hospital (km) | {dr['minimo']} | {dr['mediana']} | {dr['media']} | {dr['maximo']} | {dr['media_ponderada_pela_populacao']} |",
        "",
        "## 3. Sensibilidade ao limite de tempo",
        "",
        "| Limite (min) | Subsecções | População abrangida | % da população analisada |",
        "|---:|---:|---:|---:|",
    ]
    for _, linha in sensibilidade.iterrows():
        linhas.append(f"| {int(linha['limite_min'])} | {numero(int(linha['subseccoes_elegiveis']))} | "
                      f"{numero(int(linha['populacao_abrangida']))} | {linha['percentagem_populacao_analisada']} % |")
    if isocrona.get("populacao_centroides_dentro_isocrona_valhalla") is not None:
        linhas += ["", "**Comparação entre motores de routing (sensibilidade):** a população com "
                   "centroide dentro da isócrona de 30 min do Valhalla é "
                   f"{numero(isocrona['populacao_centroides_dentro_isocrona_valhalla'])} residentes "
                   f"(OSRM: {numero(indicadores['populacao_residente_abrangida'])}). "
                   f"{isocrona.get('concordancia_centroides_elegiveis_percent')} % dos centroides "
                   "elegíveis segundo o OSRM estão dentro da isócrona do Valhalla. O Valhalla usa "
                   "velocidades mais prudentes; o resultado oficial do estudo é o do OSRM."]
    linhas += ["", "## 4. População elegível por município", "",
               "| Município | Subsecções elegíveis | População elegível | População analisada | % do município analisado |",
               "|---|---:|---:|---:|---:|"]
    for _, linha in por_municipio.iterrows():
        linhas.append(f"| {linha['municipio']} | {linha['subseccoes_elegiveis']} | "
                      f"{numero(linha['populacao_elegivel'])} | {numero(linha['populacao_analisada'])} | "
                      f"{linha['percentagem']} % |")
    p = capacidade["pressupostos"]
    linhas += [
        "", "## 5. Capacidade operacional — CENÁRIO ILUSTRATIVO (pressupostos, não dados)", "",
        "A população elegível **não** é o número de doentes que o serviço consegue acompanhar.",
        "O cenário seguinte usa os pressupostos editáveis em `config.py`:", "",
        f"* Equipas: {p['equipas']} ({p['composicao_equipa']}); viaturas: {p['viaturas']} "
        f"(ligeiras de {p['lugares_por_viatura_incluindo_condutor']} lugares, incluindo o condutor)",
        f"* Turno útil: {p['minutos_turno']} min; duração da visita: {p['duracao_visita_min']} min; "
        f"deslocação entre domicílios: {p['deslocacao_entre_visitas_min']} min; "
        f"visitas por doente/dia: {p['visitas_por_doente_dia']}", "",
        "| Caso | Ida (min) | Regresso (min) | Visitas/equipa/dia | Doentes acompanhados |",
        "|---|---:|---:|---:|---:|",
        f"| Tempos médios por residente elegível | {cm['tempo_ida_usado_min']} | {cm['tempo_regresso_usado_min']} | "
        f"{cm['visitas_por_equipa_dia']} | {cm['doentes_acompanhados_em_simultaneo']} |",
        f"| Pior caso (domicílio a 30 min) | {cp['tempo_ida_usado_min']} | {cp['tempo_regresso_usado_min']} | "
        f"{cp['visitas_por_equipa_dia']} | {cp['doentes_acompanhados_em_simultaneo']} |",
        "",
        "## 6. Fontes e reprodutibilidade", "",
        f"* População e geografia: INE — Censos 2021 (resultados definitivos), BGRI 2021; "
        f"recolha em {fontes.get('data_recolha', '?')} a partir de {fontes.get('pagina_download_utilizada', '?')}",
        f"* Routing: {routing.get('servico', '?')} em {routing.get('servidor', '?')}, perfil "
        f"\"{routing.get('perfil', '?')}\"; cálculo entre {routing.get('data_calculo_inicio', '?')} e "
        f"{routing.get('data_calculo_fim', '?')}; rede OpenStreetMap; sem trânsito em tempo real",
        f"* Isócrona: {isocrona.get('servico_isocrona', '?')} em {isocrona.get('servidor', '?')} "
        f"({isocrona.get('valhalla', {})}); recortada pelo território português",
        "* Metadados completos (SHA-256 dos ficheiros, parâmetros, versões): `registo/metadados_execucao.json`",
        "",
        "## 7. Limitações a ter em conta", "",
        "* **Centroides:** cada subsecção é representada pelo centro geométrico do polígono; os "
        "residentes não vivem todos nesse ponto. Subsecções perto dos 30 min (ver secção 3) podem "
        "ter parte dos domicílios dentro e parte fora do limite.",
        "* **Tempos de viagem:** estimados pelo OSRM em fluxo livre (sem trânsito, semáforos ou "
        "estacionamento); o tempo real tende a ser um pouco maior.",
        "* **Rede rodoviária:** OpenStreetMap pode ter estradas em falta ou mal classificadas.",
        "* **População:** residentes em 2021 (Censos); não inclui alterações posteriores.",
    ]
    destino = config.PASTA_RELATORIOS / "resumo_resultados.md"
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return destino


def executar_etapa_8():
    """
    Executa a etapa 8: indicadores, sensibilidade, capacidade e relatório.

    Devolve:
        dict: indicadores principais.
    """
    mensagem("=" * 70)
    mensagem("ETAPA 8 — Resumo dos resultados e capacidade operacional")
    mensagem("=" * 70)
    tabela = pd.read_csv(config.PASTA_TABELAS / "tabela_individual_subseccoes.csv",
                         sep=";", decimal=",", dtype={"id_subseccao": str})

    indicadores = calcular_indicadores(tabela)
    sensibilidade = analisar_sensibilidade(tabela)
    capacidade = calcular_capacidade_operacional(indicadores)

    tabela["elegivel"] = tabela["elegibilidade"] == "elegível"
    por_municipio = tabela.groupby("municipio").apply(
        lambda g: pd.Series({
            "subseccoes_elegiveis": int(g["elegivel"].sum()),
            "populacao_elegivel": int(g.loc[g["elegivel"], "populacao_residente"].sum()),
            "populacao_analisada": int(g["populacao_residente"].sum()),
        }), include_groups=False).reset_index()
    por_municipio["percentagem"] = (100 * por_municipio["populacao_elegivel"] /
                                    por_municipio["populacao_analisada"]).round(1)
    por_municipio = por_municipio[por_municipio["populacao_elegivel"] > 0].sort_values(
        "populacao_elegivel", ascending=False)

    opcoes = {"index": False, "encoding": "utf-8-sig", "sep": ";", "decimal": ","}
    sensibilidade.to_csv(config.PASTA_RELATORIOS / "sensibilidade_limite_tempo.csv", **opcoes)
    por_municipio.to_csv(config.PASTA_RELATORIOS / "populacao_elegivel_por_municipio.csv", **opcoes)
    resumo = {"indicadores": indicadores, "capacidade_operacional": capacidade,
              "sensibilidade": sensibilidade.to_dict(orient="records")}
    with open(config.PASTA_RELATORIOS / "resumo_resultados.json", "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)
    ficheiro_md = escrever_resumo_markdown(indicadores, sensibilidade, capacidade, por_municipio)

    # ---- Mostrar no ecrã ----
    n = lambda v: f"{v:,}".replace(",", " ")  # noqa: E731 (formatação de milhares)
    mensagem("-" * 70)
    mensagem(f"   Subsecções analisadas ............ {n(indicadores['subseccoes_analisadas'])}")
    mensagem(f"   Subsecções elegíveis ............. {n(indicadores['subseccoes_elegiveis'])}")
    mensagem(f"   Subsecções não elegíveis ......... {n(indicadores['subseccoes_nao_elegiveis'])}")
    mensagem(f"   População total analisada ........ {n(indicadores['populacao_total_analisada'])}")
    mensagem(f"   POPULAÇÃO ABRANGIDA (≤ 30 min) ... {n(indicadores['populacao_residente_abrangida'])}")
    mensagem(f"   Percentagem de cobertura ......... {indicadores['percentagem_populacao_abrangida']} %")
    t = indicadores["tempo_hospital_domicilio_elegiveis_min"]
    mensagem(f"   Tempo médio por residente elegível: {t['media_ponderada_pela_populacao']} min")
    mensagem(f"   Capacidade (cenário ilustrativo, tempos médios): "
             f"{capacidade['cenarios']['tempos_medios']['doentes_acompanhados_em_simultaneo']} doentes/dia")
    mensagem("-" * 70)
    registar_metadados("etapa_08_resumo", {"indicadores": indicadores, "capacidade": capacidade})
    mensagem(f"ETAPA 8 concluída. Resumo: {ficheiro_md.relative_to(config.PASTA_PROJETO)}")
    return indicadores


if __name__ == "__main__":
    verificar_ficheiro_existe(config.PASTA_TABELAS / "tabela_individual_subseccoes.csv",
                              "etapa_05_classificar_elegibilidade.py")
    executar_etapa_8()
