"""
ETAPA 2 — Preparar a tabela georreferenciada das subsecções estatísticas
=========================================================================

OBJETIVO
--------
Construir uma tabela com UMA linha por subsecção estatística da BGRI 2021,
contendo:
    * identificador da subsecção (código de 11 dígitos do INE, "SUBSECCAO");
    * designação territorial (freguesia e município);
    * população residente (Censos 2021, resultados definitivos);
    * centroide do polígono, em latitude e longitude (WGS84).

PASSOS
------
  a) Ler os polígonos das subsecções (GeoPackage da BGRI 2021).
  b) Calcular o centroide de cada polígono (no sistema PT-TM06, em metros).
  c) Pré-selecionar as subsecções a menos de 65 km em linha reta do hospital
     (limite físico explicado em config.py — não é um limite administrativo).
  d) Verificar se as regiões descarregadas cobrem todo o círculo de 65 km.
  e) Ler a população residente no Ficheiro Síntese (Excel) e associá-la a
     cada polígono pelo código da subsecção. Comparar com o valor que vem
     no próprio GeoPackage (controlo de qualidade).
  f) Se faltar população ao nível da subsecção, usar o nível imediatamente
     superior (secção estatística) e registar a mudança de resolução.
  g) Converter os centroides para latitude/longitude e validar coordenadas.
  h) Guardar o resultado em dados/processados/ e resultados/tabelas/.

LIMITAÇÃO IMPORTANTE — CENTROIDES
---------------------------------
O centroide é o "centro geométrico" do polígono. Usá-lo é uma APROXIMAÇÃO:
não significa que todos os residentes vivam nesse ponto. Em subsecções rurais
grandes, as casas podem estar longe do centroide, e o centroide pode até cair
fora do polígono (formas em "C") ou longe de qualquer estrada. A coluna
"centroide_dentro_poligono" assinala estes casos.

EXECUTAR SÓ ESTA ETAPA (depois da etapa 1)
------------------------------------------
    python etapa_02_preparar_subseccoes.py
"""

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

import config
from utilitarios import mensagem, registar_metadados, verificar_ficheiro_existe


def ponto_hospital_em_metros():
    """
    Converte as coordenadas do hospital (lat/lon) para o sistema PT-TM06.

    Devolve:
        shapely.Point: posição do hospital em metros (EPSG:3763).
    """
    serie = gpd.GeoSeries([Point(config.HOSPITAL_LONGITUDE, config.HOSPITAL_LATITUDE)],
                          crs=config.CRS_WGS84)
    return serie.to_crs(config.CRS_PORTUGAL).iloc[0]


def ler_poligonos_bgri():
    """
    Lê os polígonos das subsecções de todas as regiões descarregadas.

    Devolve:
        GeoDataFrame: uma linha por subsecção, com o código, os códigos
        administrativos, a população que consta do GeoPackage e a geometria.
    """
    colunas = ["SUBSECCAO", "DTMN21", "DTMNFR21", "DTMNFRSEC21", "SECSSNUM21",
               "NUTS2", "NUTS3", config.VARIAVEL_POPULACAO]
    partes = []
    for regiao in config.REGIOES_BGRI_NUTS2:
        pasta = config.PASTA_ENTRADA / f"BGRI21_{regiao}"
        ficheiros = list(pasta.glob("*.gpkg"))
        if not ficheiros:
            raise FileNotFoundError(
                f"Não encontrei o GeoPackage da região {regiao} em {pasta}.\n"
                "Execute primeiro: python etapa_01_descarregar_dados_ine.py")
        mensagem(f"   A ler polígonos: {ficheiros[0].name}")
        parte = gpd.read_file(ficheiros[0], columns=colunas)
        partes.append(parte)

    poligonos = pd.concat(partes, ignore_index=True)
    poligonos = gpd.GeoDataFrame(poligonos, geometry="geometry", crs=partes[0].crs)
    if str(poligonos.crs) != config.CRS_PORTUGAL:
        poligonos = poligonos.to_crs(config.CRS_PORTUGAL)

    # Pode haver subsecções repetidas se duas regiões se sobrepuserem.
    repetidas = poligonos["SUBSECCAO"].duplicated().sum()
    if repetidas:
        mensagem(f"   AVISO: {repetidas} subsecções repetidas foram removidas.")
        poligonos = poligonos.drop_duplicates("SUBSECCAO")

    poligonos = poligonos.rename(columns={config.VARIAVEL_POPULACAO: "populacao_bgri_gpkg"})
    mensagem(f"   Total de polígonos lidos: {len(poligonos):,}".replace(",", " "))
    return poligonos


