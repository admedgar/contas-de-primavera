"""Séries mês a mês a partir das consultas LEVES (sem rebaixar os 42 MB):
 - DespesasPorFornecedor com período = o mês: empenhado, liquidado e pago DO MÊS.
 - DespesasPorOrgao com período = o mês: empenhado do mês, mas liquidado/pago ACUMULADOS desde 1º/jan;
   o valor mensal é a diferença entre acumulados consecutivos."""
from __future__ import annotations

import logging
from datetime import date

from .. import db, http
from ..parsers import centavos, limpa, tipo_documento
from .despesas import params_base, verifica_campos

log = logging.getLogger("contas.mensal")


def ate_mes(ano: int) -> int:
    hoje = date.today()
    return 12 if ano < hoje.year else (0 if ano > hoje.year else hoje.month)


def diferenca_acumulados(acum: dict) -> dict:
    """{mes: {orgao: (liq, pago)}} acumulados -> mensal. Órgão ausente num mês conta como acumulado anterior (sem variação)."""
    saida, anterior = {}, {}
    for mes in sorted(acum):
        saida[mes] = {}
        for org, (liq, pago) in acum[mes].items():
            l0, p0 = anterior.get(org, (0, 0))
            saida[mes][org] = (liq - l0, pago - p0)
            anterior[org] = (liq, pago)
    return saida


def coletar_mensal(conn, entidade: str, ano: int):
    meses = ate_mes(ano)
    with db.coleta(conn, entidade, "mensal", ano) as info:
        mf, acum, emp_org, total_b, n_reg = [], {}, {}, 0, 0
        for mes in range(1, meses + 1):
            forn, url, n = http.get_json(entidade, "Despesas", params_base(
                ano, "DespesasPorFornecedor", mes, mes, MostrarFornecedor="True"))
            verifica_campos(forn, {"CODIGO", "DESCRICAO", "INSMF", "EMPENHADO", "LIQUIDADO", "PAGO"}, "PorFornecedor mensal")
            org, _, n2 = http.get_json(entidade, "Despesas", params_base(ano, "DespesasPorOrgao", mes, mes))
            info["url"] = url
            total_b += n + n2
            n_reg += len(forn) + len(org)
            for r in forn:
                v = (centavos(r["EMPENHADO"]), centavos(r["LIQUIDADO"]), centavos(r["PAGO"]))
                if any(v):
                    mf.append((entidade, ano, mes, r["CODIGO"], *v))
                    conn.execute("INSERT OR IGNORE INTO fornecedor VALUES (?,?,?,?,?)",
                                 (entidade, r["CODIGO"], limpa(r["DESCRICAO"]), limpa(r["INSMF"]),
                                  tipo_documento(limpa(r["INSMF"]))))
            acum[mes] = {o["CODIGO"]: (centavos(o["LIQUIDADO"]), centavos(o["PAGO"])) for o in org}
            emp_org[mes] = {o["CODIGO"]: centavos(o["EMPENHADO"]) for o in org}
        mo = diferenca_acumulados(acum)
        conn.execute("DELETE FROM mensal_fornecedor WHERE entidade=? AND exercicio=?", (entidade, ano))
        conn.execute("DELETE FROM mensal_orgao WHERE entidade=? AND exercicio=?", (entidade, ano))
        conn.executemany("INSERT INTO mensal_fornecedor VALUES (?,?,?,?,?,?,?)", mf)
        for mes, orgs in mo.items():
            for org, (liq, pago) in orgs.items():
                conn.execute("INSERT INTO mensal_orgao VALUES (?,?,?,?,?,?,?)",
                             (entidade, ano, mes, org, emp_org[mes].get(org, 0), liq, pago))
        info["registros"], info["bytes"] = n_reg, total_b
