"""Checagens de consistência. Regra principal: a soma dos detalhes (empenhos) tem de ser IGUAL, ao centavo, aos totais que o
próprio portal informa. Divergências são gravadas na tabela `validacao` e mostradas em Metodologia."""
from __future__ import annotations

import json

from . import config, db

MEDIDAS = ("empenhado", "liquidado", "pago")


def _res(checagem, esperado, obtido, detalhe="", tolera_aviso=False):
    dif = (obtido - esperado) if esperado is not None and obtido is not None else None
    status = "ok" if dif == 0 else ("aviso" if tolera_aviso else "divergente")
    return {"checagem": checagem, "status": status, "esperado": esperado, "obtido": obtido, "diferenca": dif, "detalhe": detalhe}


def validar(conn, entidade: str, ano: int) -> list:
    q1 = lambda sql, *a: conn.execute(sql, a).fetchone()
    out = []
    soma = q1("SELECT COALESCE(SUM(empenhado),0) e, COALESCE(SUM(liquidado),0) l, COALESCE(SUM(pago),0) p, COUNT(*) n "
              "FROM empenho WHERE entidade=? AND exercicio=?", entidade, ano)
    if soma["n"] == 0:
        out.append(_res("empenhos_carregados", 1, 0, "nenhum empenho carregado para o exercício"))
    for origem in ("por_orgao", "por_fornecedor"):
        t = q1("SELECT * FROM total_portal WHERE entidade=? AND exercicio=? AND origem=?", entidade, ano, origem)
        for m, k in zip(MEDIDAS, ("e", "l", "p")):
            if t is None:
                out.append(_res(f"{m}_vs_portal_{origem}", None, soma[k], "total do portal não coletado")); out[-1]["status"] = "aviso"
            else:
                out.append(_res(f"{m}_vs_portal_{origem}", t[m], soma[k],
                                f"soma dos empenhos × total do portal ({origem}), coletado em {t['coletado_em']}"))
    # por órgão, ao centavo
    difs = conn.execute("""
        SELECT t.orgao, t.empenhado te, t.liquidado tl, t.pago tp,
               COALESCE(SUM(e.empenhado),0) se, COALESCE(SUM(e.liquidado),0) sl, COALESCE(SUM(e.pago),0) sp
        FROM orgao_total_portal t LEFT JOIN empenho e
          ON e.entidade=t.entidade AND e.exercicio=t.exercicio AND e.orgao=t.orgao
        WHERE t.entidade=? AND t.exercicio=? GROUP BY t.orgao, t.empenhado, t.liquidado, t.pago""", (entidade, ano)).fetchall()
    ruins = [r["orgao"] for r in difs if (r["te"], r["tl"], r["tp"]) != (r["se"], r["sl"], r["sp"])]
    sem_orgao = q1("SELECT COUNT(*) n FROM empenho e WHERE entidade=? AND exercicio=? AND orgao NOT IN "
                   "(SELECT orgao FROM orgao_total_portal WHERE entidade=? AND exercicio=?)", entidade, ano, entidade, ano)["n"]
    out.append(_res("por_orgao_confere", 0, len(ruins) + sem_orgao,
                    f"{len(difs)} órgãos conferidos; divergentes: {ruins or 'nenhum'}; empenhos sem órgão no portal: {sem_orgao}"))
    # integridade referencial
    orf = q1("SELECT COUNT(*) n FROM empenho e LEFT JOIN fornecedor f ON f.entidade=e.entidade AND f.codif=e.codif "
             "WHERE e.entidade=? AND e.exercicio=? AND f.codif IS NULL", entidade, ano)["n"]
    out.append(_res("empenhos_sem_fornecedor", 0, orf, "empenhos cujo fornecedor não foi carregado"))
    # mensal × anual
    ms = q1("SELECT COUNT(*) n, COALESCE(SUM(empenhado),0) e, COALESCE(SUM(liquidado),0) l, COALESCE(SUM(pago),0) p "
            "FROM mensal_fornecedor WHERE entidade=? AND exercicio=?", entidade, ano)
    if ms["n"]:
        t = q1("SELECT * FROM total_portal WHERE entidade=? AND exercicio=? AND origem='por_fornecedor'", entidade, ano)
        for m, k in zip(MEDIDAS, ("e", "l", "p")):
            out.append(_res(f"{m}_soma_dos_meses_vs_anual", t[m] if t else None, ms[k],
                            "soma das 12 consultas mensais × consulta anual (pode divergir se o portal lançou algo entre as duas coletas)",
                            tolera_aviso=True))
        mo = q1("SELECT COALESCE(SUM(liquidado),0) l, COALESCE(SUM(pago),0) p FROM mensal_orgao WHERE entidade=? AND exercicio=?", entidade, ano)
        out.append(_res("liquidado_mensal_orgao_vs_fornecedor", ms["l"], mo["l"], "duas consultas mensais independentes", tolera_aviso=True))
        out.append(_res("pago_mensal_orgao_vs_fornecedor", ms["p"], mo["p"], "duas consultas mensais independentes", tolera_aviso=True))
    # receita
    rt = conn.execute("SELECT codigo, SUM(arrecadado) a FROM receita WHERE entidade=? AND exercicio=? AND ordem=1 GROUP BY codigo",
                      (entidade, ano)).fetchall()
    rm = {r["codigo"]: r["a"] for r in conn.execute(
        "SELECT codigo, SUM(arrecadado) a FROM receita_mensal_topo WHERE entidade=? AND exercicio=? GROUP BY codigo", (entidade, ano))}
    if rt and rm:
        esperado = sum(r["a"] for r in rt)
        out.append(_res("receita_topo_soma_dos_meses_vs_anual", esperado, sum(rm.get(r["codigo"], 0) for r in rt),
                        "linhas de topo (correntes + capital + deduções): meses × ano", tolera_aviso=True))
    # sanidade: valores negativos em totais por órgão
    neg = q1("SELECT COUNT(*) n FROM (SELECT orgao FROM empenho WHERE entidade=? AND exercicio=? GROUP BY orgao HAVING SUM(empenhado)<0)", entidade, ano)["n"]
    out.append(_res("orgaos_com_empenhado_negativo", 0, neg, "total negativo indicaria anulação sem o empenho original"))
    if entidade == "camara":
        out += checagens_camara(conn, ano)
    aplica_conhecidas(entidade, ano, out)
    agora = db.agora()
    conn.execute("DELETE FROM validacao WHERE entidade=? AND exercicio=?", (entidade, ano))
    conn.executemany("INSERT INTO validacao VALUES (?,?,?,?,?,?,?,?,?)",
                     [(entidade, ano, r["checagem"], r["status"], r["esperado"], r["obtido"], r["diferenca"], r["detalhe"], agora) for r in out])
    conn.commit()
    return out