def calcular_centroides(poligonos):
    """
    Calcula o centroide de cada polígono e a distância em linha reta ao hospital.

    Parâmetros:
        poligonos (GeoDataFrame): polígonos em EPSG:3763 (metros).

    Devolve:
        GeoDataFrame: o mesmo, com as colunas novas "centroide" (geometria),
        "centroide_dentro_poligono" (True/False) e "distancia_linha_reta_km".
    """
    poligonos = poligonos.copy()
    # O cálculo é feito em metros (PT-TM06), o que é geometricamente correto.
    poligonos["centroide"] = poligonos.geometry.centroid
    poligonos["centroide_dentro_poligono"] = poligonos["centroide"].within(poligonos.geometry)
    hospital = ponto_hospital_em_metros()
    poligonos["distancia_linha_reta_km"] = poligonos["centroide"].distance(hospital) / 1000
    return poligonos


def verificar_cobertura_do_circulo(poligonos):
    """
    Verifica se os polígonos descarregados cobrem todo o círculo de pré-seleção.

    Se faltar uma região portuguesa (por exemplo, se o círculo entrar numa
    região NUTS II que não foi descarregada), haverá "buracos" no círculo.

    Como interpretar os buracos: todo o território português a LESTE de Évora,
    até à fronteira, pertence ao Alentejo (região sempre descarregada). Logo,
    um buraco a leste do hospital só pode ser território espanhol (fora da
    BGRI). Um buraco a OESTE do hospital indica uma região portuguesa em falta.

    Parâmetros:
        poligonos (GeoDataFrame): todos os polígonos lidos.

    Devolve:
        dict: percentagem coberta, área em falta a leste (Espanha) e a oeste.
    """
    hospital = ponto_hospital_em_metros()
    circulo = hospital.buffer(config.RAIO_PRE_SELECAO_KM * 1000)
    candidatos = poligonos[poligonos.intersects(circulo)]
    config.PASTA_PROCESSADOS.mkdir(parents=True, exist_ok=True)
    # buffer(0.5) fecha pequenas fendas (meio metro) entre polígonos vizinhos
    area_portuguesa = candidatos.geometry.buffer(0.5).union_all()
    em_falta = gpd.GeoSeries([circulo.difference(area_portuguesa)],
                             crs=config.CRS_PORTUGAL).explode()
    em_falta = em_falta[em_falta.area > 100_000]  # ignorar lascas < 0,1 km²
    a_leste = em_falta[em_falta.centroid.x > hospital.x]
    a_oeste = em_falta[em_falta.centroid.x <= hospital.x]

    resultado = {
        "percentagem_circulo_coberta": round(100 * (1 - em_falta.area.sum() / circulo.area), 2),
        "area_em_falta_a_leste_km2_espanha": round(a_leste.area.sum() / 1e6, 1),
        "area_em_falta_a_oeste_km2": round(a_oeste.area.sum() / 1e6, 1),
    }
    # Guardar o território português da área de estudo (círculo + 5 km de
    # margem, porque o ponto de encaixe na estrada de um centroide junto ao
    # limite do círculo pode ficar ligeiramente fora dele). É usado para
    # recortar a isócrona e confirmar que todos os pontos estão em Portugal.
    circulo_com_margem = hospital.buffer((config.RAIO_PRE_SELECAO_KM + 5) * 1000)
    margem = poligonos[poligonos.intersects(circulo_com_margem)]
    territorio = margem.geometry.buffer(0.5).union_all().intersection(circulo_com_margem)
    gpd.GeoDataFrame({"descricao": ["Território português (BGRI 2021) na área de estudo + 5 km"]},
                     geometry=[territorio],
                     crs=config.CRS_PORTUGAL).to_file(config.FICHEIRO_TERRITORIO, driver="GPKG")

    mensagem(f"   Cobertura do círculo de {config.RAIO_PRE_SELECAO_KM:.0f} km: "
             f"{resultado['percentagem_circulo_coberta']} % "
             f"(em falta a leste — Espanha: {resultado['area_em_falta_a_leste_km2_espanha']} km²; "
             f"a oeste: {resultado['area_em_falta_a_oeste_km2']} km²)")
    if resultado["area_em_falta_a_oeste_km2"] > 0:
        mensagem("   AVISO: há território a oeste do hospital sem subsecções. Acrescente "
                 "regiões em config.REGIOES_BGRI_NUTS2 e repita as etapas 1 e 2.")
    else:
        mensagem("   OK: todo o território português dentro do círculo está coberto.")
    return resultado


