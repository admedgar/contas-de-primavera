"""Configuração central: endereços, caminhos e limites de cortesia com o servidor."""
from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DB_PADRAO = Path(os.environ.get("CONTAS_DB", RAIZ / "data" / "contas.sqlite"))
RAW_DIR = RAIZ / "data" / "raw"
WEB_DATA = RAIZ / "web" / "data"

BASE_URL = "https://scpi.primaveradoleste.mt.gov.br"
ENTIDADES = {
    "prefeitura": {"nome": "Prefeitura Municipal de Primavera do Leste", "portal": "transparencia",
                   "cnpj": "01.974.088/0001-05"},   # empenhos em nome do próprio ente (ex.: folha) não são "fornecedor"
    "camara": {"nome": "Câmara Municipal de Primavera do Leste", "portal": "transparenciacamara", "cnpj": "24.672.727/0001-83"},
}
IBGE_MUNICIPIO = "5107040"  # Primavera do Leste (MT)

# Identifica o projeto ao servidor do portal. Para que a prefeitura consiga falar com o responsável em caso de problema,
# defina CONTAS_CONTATO (e-mail ou URL) no ambiente; ele entra no User-Agent e NÃO fica gravado no código.
_CONTATO = os.environ.get("CONTAS_CONTATO", "").strip()
USER_AGENT = os.environ.get(
    "CONTAS_USER_AGENT",
    "ContasDePrimavera/0.4 (projeto independente de transparencia" + (f"; contato: {_CONTATO}" if _CONTATO else "") + ")",
)
PAUSA_ENTRE_REQUISICOES_S = float(os.environ.get("CONTAS_PAUSA_S", "2.0"))
TIMEOUT_S = 600
TENTATIVAS = 4
ESPERA_RETRY_S = (5, 15, 45)
# Servidores: grupos menores que isto são somados em "Outros" (evita expor salário individual)
K_ANONIMATO = 3

# Pessoas físicas (CPF mascarado) nas listas publicadas de empenhos e fornecedores:
#   "beneficiarios" (padrão): nome, documento e histórico são omitidos quando o pagamento NÃO é prestação de serviço/venda
#       (diárias, auxílios financeiros, sentenças judiciais, premiações, reembolsos, folha...), pois o histórico oficial pode citar
#       pacientes, beneficiários de programas sociais etc. Totais permanecem. Vereadores confirmados continuam nominais.
#   "portal": publica como o portal oficial.   "todos": omite toda pessoa física.
PF_POLITICA = os.environ.get("CONTAS_PF", "beneficiarios")
ELEMENTOS_PF_VISIVEIS = {"30", "35", "36", "37", "39", "40", "51", "52"}   # material e serviços contratados (relação comercial)
# Elementos cujo favorecido é, por natureza, uma pessoa (mesmo quando cadastrada com CNPJ de microempreendedor com o próprio nome):
# diárias (14), premiações (31), auxílios financeiros a pessoas físicas (48). Omitidos na política "beneficiarios".
ELEMENTOS_SEMPRE_PESSOA = {"14", "31", "48"}

ARQ_ALERTAS = RAIZ / "config" / "alertas.json"
ARQ_SITE = RAIZ / "config" / "site.json"
ARQ_VALIDACAO_CONHECIDA = RAIZ / "config" / "validacao_conhecida.json"
DIST = RAIZ / "dist"
