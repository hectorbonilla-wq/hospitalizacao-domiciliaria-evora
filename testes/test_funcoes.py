"""
Testes simples das funções principais (não precisam de Internet).

Executar a partir da pasta do projeto:
    python -m pytest testes/ -v
ou, sem pytest:
    python testes/test_funcoes.py

Cada teste verifica uma regra com um exemplo cujo resultado conhecemos.
"""

import sys
from pathlib import Path

import numpy as np

# Permite importar os módulos do projeto (que estão na pasta acima)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from etapa_02_preparar_subseccoes import validar_coordenadas  # noqa: E402
from etapa_04_verificar_consistencia import (contar_violacoes_triangulares,  # noqa: E402
                                             distancia_linha_reta_km)
from etapa_05_classificar_elegibilidade import classificar_tempo  # noqa: E402
from etapa_08_resumo_e_capacidade import calcular_capacidade_operacional  # noqa: E402
import pandas as pd  # noqa: E402
from matriz_doentes import (aplicar_condicoes_reais, ler_doentes, matriz_quadrada,  # noqa: E402
                            texto_da_morada)


def test_conversao_gms_para_decimal():
    """38º34'07.99" N e 7º54'11.44" W devem dar 38.5688861 e -7.9031778."""
    assert round(config.gms_para_decimal(38, 34, 7.99, "N"), 7) == 38.5688861
    assert round(config.gms_para_decimal(7, 54, 11.44, "W"), 7) == -7.9031778
    assert config.HOSPITAL_LONGITUDE < 0, "Longitude a Oeste tem de ser negativa"


def test_classificacao_no_limite():
    """Exatamente 30 min é elegível; 30,01 min já não é."""
    assert classificar_tempo(30.0)[0] == "elegível"
    assert classificar_tempo(29.99)[0] == "elegível"
    assert classificar_tempo(30.01)[0] == "não elegível"
    assert classificar_tempo(0)[0] == "elegível"


def test_classificacao_sem_tempo():
    """Sem tempo calculado, a subsecção não pode ser elegível."""
    assert classificar_tempo(None)[0] == "não elegível"
    assert classificar_tempo(float("nan"))[0] == "não elegível"


def test_validar_coordenadas():
    """Évora é válida; coordenadas trocadas, em falta ou muito longe não são.

    Nota: este é um filtro grosseiro (retângulo). A confirmação rigorosa de
    que um ponto está em Portugal usa o território da BGRI 2021 (etapas 2, 4 e 6).
    """
    assert validar_coordenadas(config.HOSPITAL_LATITUDE, config.HOSPITAL_LONGITUDE)
    assert not validar_coordenadas(-7.90, 38.57)        # lat/lon trocadas
    assert not validar_coordenadas(37.39, -5.98)        # Sevilha (Espanha)
    assert not validar_coordenadas(float("nan"), -7.9)  # valor em falta


def test_desigualdade_triangular_detecta_erros():
    """Uma matriz correta não tem violações; uma matriz errada tem."""
    correta = np.array([[0, 10, 15], [10, 0, 5], [15, 5, 0]], dtype=float)
    assert contar_violacoes_triangulares(correta, 0)[0] == 0
    errada = np.array([[0, 10, 50], [10, 0, 5], [50, 5, 0]], dtype=float)  # 50 > 10 + 5
    assert contar_violacoes_triangulares(errada, 0)[0] > 0


def test_distancia_linha_reta():
    """Évora → Lisboa (Praça do Comércio) fica a cerca de 109 km em linha reta."""
    distancia = distancia_linha_reta_km(38.5714, -7.9135, 38.7075, -9.1364)
    assert 105 < distancia < 112


def test_raio_pre_selecao():
    """30 min a 130 km/h = 65 km."""
    assert config.RAIO_PRE_SELECAO_KM == 65


def test_capacidade_operacional():
    """Com turno de 420 min, ida+regresso 30 min, visita 45 e entre-visitas 15: 6 visitas."""
    indicadores = {"tempo_hospital_domicilio_elegiveis_min": {"media_ponderada_pela_populacao": 15},
                   "tempo_domicilio_hospital_elegiveis_min": {"media_ponderada_pela_populacao": 15}}
    resultado = calcular_capacidade_operacional(indicadores)
    # (420 − 15 − 15 + 15) / (45 + 15) = 6,75 → 6 visitas
    assert resultado["cenarios"]["tempos_medios"]["visitas_por_equipa_dia"] == 6
    # pior caso: (420 − 30 − 30 + 15) / 60 = 6,25 → 6
    assert resultado["cenarios"]["pior_caso_30min"]["visitas_por_equipa_dia"] == 6


def test_condicoes_reais():
    """10 min em fluxo livre → 10 × 1,15 + 3 = 14,5 min; a diagonal continua a 0."""
    livre = pd.DataFrame([[0, 10], [12, 0]], index=["HOSPITAL", "D1"], columns=["HOSPITAL", "D1"], dtype=float)
    reais = aplicar_condicoes_reais(livre)
    esperado = 10 * config.CONDICOES_REAIS_FATOR_TRANSITO + config.CONDICOES_REAIS_TEMPO_ACESSO_MIN
    assert abs(reais.loc["HOSPITAL", "D1"] - esperado) < 1e-9
    assert reais.loc["D1", "D1"] == 0 and reais.loc["HOSPITAL", "HOSPITAL"] == 0


def test_matriz_quadrada_mesma_ordem():
    """A matriz recortada é quadrada e tem a mesma ordem nas linhas e colunas."""
    nomes = ["HOSPITAL", "D1", "D2", "D3"]
    completa = pd.DataFrame(np.arange(16).reshape(4, 4), index=nomes, columns=nomes)
    q = matriz_quadrada(completa, ["D3", "D1"])
    assert list(q.index) == list(q.columns) == ["HOSPITAL", "D3", "D1"]
    assert q.loc["D3", "D1"] == completa.loc["D3", "D1"]  # sentido D3 → D1 preservado


def test_ler_doentes_e_morada(tmp_path=None):
    """Lê um CSV com ';' e junta a morada num texto de pesquisa."""
    import tempfile
    pasta = Path(tempfile.mkdtemp())
    ficheiro = pasta / "d.csv"
    ficheiro.write_text("id_doente;morada;codigo_postal;localidade\nD1;Rua 5 de Outubro;7000-854;Évora\n",
                        encoding="utf-8")
    doentes = ler_doentes(ficheiro)
    assert texto_da_morada(doentes.iloc[0]) == "Rua 5 de Outubro, 7000-854 Évora"
    assert doentes["latitude"].isna().all()  # sem coordenadas → serão geocodificadas


if __name__ == "__main__":
    # Execução simples sem pytest: corre todas as funções que começam por "test_"
    testes = [f for nome, f in list(globals().items()) if nome.startswith("test_")]
    for teste in testes:
        teste()
        print(f"OK  {teste.__name__}")
    print(f"\n{len(testes)} testes passaram.")