def localizar_hospital(poligonos):
    """
    Confirma que o hospital está em território português, identificando a
    subsecção da BGRI 2021 onde as suas coordenadas caem.

    Parâmetros:
        poligonos (GeoDataFrame): todos os polígonos lidos.

    Devolve:
        str ou None: código da subsecção onde está o hospital.

    Erros:
        ValueError se o hospital não estiver dentro de nenhuma subsecção
        (coordenadas erradas, trocadas ou fora de Portugal).
    """
    hospital = ponto_hospital_em_metros()
    contem = poligonos[poligonos.contains(hospital)]
    if contem.empty:
        raise ValueError(
            "As coordenadas do hospital não caem em nenhuma subsecção da BGRI 2021 "
            f"(lat {config.HOSPITAL_LATITUDE}, lon {config.HOSPITAL_LONGITUDE}). "
            "Confirme em config.py: a longitude a Oeste deve ser NEGATIVA.")
    codigo = contem["SUBSECCAO"].iloc[0]
    mensagem(f"   OK: o hospital está em Portugal, na subsecção {codigo} "
             f"(município {contem['DTMN21'].iloc[0]}).")
    return codigo


def ler_ficheiro_sintese(nome_pasta, coluna_codigo):
    """
    Lê um Ficheiro Síntese dos Censos 2021 (Excel do INE).

    O Excel tem uma linha de título, seguida da linha com os nomes das colunas
    e depois linhas de totais (país, região, município...) e, por fim, as
    linhas de cada unidade. Ficamos só com as linhas da unidade pretendida.

    Como a leitura do Excel é lenta (1–3 minutos), o resultado é guardado
    numa cópia CSV em dados/processados/ e reutilizado nas execuções seguintes.

    Parâmetros:
        nome_pasta (str): pasta em dados/entrada/ (ex.: "FS2021SubSeccaoTot").
        coluna_codigo (str): "SUBSECCAO" ou "SECCAO".

    Devolve:
        DataFrame ou None: tabela com o código, as designações e a população
        residente; None se o ficheiro não existir.
    """
    copia_csv = config.PASTA_PROCESSADOS / f"{nome_pasta}.csv"
    if copia_csv.exists():
        mensagem(f"   A reutilizar a cópia já convertida: {copia_csv.name}")
        return pd.read_csv(copia_csv, dtype=str)

    ficheiros = list((config.PASTA_ENTRADA / nome_pasta).glob("*.xlsx"))
    if not ficheiros:
        return None

    mensagem(f"   A ler o Excel do INE (pode demorar 1–3 minutos): {ficheiros[0].name}")
    colunas = ["MUNICIPIO", "MUNICIPIO DSG", "FREGUESIA", "FREGUESIA DSG",
               "SECCAO", "SUBSECCAO", config.VARIAVEL_POPULACAO]
    tabela = pd.read_excel(ficheiros[0], header=1, dtype=str,
                           usecols=lambda nome: nome in colunas)
    # Guardar também os totais por município (linhas sem freguesia), que
    # servem para confirmar que a soma das subsecções bate certo.
    totais_municipio = tabela[tabela["MUNICIPIO"].notna() & tabela["FREGUESIA"].isna()]
    config.PASTA_PROCESSADOS.mkdir(parents=True, exist_ok=True)
    totais_municipio.to_csv(config.PASTA_PROCESSADOS / f"{nome_pasta}_totais_municipio.csv",
                            index=False)
    # Linhas da unidade pretendida: aquelas em que o código está preenchido.
    tabela = tabela[tabela[coluna_codigo].notna()]
    if coluna_codigo == "SECCAO":
        tabela = tabela[tabela["SUBSECCAO"].isna()]
    tabela.to_csv(copia_csv, index=False)
    return tabela