def conhecidas(caminho=None) -> list:
    caminho = caminho or config.ARQ_VALIDACAO_CONHECIDA
    try:
        return json.loads(open(caminho, encoding="utf-8").read()).get("conhecidas", [])
    except FileNotFoundError:
        return []


def aplica_conhecidas(entidade: str, ano: int, resultados: list, lista: list = None):
    """Divergência que existe na PRÓPRIA FONTE e já foi verificada vira 'aviso' enquanto a diferença for exatamente a registrada."""
    for c in (conhecidas() if lista is None else lista):
        if c["entidade"] != entidade or c["exercicio"] != ano:
            continue
        for r in resultados:
            if r["checagem"] == c["checagem"] and r["status"] == "divergente" and r["diferenca"] == c["diferenca"]:
                r["status"] = "aviso"
                r["detalhe"] = f"{r['detalhe']} [DIVERGÊNCIA CONHECIDA DA FONTE: {c['nota']}]"


def resumo(resultados: list) -> tuple:
    div = [r for r in resultados if r["status"] == "divergente"]
    avs = [r for r in resultados if r["status"] == "aviso"]
    return len(resultados), len(div), len(avs)


def checagens_camara(conn, ano: int) -> list:
    """Conferências próprias da Câmara (diárias × elemento 14, verba × elemento 93, vínculos de vereadores, repasses)."""
    from .publicar_camara import ehdiaria
    E, out = "camara", []
    q1 = lambda sql, *a: conn.execute(sql, a).fetchone()
    pago = lambda el: q1("SELECT COALESCE(SUM(pago),0) FROM empenho WHERE entidade=? AND exercicio=? AND elemento=?", E, ano, el)[0]
    di = sum(r["valor"] - r["valor_anulado"] for r in conn.execute("SELECT valor, valor_anulado, elemento FROM diaria WHERE entidade=? AND exercicio=?", (E, ano)) if ehdiaria(r["elemento"]))
    out.append(_res("diarias_vs_elemento_14_pago", pago("14"), di, "soma da consulta Diarias (só diárias, sem locomoção) × pago do elemento 14", tolera_aviso=True))
    vsum = q1("SELECT COALESCE(SUM(pago),0) FROM verba_indenizatoria WHERE entidade=? AND exercicio=?", E, ano)[0]
    out.append(_res("verba_e_reembolsos_vs_elemento_93_pago", pago("93"), vsum, "verba indenizatória + reembolsos classificados × pago do elemento 93"))
    pend = q1("SELECT COUNT(DISTINCT v.codif) FROM vereador_vinculo v WHERE v.status='sugerido' AND (EXISTS (SELECT 1 FROM empenho e WHERE e.entidade=? AND e.exercicio=? AND e.codif=v.codif AND e.elemento IN ('93','14')) "
              "OR EXISTS (SELECT 1 FROM diaria d WHERE d.entidade=? AND d.exercicio=? AND d.codif=v.codif))", E, ano, E, ano)[0]
    out.append(_res("vinculos_de_vereadores_pendentes", 0, pend, "cadastros com nome igual/parecido a vereador mas sem confirmação (config/vinculos_vereadores.csv); ficam FORA das somas até decisão", tolera_aviso=True))
    sem = q1("SELECT COUNT(*) FROM verba_indenizatoria WHERE entidade=? AND exercicio=? AND categoria='verba' AND vereador_id IS NULL", E, ano)[0]
    out.append(_res("verba_sem_vereador_vinculado", 0, sem, "pagamentos de verba indenizatória cujo favorecido não está vinculado a vereador confirmado", tolera_aviso=True))
    nver = q1("SELECT COUNT(DISTINCT vereador_id) FROM vereador_folha WHERE ano=?", ano)[0]
    out.append(_res("vereadores_com_folha_no_ano", 1, nver if nver else 0, "vereadores com ao menos um mês na folha do ano") if nver == 0 else
               {"checagem": "vereadores_com_folha_no_ano", "status": "ok", "esperado": nver, "obtido": nver, "diferenca": 0, "detalhe": f"{nver} vereadores com registro na folha do ano"})
    m = q1("SELECT MAX(mes) FROM vereador_folha WHERE ano=?", ano)[0]
    if m:
        a = q1("SELECT COALESCE(SUM(lancamentos),0) FROM vereador_folha WHERE ano=? AND mes=? AND UPPER(cargo)='VEREADOR'", ano, m)[0]
        g = q1("SELECT qtd FROM servidor_agregado WHERE entidade=? AND ref_ano=? AND ref_mes=? AND dimensao='cargo' AND chave='VEREADOR'", E, ano, m)
        out.append(_res("vereadores_folha_vs_agregado", g[0] if g else None, a, f"lançamentos com cargo exato VEREADOR na folha nominal de {m:02d}/{ano} × grupo VEREADOR do agregado (suplentes são outro grupo de cargo)"))
    rp = q1("SELECT COALESCE(SUM(repasse),0) FROM transferencia WHERE entidade='prefeitura' AND exercicio=? AND UPPER(recebedora) LIKE '%CAMARA%'", ano)[0]
    rc = q1("SELECT COALESCE(SUM(devolucao),0) FROM transferencia WHERE entidade='camara' AND exercicio=?", ano)[0]
    if rp or rc:
        out.append(_res("repasse_prefeitura_vs_recebido_camara", rp, rc, "repasse informado pela Prefeitura × recebimento informado pela Câmara (a Câmara registra na coluna DEVOLUCAO e pode ter lançado menos meses)", tolera_aviso=True))
    return out
