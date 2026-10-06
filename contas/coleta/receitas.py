"""Receita orçamentária. A fonte é uma ÁRVORE (códigos repetidos em níveis diferentes): somar tudo triplica o total.
Os totais confiáveis são as linhas de topo (ORDEM = 1): receitas correntes, de capital e deduções."""
from __future__ import annotations

from .. import db, http
from ..parsers import centavos, limpa
from .despesas import params_base, verifica_campos
from .mensal import ate_mes

OBRIG = {"ORDEM", "CODIGO", "NOME", "PREVISAO_INICIAL", "PREVISAO_ATUALIZADA", "ARRECADADO_PERIODO", "ARRECADADO_TOTAL"}


def topo(linhas: list) -> list:
    return [r for r in linhas if str(r["ORDEM"]).strip() == "1"]


def coletar_receitas(conn, entidade: str, ano: int):
    with db.coleta(conn, entidade, "receita_orcamentaria", ano) as info:
        dados, info["url"], b = http.get_json(entidade, "Receitas", params_base(ano, "ReceitaOrcamentaria"))
        verifica_campos(dados, OBRIG, "ReceitaOrcamentaria")
        conn.execute("DELETE FROM receita WHERE entidade=? AND exercicio=?", (entidade, ano))
        conn.executemany("INSERT INTO receita VALUES (?,?,?,?,?,?,?,?,?)", [
            (entidade, ano, i, int(r["ORDEM"] or 0), r["CODIGO"], limpa(r["NOME"]),
             centavos(r["PREVISAO_INICIAL"]), centavos(r["PREVISAO_ATUALIZADA"]), centavos(r["ARRECADADO_TOTAL"]))
            for i, r in enumerate(dados)])
        conn.execute("DELETE FROM receita_mensal_topo WHERE entidade=? AND exercicio=?", (entidade, ano))
        n = len(dados)
        for mes in range(1, ate_mes(ano) + 1):
            m, _, b2 = http.get_json(entidade, "Receitas", params_base(ano, "ReceitaOrcamentaria", mes, mes))
            b += b2
            n += len(m)
            for r in topo(m):
                conn.execute("INSERT OR REPLACE INTO receita_mensal_topo VALUES (?,?,?,?,?,?)",
                             (entidade, ano, mes, r["CODIGO"], limpa(r["NOME"]), centavos(r["ARRECADADO_PERIODO"])))
        info["registros"], info["bytes"] = n, b