def associar_populacao(subseccoes):
    """
    Associa a população residente (Ficheiro Síntese, Censos 2021) a cada
    polígono, usando o código da subsecção como chave de ligação.

    Ordem de prioridade (sempre dados oficiais do INE, nunca estimativas):
        1. Ficheiro Síntese por subsecção (Excel);
        2. Atributo N_INDIVIDUOS do GeoPackage da BGRI 2021 (mesmo recenseamento);
        3. Nível superior: secção estatística (ver agregar_ao_nivel_seccao).

    Parâmetros:
        subseccoes (GeoDataFrame): polígonos pré-selecionados.

    Devolve:
        tuple (GeoDataFrame, dict): tabela com "populacao_residente",
        "fonte_populacao", designações; e um dicionário com o controlo de
        qualidade (diferenças entre fontes, valores em falta).
    """
    controlo = {}
    sintese = ler_ficheiro_sintese("FS2021SubSeccaoTot", "SUBSECCAO")

    if sintese is None:
        mensagem("   AVISO: Ficheiro Síntese por subsecção indisponível. "
                 "Será usada a população que consta do GeoPackage da BGRI 2021.")
        subseccoes["populacao_sintese"] = pd.NA
        subseccoes["MUNICIPIO DSG"] = pd.NA
        subseccoes["FREGUESIA DSG"] = pd.NA
    else:
        sintese = sintese.rename(columns={config.VARIAVEL_POPULACAO: "populacao_sintese"})
        sintese["populacao_sintese"] = pd.to_numeric(sintese["populacao_sintese"])
        subseccoes = subseccoes.merge(
            sintese[["SUBSECCAO", "populacao_sintese", "MUNICIPIO DSG", "FREGUESIA DSG"]],
            on="SUBSECCAO", how="left")

    # Escolher a fonte de população para cada subsecção
    subseccoes["populacao_residente"] = subseccoes["populacao_sintese"]
    subseccoes["fonte_populacao"] = "INE Censos 2021 — Ficheiro Síntese (subsecção)"
    sem_sintese = subseccoes["populacao_residente"].isna()
    subseccoes.loc[sem_sintese, "populacao_residente"] = subseccoes.loc[sem_sintese, "populacao_bgri_gpkg"]
    subseccoes.loc[sem_sintese, "fonte_populacao"] = "INE BGRI 2021 — atributo N_INDIVIDUOS (subsecção)"

    # Controlo de qualidade: as duas fontes oficiais devem coincidir.
    ambas = subseccoes["populacao_sintese"].notna() & subseccoes["populacao_bgri_gpkg"].notna()
    diferentes = ambas & (subseccoes["populacao_sintese"] != subseccoes["populacao_bgri_gpkg"])
    controlo["subseccoes_com_ambas_as_fontes"] = int(ambas.sum())
    controlo["subseccoes_com_valores_diferentes"] = int(diferentes.sum())
    controlo["subseccoes_sem_ficheiro_sintese"] = int(sem_sintese.sum())
    mensagem(f"   Controlo: {int(diferentes.sum())} subsecções com população diferente "
             f"entre o Ficheiro Síntese e o GeoPackage (esperado: 0).")

    em_falta = subseccoes["populacao_residente"].isna()
    controlo["subseccoes_sem_populacao"] = int(em_falta.sum())
    subseccoes["nivel_geografico"] = "subsecção estatística"
    if em_falta.any():
        mensagem(f"   AVISO: {int(em_falta.sum())} subsecções sem população. "
                 "A mudar para o nível da secção estatística nessas áreas.")
        subseccoes = agregar_ao_nivel_seccao(subseccoes)
    return subseccoes, controlo


