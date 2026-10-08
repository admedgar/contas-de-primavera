"""SICONFI (Tesouro Nacional, dados abertos): receita realizada do município nos demonstrativos oficiais.
 - DCA Anexo I-C (anual, "Balanço Orçamentário - receita"): receita BRUTA realizada por classificação + colunas de deduções (Fundeb, outras).
 - RREO Anexo 01 (bimestral): previsão atualizada e realizada "no bimestre" e "até o bimestre" por origem.
Perímetro e convenção diferem do portal da Prefeitura (consolidado com regime próprio e intra-orçamentárias; linhas do RREO líquidas do Fundeb).
Por isso estes números só são comparados ENTRE SI (SICONFI × SICONFI)."""
from __future__ import annotations

import json
import urllib.parse
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .. import config, db, http

BASE = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/"
ANEXO_DCA = "DCA-Anexo I-C"
ANEXO_RREO = "RREO-Anexo 01"
COLUNAS_DCA = ("Receitas Brutas Realizadas", "Deduções - FUNDEB", "Outras Deduções da Receita")
COLUNAS_RREO = ("PREVISÃO ATUALIZADA (a)", "No Bimestre (b)", "Até o Bimestre (c)")
OBRIG = {"cod_conta", "conta", "coluna", "valor"}


class FormatoMudou(RuntimeError):
    pass


def centavos_float(v) -> int:
    return int((Decimal(str(v or 0)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def consulta(rota: str, **q) -> list:
    """Percorre as páginas (hasMore/offset) e devolve todos os itens."""
    itens, offset = [], 0
    while True:
        url = BASE + rota + "?" + urllib.parse.urlencode({**q, "offset": offset}) if offset else BASE + rota + "?" + urllib.parse.urlencode(q)
        d = http.get_json_externo(url)
        if not isinstance(d, dict) or "items" not in d:
            raise FormatoMudou(f"SICONFI {rota}: resposta sem 'items'")
        itens += d["items"]
        if not d.get("hasMore") or not d["items"]:
            return itens
        offset += len(d["items"])


def _confere(itens, fonte):
    if itens and not OBRIG <= set(itens[0]):
        raise FormatoMudou(f"{fonte}: campos ausentes {sorted(OBRIG - set(itens[0]))}")


def coletar_dca(conn, anos: list):
    with db.coleta(conn, "prefeitura", "siconfi_dca") as info:
        n, agora = 0, db.agora()
        for ano in anos:
            itens = consulta("dca", an_exercicio=ano, no_anexo=ANEXO_DCA, id_ente=config.IBGE_MUNICIPIO)
            _confere(itens, "DCA")
            linhas = [("dca", ano, 0, i["coluna"], i["cod_conta"], i["conta"], centavos_float(i["valor"]), agora) for i in itens if i["coluna"] in COLUNAS_DCA]
            if not linhas:
                continue                      # ano ainda não declarado: não apaga o que existir
            conn.execute("DELETE FROM siconfi_receita WHERE origem='dca' AND exercicio=?", (ano,))
            conn.executemany("INSERT OR REPLACE INTO siconfi_receita VALUES (?,?,?,?,?,?,?,?)", linhas)
            n += len(linhas)
        info["registros"] = n
        info["url"] = BASE + "dca"


def coletar_rreo(conn, anos: list):
    with db.coleta(conn, "prefeitura", "siconfi_rreo") as info:
        n, agora = 0, db.agora()
        for ano in anos:
            for bim in range(1, 7):
                itens = consulta("rreo", an_exercicio=ano, nr_periodo=bim, co_tipo_demonstrativo="RREO", no_anexo=ANEXO_RREO, id_ente=config.IBGE_MUNICIPIO)
                _confere(itens, "RREO")
                linhas = [("rreo", ano, bim, i["coluna"], i["cod_conta"], i["conta"], centavos_float(i["valor"]), agora) for i in itens if i["coluna"] in COLUNAS_RREO]
                if not linhas:
                    break                     # bimestre ainda não publicado
                conn.execute("DELETE FROM siconfi_receita WHERE origem='rreo' AND exercicio=? AND periodo=?", (ano, bim))
                conn.executemany("INSERT OR REPLACE INTO siconfi_receita VALUES (?,?,?,?,?,?,?,?)", linhas)
                n += len(linhas)
        info["registros"] = n
        info["url"] = BASE + "rreo"


def coletar_siconfi(conn, entidade: str = "prefeitura", ano: int = None, hoje: date = None):
    hoje = hoje or date.today()
    ano = ano or hoje.year
    coletar_dca(conn, [ano - 4 + i for i in range(4)])        # 4 exercícios fechados (ano-4 .. ano-1)
    coletar_rreo(conn, [ano - 3 + i for i in range(4)])       # mesmo bimestre em 4 anos (ano-3 .. ano)
