"""
config.py — Parâmetros de configuração do projeto
===================================================

Este ficheiro reúne, num único local, todos os valores que podem ser
alterados pelo utilizador: coordenadas do hospital, limite de tempo,
endereços das fontes de dados, servidores de routing, nomes de pastas e
pressupostos da capacidade operacional.

Regra prática para principiantes: se quiser mudar o comportamento do
programa, comece por aqui. Os restantes ficheiros (etapa_XX_*.py) leem
estes valores com "import config".
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Local de referência: o hospital
# ---------------------------------------------------------------------------
HOSPITAL_NOME = (
    "ULS do Alentejo Central – Hospital do Espírito Santo de Évora "
    "(Hospitalização Domiciliária)"
)
HOSPITAL_MORADA = "Largo do Senhor da Pobreza, 7000-811 Évora"

# Coordenadas GPS oficiais indicadas pelo utilizador, em graus, minutos e
# segundos (GMS):   Latitude 38º34'07.99" N  |  Longitude 7º54'11.44" W
# NOTA: estas coordenadas NÃO foram geocodificadas pelo programa; são um
# dado de entrada. O hemisfério Oeste (W) corresponde a longitude NEGATIVA.


def gms_para_decimal(graus, minutos, segundos, hemisferio):
    """
    Converte coordenadas em graus-minutos-segundos para graus decimais.

    Parâmetros:
        graus, minutos, segundos (float): partes da coordenada.
        hemisferio (str): "N", "S", "E" ou "W".

    Devolve:
        float: coordenada em graus decimais (negativa para S e W).

    Exemplo:
        gms_para_decimal(7, 54, 11.44, "W")  ->  -7.9031778
    """
    valor = graus + minutos / 60 + segundos / 3600
    return -valor if hemisferio in ("S", "W") else valor


HOSPITAL_LATITUDE = round(gms_para_decimal(38, 34, 7.99, "N"), 7)    # 38.5688861
HOSPITAL_LONGITUDE = round(gms_para_decimal(7, 54, 11.44, "W"), 7)   # -7.9031778

# Coordenadas indicadas na primeira versão do pedido (38.5687432, -7.9081582),
# cerca de 430 m a oeste. Mantidas apenas para referência/documentação.
HOSPITAL_COORDENADAS_ALTERNATIVAS = (38.5687432, -7.9081582)

# ---------------------------------------------------------------------------
# 2. Critério de elegibilidade
# ---------------------------------------------------------------------------
# Uma subsecção é ELEGÍVEL se o tempo de viagem hospital -> domicílio
# for IGUAL OU INFERIOR a este valor (em minutos).
LIMITE_TEMPO_MINUTOS = 30

# ---------------------------------------------------------------------------
# 3. Área de estudo (pré-seleção física, NÃO administrativa)
# ---------------------------------------------------------------------------
# Para não pedir ao servidor de routing milhares de percursos inúteis
# (por exemplo, para o Algarve), só são analisadas as subsecções cujo
# centroide está a menos de RAIO_PRE_SELECAO_KM em linha reta do hospital.
#
# Justificação: a distância por estrada é SEMPRE maior ou igual à
# distância em linha reta. Mesmo circulando sempre a 130 km/h (velocidade
# máxima legal em autoestrada em Portugal), em 30 minutos não se percorrem
# mais de 65 km. Logo, nenhuma subsecção a mais de 65 km em linha reta pode
# estar a 30 minutos de carro. Este critério é físico e não exclui
# subsecções por pertencerem a um concelho ou distrito.
VELOCIDADE_MAXIMA_TEORICA_KMH = 130
RAIO_PRE_SELECAO_KM = VELOCIDADE_MAXIMA_TEORICA_KMH * LIMITE_TEMPO_MINUTOS / 60

# ---------------------------------------------------------------------------
# 4. Fontes oficiais do INE (BGRI 2021 e Censos 2021)
# ---------------------------------------------------------------------------
# Página de descarregamento indicada no enunciado. Em 2026 o INE moveu o
# índice para a raiz do site (https://mapas.ine.pt/). O programa tenta as
# duas e extrai automaticamente os links dos ficheiros.
INE_PAGINAS_DOWNLOAD = [
    "https://mapas.ine.pt/download/index2021.phtml",
    "https://mapas.ine.pt/",
]
INE_URL_BASE = "https://mapas.ine.pt/"

# Identificação do programa nos pedidos HTTP. O servidor do INE recusa
# (erro 403) pedidos sem um "User-Agent" de navegador; este cabeçalho
# genérico resolve o problema e é usado em todos os pedidos do projeto.
CABECALHOS_HTTP = {
    "User-Agent": "Mozilla/5.0 (compatible; estudo-cobertura-hospitalizacao-domiciliaria/1.0)"
}

# Regiões NUTS II da BGRI 2021 a descarregar (ficheiro GeoPackage com os
# polígonos das subsecções e as variáveis estatísticas dos Censos 2021).
# O círculo de pré-seleção de 65 km em torno de Évora abrange o Alentejo
# e, marginalmente, a Área Metropolitana de Lisboa (zona de Pegões/Montijo).
# A etapa 2 verifica automaticamente se as regiões escolhidas cobrem todo o
# círculo; se não cobrirem, avisa para acrescentar regiões aqui.
# Nomes possíveis: "NORTE", "CENTRO", "LISBOA", "ALENTEJO", "ALGARVE".
REGIOES_BGRI_NUTS2 = ["ALENTEJO", "LISBOA"]

# Ficheiro alfanumérico oficial (Ficheiro Síntese dos Censos 2021) com a
# população residente por subsecção estatística (e, em alternativa, por
# secção estatística — nível imediatamente superior).
INE_FICHEIRO_SINTESE_SUBSECCAO = "2021FicheiroSintese/FS2021SubSeccaoTot.zip"
INE_FICHEIRO_SINTESE_SECCAO = "2021FicheiroSintese/FS2021SeccaoTot.zip"
INE_DICIONARIO_VARIAVEIS = "C2021_FSINTESE_VARIAVEIS.csv"

# Variável que corresponde à população residente nos ficheiros do INE.
# (Dicionário do INE: "N_INDIVIDUOS – Nº total de indivíduos".)
VARIAVEL_POPULACAO = "N_INDIVIDUOS"

# Toda a análise fica restrita a PORTUGAL: só são analisadas subsecções da
# BGRI 2021 (território nacional); a isócrona é recortada pelos limites do
# território português; e os pontos de encaixe na rede rodoviária são
# confirmados como estando em Portugal (etapa 4).
APENAS_PORTUGAL = True

# ---------------------------------------------------------------------------
# 5. Serviços de routing (rede rodoviária OpenStreetMap)
# ---------------------------------------------------------------------------
# Motor usado para TODOS os tempos e distâncias do estudo:
#   "ors"  = OpenRouteService (precisa de chave pessoal gratuita — ver README)
#   "osrm" = servidor público do OSRM (sem chave)
# A chave do OpenRouteService é lida do ficheiro chave_openrouteservice.txt
# (na pasta do projeto, fora do Git) ou da variável de ambiente ORS_API_KEY.
# NUNCA escreva a chave neste ficheiro: config.py está no GitHub.
MOTOR_ROUTING = "ors"
ORS_URL = "https://api.openrouteservice.org"
ORS_PERFIL = "driving-car"          # automóvel ligeiro
ORS_PONTOS_POR_PEDIDO = 3000        # limite do ORS: ~3500 percursos por pedido
ORS_PAUSA_ENTRE_PEDIDOS_S = 2.0     # limite do plano gratuito: ~40 pedidos/minuto

# OSRM: servidor de demonstração público. É gratuito mas tem limites de
# utilização (cerca de 1 pedido por segundo). Para estudos frequentes,
# recomenda-se instalar um servidor OSRM próprio (ver README).
OSRM_URL = "https://router.project-osrm.org"
OSRM_PERFIL = "driving"            # automóvel
OSRM_PONTOS_POR_PEDIDO = 99        # nº de subsecções por pedido /table
OSRM_PAUSA_ENTRE_PEDIDOS_S = 1.0   # respeitar o servidor público
OSRM_TENTATIVAS = 4                # tentativas em caso de erro de rede
OSRM_TIMEOUT_S = 90

# Distância máxima (metros) entre o centroide e a estrada mais próxima a
# partir da qual a localização é marcada como "afastada da rede".
DISTANCIA_MAXIMA_ATE_ESTRADA_M = 1000

# Valhalla: usado APENAS para desenhar a isócrona de 30 minutos no mapa
# (o OSRM não calcula isócronas). A classificação de elegibilidade é feita
# sempre com os tempos do OSRM.
VALHALLA_URL = "https://valhalla1.openstreetmap.de"
VALHALLA_PERFIL = "auto"

# Geocodificação (Parte B): converter MORADAS de doentes em coordenadas.
# Serviço Nominatim (OpenStreetMap). Regras de uso do servidor público:
# no máximo 1 pedido por segundo e identificação do programa.
# PRIVACIDADE: as moradas são enviadas para este servidor. Para doentes reais,
# confirme com o Encarregado de Proteção de Dados da ULS; a alternativa é
# instalar um Nominatim próprio e mudar este endereço (ex.: http://localhost:8080).
GEOCODIFICACAO_URL = "https://nominatim.openstreetmap.org"
GEOCODIFICACAO_PAUSA_S = 1.1
GEOCODIFICACAO_CABECALHOS = {"User-Agent": "estudo-cobertura-hospitalizacao-domiciliaria/1.0"}
# Com chave do OpenRouteService, cada morada é procurada em DOIS serviços
# (ORS e Nominatim). Se os dois resultados distarem mais do que isto, avisa-se.
GEOCODIFICACAO_DIFERENCA_MAXIMA_M = 250
# Se um serviço só encontrou o centro da localidade e o outro encontrou a rua a
# mais desta distância desse centro, pede-se confirmação (pode ser outra terra).
GEOCODIFICACAO_DISTANCIA_MAX_CENTRO_M = 3000

# Condições reais de circulação (ESTIMATIVA — pressupostos editáveis)
# O OpenStreetMap/OSRM dá tempos em FLUXO LIVRE (sem trânsito). Os servidores
# públicos não têm trânsito em tempo real (testado: o Valhalla dá o mesmo tempo
# às 03:00 e às 08:30). Para aproximar condições reais usa-se:
#     tempo_real = tempo_fluxo_livre × FATOR_TRANSITO + TEMPO_ACESSO_MIN
# O tempo de acesso (estacionar, caminhar até à porta) só se soma quando a
# origem e o destino são pontos diferentes. Calibre estes valores com tempos
# medidos pela equipa (ex.: registos GPS da viatura).
CONDICOES_REAIS_FATOR_TRANSITO = 1.15     # +15 % (semáforos, cruzamentos, trânsito urbano)
CONDICOES_REAIS_TEMPO_ACESSO_MIN = 3      # minutos para estacionar e chegar à porta

# ---------------------------------------------------------------------------
# 6. Verificações de consistência
# ---------------------------------------------------------------------------
# Nº de subsecções sorteadas para construir uma matriz quadrada completa
# (todos-para-todos) e testar a desigualdade triangular.
TAMANHO_AMOSTRA_TRIANGULAR = 40
SEMENTE_ALEATORIA = 2021           # garante que a amostra é reprodutível
TOLERANCIA_TRIANGULAR_S = 5        # folga (segundos) para arredondamentos
VELOCIDADE_MEDIA_MINIMA_KMH = 3    # abaixo disto o percurso é suspeito
VELOCIDADE_MEDIA_MAXIMA_KMH = 130  # acima disto o percurso é suspeito

# ---------------------------------------------------------------------------
# 7. Pressupostos da capacidade operacional (CENÁRIO ILUSTRATIVO)
# ---------------------------------------------------------------------------
# Estes valores NÃO são dados observados. São pressupostos editáveis para
# mostrar a diferença entre "população elegível" e "doentes que a equipa
# consegue acompanhar". Substitua-os pelos valores reais do serviço.
CAPACIDADE_NUMERO_EQUIPAS = 1             # 1 equipa = 1 médico + 1 enfermeiro
CAPACIDADE_VIATURAS_DISPONIVEIS = 1       # viaturas ligeiras de 5 lugares
CAPACIDADE_LUGARES_POR_VIATURA = 5        # inclui o condutor
CAPACIDADE_PESSOAS_POR_EQUIPA = 2         # médico + enfermeiro
CAPACIDADE_MINUTOS_TURNO = 7 * 60         # tempo disponível para visitas/dia
CAPACIDADE_DURACAO_VISITA_MIN = 45        # duração média de cada visita
CAPACIDADE_VISITAS_POR_DOENTE_DIA = 1     # visitas diárias por doente
CAPACIDADE_TEMPO_ENTRE_VISITAS_MIN = 15   # deslocação média entre 2 domicílios

# ---------------------------------------------------------------------------
# 8. Pastas do projeto
# ---------------------------------------------------------------------------
PASTA_PROJETO = Path(__file__).resolve().parent
PASTA_ENTRADA = PASTA_PROJETO / "dados" / "entrada"          # ficheiros INE
PASTA_PROCESSADOS = PASTA_PROJETO / "dados" / "processados"  # intermédios
PASTA_TABELAS = PASTA_PROJETO / "resultados" / "tabelas"
PASTA_MATRIZES = PASTA_PROJETO / "resultados" / "matrizes"
PASTA_GEOJSON = PASTA_PROJETO / "resultados" / "geojson"
PASTA_MAPAS = PASTA_PROJETO / "resultados" / "mapas"
PASTA_RELATORIOS = PASTA_PROJETO / "resultados" / "relatorios"
PASTA_REGISTO = PASTA_PROJETO / "registo"

# Ficheiros intermédios (passam informação de uma etapa para a seguinte)
FICHEIRO_SUBSECCOES = PASTA_PROCESSADOS / "subseccoes_area_estudo.gpkg"
# Um ficheiro por motor, para se poderem comparar os resultados
FICHEIRO_ROUTING = PASTA_PROCESSADOS / f"resultados_routing_{MOTOR_ROUTING}.csv"
FICHEIRO_TERRITORIO = PASTA_PROCESSADOS / "territorio_portugal_area_estudo.gpkg"
FICHEIRO_ISOCRONA = PASTA_GEOJSON / "isocrona_30min.geojson"
FICHEIRO_METADADOS = PASTA_REGISTO / "metadados_execucao.json"
FICHEIRO_LOG = PASTA_REGISTO / "execucao.log"

# Sistemas de coordenadas
CRS_PORTUGAL = "EPSG:3763"  # PT-TM06/ETRS89 (metros) — usado pela BGRI 2021
CRS_WGS84 = "EPSG:4326"     # latitude/longitude (GPS, mapas web)