def agregar_ao_nivel_seccao(subseccoes):
    """
    Plano de recurso: para cada secção estatística em que alguma subsecção não
    tem população, junta todas as subsecções dessa secção num único polígono e
    atribui-lhe a população oficial da SECÇÃO (Ficheiro Síntese por secção).

    Isto reduz a resolução espacial nessas zonas, mas evita inventar valores.
    A coluna "nivel_geografico" passa a "secção estatística" nessas linhas.

    Parâmetros:
        subseccoes (GeoDataFrame): tabela com "populacao_residente" em falta
        nalgumas linhas.

    Devolve:
        GeoDataFrame: tabela em que as linhas sem população foram substituídas
        por polígonos de secção (ou mantidas como "sem dados" se nem a secção
        tiver dados).
    """
    seccoes_afetadas = subseccoes.loc[subseccoes["populacao_residente"].isna(), "DTMNFRSEC21"].unique()
    sintese_seccao = ler_ficheiro_sintese("FS2021SeccaoTot", "SECCAO")
    populacao_seccao = {}
    if sintese_seccao is not None:
        populacao_seccao = dict(zip(sintese_seccao["SECCAO"],
                                    pd.to_numeric(sintese_seccao[config.VARIAVEL_POPULACAO])))

    manter = subseccoes[~subseccoes["DTMNFRSEC21"].isin(seccoes_afetadas)]
    agrupar = subseccoes[subseccoes["DTMNFRSEC21"].isin(seccoes_afetadas)]
    novas_linhas = []
    for codigo_seccao, grupo in agrupar.groupby("DTMNFRSEC21"):
        geometria = grupo.geometry.union_all()
        linha = grupo.iloc[0].copy()
        linha["SUBSECCAO"] = codigo_seccao  # identificador passa a ser o da secção
        linha["geometry"] = geometria
        linha["populacao_residente"] = populacao_seccao.get(codigo_seccao, pd.NA)
        linha["fonte_populacao"] = "INE Censos 2021 — Ficheiro Síntese (SECÇÃO)"
        linha["nivel_geografico"] = "secção estatística"
        if pd.isna(linha["populacao_residente"]):
            linha["fonte_populacao"] = "SEM DADOS POPULACIONAIS"
        novas_linhas.append(linha)
        mensagem(f"   Secção {codigo_seccao}: {len(grupo)} subsecções agregadas.")

    resultado = pd.concat([manter, gpd.GeoDataFrame(novas_linhas, crs=subseccoes.crs)],
                          ignore_index=True)
    return gpd.GeoDataFrame(resultado, geometry="geometry", crs=subseccoes.crs)


def construir_designacao(linha):
    """
    Cria um texto legível com a localização da subsecção.

    Parâmetros:
        linha (pandas.Series): uma linha da tabela de subsecções.

    Devolve:
        str: ex. "Bacelo e Senhora da Saúde (Évora) — secção 003, subsecção 05".
    """
    freguesia = linha.get("FREGUESIA DSG")
    municipio = linha.get("MUNICIPIO DSG")
    if pd.isna(freguesia):
        freguesia = f"Freguesia {linha['DTMNFR21']}"
    if pd.isna(municipio):
        municipio = f"Município {linha['DTMN21']}"
    if linha["nivel_geografico"] == "secção estatística":
        return f"{freguesia} ({municipio}) — secção {linha['SUBSECCAO'][-3:]}"
    codigo = str(linha["SECSSNUM21"])
    return f"{freguesia} ({municipio}) — secção {codigo[:3]}, subsecção {codigo[3:]}"


def validar_coordenadas(latitude, longitude):
    """
    Verifica se um par de coordenadas é plausível para Portugal Continental.

    Parâmetros:
        latitude (float), longitude (float): coordenadas em graus decimais.

    Devolve:
        bool: True se as coordenadas forem números válidos dentro dos limites
        aproximados de Portugal Continental (lat 36.8–42.2; lon -9.6 a -6.1).

    Nota: é um filtro grosseiro (um retângulo, que inclui partes de Espanha);
    serve para apanhar erros como coordenadas trocadas ou vazias. A garantia
    de que tudo está em Portugal vem de só usarmos polígonos da BGRI 2021
    (território nacional) e do teste aos pontos de encaixe na etapa 4.
    """
    if pd.isna(latitude) or pd.isna(longitude):
        return False
    return 36.8 <= latitude <= 42.2 and -9.6 <= longitude <= -6.1


def verificar_totais_municipais(subseccoes):
    """
    Controlo de qualidade: para os municípios totalmente incluídos na área de
    estudo, a soma da população das subsecções deve ser IGUAL ao total oficial
    do município publicado pelo INE no mesmo Ficheiro Síntese.

    Parâmetros:
        subseccoes (GeoDataFrame): tabela final da etapa 2 (colunas renomeadas).

    Devolve:
        list[dict]: um registo por município verificado (soma, total, diferença).
    """
    ficheiro_totais = config.PASTA_PROCESSADOS / "FS2021SubSeccaoTot_totais_municipio.csv"
    copia_sintese = config.PASTA_PROCESSADOS / "FS2021SubSeccaoTot.csv"
    if not ficheiro_totais.exists() or not copia_sintese.exists():
        mensagem("   (Totais municipais indisponíveis; verificação ignorada.)")
        return []
    totais = pd.read_csv(ficheiro_totais, dtype=str)
    sintese = pd.read_csv(copia_sintese, dtype=str, usecols=["MUNICIPIO"])
    n_subseccoes_oficial = sintese["MUNICIPIO"].value_counts()

    verificacoes = []
    for codigo, grupo in subseccoes.groupby("codigo_municipio"):
        # Só faz sentido comparar se o município inteiro está na área de estudo
        if len(grupo) != n_subseccoes_oficial.get(codigo, -1):
            continue
        linha_total = totais[totais["MUNICIPIO"] == codigo]
        if linha_total.empty:
            continue
        total_oficial = int(linha_total[config.VARIAVEL_POPULACAO].iloc[0])
        soma = int(grupo["populacao_residente"].sum())
        verificacoes.append({"municipio": grupo["municipio"].iloc[0], "codigo": codigo,
                             "soma_subseccoes": soma, "total_oficial_ine": total_oficial,
                             "diferenca": soma - total_oficial})
    erradas = [v for v in verificacoes if v["diferenca"] != 0]
    mensagem(f"   Controlo de totais municipais: {len(verificacoes)} municípios completos "
             f"verificados, {len(erradas)} com diferenças (esperado: 0).")
    return verificacoes


def executar_etapa_2():
    """
    Executa a etapa 2 completa e guarda a tabela georreferenciada.

    Devolve:
        GeoDataFrame: subsecções da área de estudo (polígonos + atributos).
    """
    mensagem("=" * 70)
    mensagem("ETAPA 2 — Preparar subsecções estatísticas (polígonos, centroides, população)")
    mensagem("=" * 70)

    poligonos = ler_poligonos_bgri()
    poligonos = calcular_centroides(poligonos)
    subseccao_hospital = localizar_hospital(poligonos)
    cobertura = verificar_cobertura_do_circulo(poligonos)

    dentro = poligonos["distancia_linha_reta_km"] <= config.RAIO_PRE_SELECAO_KM
    subseccoes = poligonos[dentro].copy()
    mensagem(f"   Subsecções com centroide a ≤ {config.RAIO_PRE_SELECAO_KM:.0f} km "
             f"em linha reta: {len(subseccoes)}")

    subseccoes, controlo = associar_populacao(subseccoes)

    # Recalcular centroides (caso tenha havido agregação ao nível da secção)
    subseccoes = calcular_centroides(gpd.GeoDataFrame(subseccoes, geometry="geometry",
                                                      crs=config.CRS_PORTUGAL))
    centroides_wgs84 = gpd.GeoSeries(subseccoes["centroide"], crs=config.CRS_PORTUGAL).to_crs(config.CRS_WGS84)
    subseccoes["latitude"] = centroides_wgs84.y.round(7)
    subseccoes["longitude"] = centroides_wgs84.x.round(7)
    subseccoes["coordenada_valida"] = [validar_coordenadas(la, lo) for la, lo in
                                       zip(subseccoes["latitude"], subseccoes["longitude"])]
    subseccoes["designacao"] = subseccoes.apply(construir_designacao, axis=1)
    subseccoes = subseccoes.rename(columns={"SUBSECCAO": "id_subseccao",
                                            "MUNICIPIO DSG": "municipio",
                                            "FREGUESIA DSG": "freguesia",
                                            "DTMN21": "codigo_municipio",
                                            "DTMNFR21": "codigo_freguesia"})
    subseccoes = subseccoes.sort_values("id_subseccao").reset_index(drop=True)

    invalidas = int((~subseccoes["coordenada_valida"]).sum())
    fora = int((~subseccoes["centroide_dentro_poligono"]).sum())
    mensagem(f"   Coordenadas inválidas: {invalidas}")
    mensagem(f"   Centroides que caem fora do próprio polígono: {fora} "
             "(aproximação: ver README)")
    mensagem(f"   População residente total na área pré-selecionada: "
             f"{int(subseccoes['populacao_residente'].sum()):,}".replace(",", " "))

    verificacoes_municipios = verificar_totais_municipais(subseccoes)

    # ---- Guardar resultados ----
    colunas = ["id_subseccao", "designacao", "municipio", "freguesia",
               "codigo_municipio", "codigo_freguesia", "NUTS3", "nivel_geografico",
               "populacao_residente", "fonte_populacao", "populacao_bgri_gpkg",
               "latitude", "longitude", "coordenada_valida",
               "centroide_dentro_poligono", "distancia_linha_reta_km", "geometry"]
    resultado = gpd.GeoDataFrame(subseccoes[colunas], geometry="geometry", crs=config.CRS_PORTUGAL)
    config.PASTA_PROCESSADOS.mkdir(parents=True, exist_ok=True)
    resultado.to_file(config.FICHEIRO_SUBSECCOES, driver="GPKG")
    tabela = pd.DataFrame(resultado.drop(columns="geometry"))
    tabela.to_csv(config.PASTA_TABELAS / "subseccoes_georreferenciadas.csv",
                  index=False, encoding="utf-8-sig", sep=";", decimal=",")

    registar_metadados("etapa_02_preparacao", {
        "unidade_geografica": "subsecção estatística (BGRI 2021)",
        "variavel_populacao": config.VARIAVEL_POPULACAO,
        "raio_pre_selecao_km": config.RAIO_PRE_SELECAO_KM,
        "criterio_pre_selecao": "distância em linha reta do centroide ao hospital "
                                "(limite físico: 30 min × 130 km/h)",
        "cobertura_circulo": cobertura,
        "hospital_latitude": config.HOSPITAL_LATITUDE,
        "hospital_longitude": config.HOSPITAL_LONGITUDE,
        "hospital_coordenadas_origem": "GPS indicado pelo utilizador: 38º34'07.99\" N, 7º54'11.44\" W",
        "subseccao_do_hospital": subseccao_hospital,
        "ambito_territorial": "apenas Portugal (subsecções da BGRI 2021)",
        "subseccoes_pre_selecionadas": len(resultado),
        "populacao_pre_selecionada": int(resultado["populacao_residente"].sum()),
        "coordenadas_invalidas": invalidas,
        "centroides_fora_do_poligono": fora,
        "controlo_populacao": controlo,
        "controlo_totais_municipais": verificacoes_municipios,
        "metodo_centroide": "centroide geométrico calculado em EPSG:3763 e "
                            "convertido para EPSG:4326",
    })
    mensagem("ETAPA 2 concluída. Ficheiros: dados/processados/subseccoes_area_estudo.gpkg "
             "e resultados/tabelas/subseccoes_georreferenciadas.csv")
    return resultado


if __name__ == "__main__":
    verificar_ficheiro_existe(config.PASTA_ENTRADA, "etapa_01_descarregar_dados_ine.py")
    executar_etapa_2()
