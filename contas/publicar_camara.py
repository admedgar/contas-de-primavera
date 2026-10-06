"""JSONs da aba Câmara. Critérios idênticos para todos os vereadores; ordem padrão alfabética (sem ranking de 'campeões')."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from . import config, db
from .coleta.camara import eh_vereador
from .parsers import normaliza_nome
from .publicar import ROTULO_PF, _grava, _rows, anos_com_dados, pf_oculta

URL_OFICIAL_VI = "https://www.primaveradoleste.mt.leg.br/transparencia"   # página de transparência da Câmara (link apenas; os PDFs NÃO são lidos)

GRUPOS_ELEMENTO = {   # elemento de despesa -> grupo do "custo da Câmara"
    "11": "Pessoal e encargos", "13": "Pessoal e encargos", "46": "Pessoal e encargos", "49": "Pessoal e encargos",
    "14": "Diárias", "93": "Verba indenizatória e reembolsos",
    "39": "Despesas administrativas", "30": "Despesas administrativas", "40": "Despesas administrativas",
    "52": "Despesas administrativas", "33": "Despesas administrativas", "92": "Despesas administrativas",
}
ELEMENTOS_ADMIN = ["39", "30", "40", "52", "33", "92"]
RE_PASSAGEIRO = re.compile(r"Passageir[oa]s?\s*:\s*(.+?)\s*(?:Trecho|\n|$)", re.I)
RE_TRECHO = re.compile(r"Trecho\s*:\s*(.+?)(?:\n|$)", re.I)


def squash(s):
    return normaliza_nome(s).replace(" ", "")


def _dias(q):
    try:
        return float(str(q).replace(",", ".")) if q else 0.0
    except ValueError:
        return 0.0


def passageiros(descricao: str) -> list:
    """Nomes citados como 'Passageiro(a): ...' no histórico; vazio se o histórico não os informa."""
    return [m.strip(" .;,") for m in RE_PASSAGEIRO.findall(descricao or "") if m.strip()]


def ehdiaria(elem: str) -> bool:
    return "DIARIA" in normaliza_nome(elem)


def ehpassagem(elem: str) -> bool:
    n = normaliza_nome(elem)
    return "PASSAGEN" in n or "LOCOMOC" in n


def comparativo(fichas: list) -> list:
    """Mesma fórmula para todos: totais do período com registro na folha e médias por mês de folha."""
    out = []
    for f in sorted(fichas, key=lambda x: normaliza_nome(x["nome"])):
        m = max(f["folha"]["meses"], 1)
        linha = {"id": f["id"], "nome": f["nome"], "meses": f["folha"]["meses"], "periodo": f["periodo"], "cargos": f["cargos"],
                 "proventos": f["folha"]["proventos"], "diarias": f["diarias"]["valor"], "diarias_qtd": f["diarias"]["qtd"],
                 "verba": f["verba"]["pago"], "reembolsos": f["reembolsos"]["pago"]}
        linha["total"] = linha["proventos"] + linha["diarias"] + linha["verba"] + linha["reembolsos"]
        for k in ("proventos", "diarias", "verba", "reembolsos", "total"):
            linha[k + "_mes"] = round(linha[k] / m)
        out.append(linha)
    return out


def ficha(conn, vid: int, nome: str, ano: int, codifs: set, diarias: list, verba: list) -> dict:
    fm_todos = _rows(conn, "SELECT mes, cargo, proventos, descontos, vinculo, admissao FROM vereador_folha WHERE vereador_id=? AND ano=? ORDER BY mes", vid, ano)
    fm = [x for x in fm_todos if x["proventos"] > 0]            # "mês de exercício" = mês com proventos na folha (critério único)
    mine_d = [d for d in diarias if d["codif"] in codifs]
    di = [d for d in mine_d if ehdiaria(d["elemento"])]
    pas = []
    for d in diarias:
        if ehpassagem(d["elemento"]):
            ps = passageiros(d["descricao"])
            if len(ps) == 1 and squash(ps[0]) == squash(nome):       # só quando UM passageiro e nome completo idêntico
                t = RE_TRECHO.search(d["descricao"] or "")
                pas.append({"data": d["data"], "valor": d["valor"] - d["valor_anulado"], "trecho": (t.group(1).strip()[:120] if t else None)})
    mv = [v for v in verba if v["vereador_id"] == vid]
    vi = [v for v in mv if v["categoria"] == "verba"]
    rb = [v for v in mv if v["categoria"] == "reembolso"]
    por_mes = lambda L, k: [{"mes": m, k: s} for m, s in sorted(_soma_mes(L, k).items())]
    return {
        "id": vid, "nome": nome,
        "periodo": [fm[0]["mes"], fm[-1]["mes"]] if fm else None,
        "vinculo": fm[-1]["vinculo"] if fm else None, "admissao": fm[0]["admissao"] if fm else None,
        "folha": {"proventos": sum(x["proventos"] for x in fm), "descontos": sum(x["descontos"] for x in fm), "meses": len(fm)},
        "folha_mensal": [{"mes": x["mes"], "proventos": x["proventos"], "descontos": x["descontos"], "cargo": x["cargo"]} for x in fm_todos],
        "meses_sem_proventos": [x["mes"] for x in fm_todos if x["proventos"] <= 0],
        "cargos": sorted({x["cargo"] for x in fm_todos}),
        "diarias": {"valor": sum(d["valor"] - d["valor_anulado"] for d in di), "qtd": len(di), "dias": round(sum(_dias(d["quantidade"]) for d in di), 2),
                    "mensal": por_mes([{"data": d["data"], "v": d["valor"] - d["valor_anulado"]} for d in di], "v"),
                    "itens": [{"data": d["data"], "valor": d["valor"] - d["valor_anulado"], "dias": _dias(d["quantidade"]), "descricao": (d["descricao"] or "")[:200]}
                              for d in sorted(di, key=lambda x: x["data"] or "", reverse=True)]},
        "verba": {"pago": sum(v["pago"] for v in vi), "empenhado": sum(v["empenhado"] for v in vi), "qtd": len(vi),
                  "mensal": [{"mes": m, "pago": s} for m, s in sorted(_soma_mes([{"data": v["data_empenho"], "v": v["pago"]} for v in vi], "v").items())],
                  "itens": [{"data": v["data_empenho"], "competencia": v["competencia"], "pago": v["pago"], "empenhado": v["empenhado"]} for v in sorted(vi, key=lambda x: x["data_empenho"] or "")]},
        "reembolsos": {"pago": sum(v["pago"] for v in rb), "qtd": len(rb),
                       "itens": [{"data": v["data_empenho"], "pago": v["pago"], "historico": (v["historico"] or "")[:200]} for v in sorted(rb, key=lambda x: x["data_empenho"] or "")]},
        "passagens": {"valor": sum(p["valor"] for p in pas), "qtd": len(pas), "itens": pas},
    }


def _soma_mes(L, k):
    s = defaultdict(int)
    for x in L:
        if x["data"]:
            s[int(x["data"][5:7])] += x[k]
    return s


def publicar_camara(conn, saida: Path = None):
    saida = Path(saida or config.WEB_DATA); base = saida / "camara"
    E = "camara"
    anos = anos_com_dados(conn, E)
    pop = {r["ano"]: r["habitantes"] for r in conn.execute("SELECT ano, habitantes FROM populacao")}
    confirm = defaultdict(set)
    for r in conn.execute("SELECT codif, vereador_id FROM vereador_vinculo WHERE status='confirmado'"):
        confirm[r["vereador_id"]].add(r["codif"])
    todos_vereadores = {c for st in confirm.values() for c in st}
    vereadores, comp, verba_out, diarias_out, admin_out, custo_out = {}, {}, {}, {}, {}, {}
    for ano in anos:
        diarias = _rows(conn, "SELECT * FROM diaria WHERE entidade=? AND exercicio=?", E, ano)
        verba = _rows(conn, "SELECT * FROM verba_indenizatoria WHERE entidade=? AND exercicio=?", E, ano)
        ids = [r["id"] for r in conn.execute("SELECT DISTINCT v.id FROM vereador v JOIN vereador_folha f ON f.vereador_id=v.id WHERE f.ano=?", (ano,))]
        fichas = [ficha(conn, vid, conn.execute("SELECT nome FROM vereador WHERE id=?", (vid,)).fetchone()[0], ano, confirm[vid], diarias, verba) for vid in ids]
        ids_ano = set(ids)
        codifs_ano = {c for vid in ids for c in confirm[vid]}          # só quem foi vereador (folha) NESTE ano é tratado como vereador
        fichas.sort(key=lambda f: normaliza_nome(f["nome"]))
        vereadores[ano] = fichas
        comp[ano] = comparativo(fichas)
        # ---- verba indenizatória (matriz mês × vereador, mês do empenho)
        vi_nao = [v for v in verba if v["vereador_id"] not in ids_ano and v["categoria"] == "verba"]
        rb_nao = [v for v in verba if v["vereador_id"] not in ids_ano and v["categoria"] == "reembolso"]
        verba_out[ano] = {
            "vereadores": [{"id": f["id"], "nome": f["nome"], "total": f["verba"]["pago"], "qtd": f["verba"]["qtd"],
                            "meses": {str(m["mes"]): m["pago"] for m in f["verba"]["mensal"]}} for f in fichas],
            "total_verba": sum(v["pago"] for v in verba if v["categoria"] == "verba"),
            "total_reembolsos": sum(v["pago"] for v in verba if v["categoria"] == "reembolso"),
            "nao_vinculado": {"verba_pago": sum(v["pago"] for v in vi_nao), "verba_qtd": len(vi_nao), "reembolsos_pago": sum(v["pago"] for v in rb_nao), "reembolsos_qtd": len(rb_nao),
                              "itens": [{"data": v["data_empenho"], "pago": v["pago"], "categoria": v["categoria"], "historico": (v["historico"] or "")[:160]} for v in vi_nao]},
            "total_elemento_93_pago": conn.execute("SELECT COALESCE(SUM(pago),0) FROM empenho WHERE entidade=? AND exercicio=? AND elemento='93'", (E, ano)).fetchone()[0],
        }
        # ---- diárias
        dd = [d for d in diarias if ehdiaria(d["elemento"])]
        liq = lambda d: d["valor"] - d["valor_anulado"]
        vereadores_d = [d for d in dd if d["codif"] in codifs_ano]
        pend = [d for d in dd if d["codif"] not in codifs_ano and eh_vereador(d["cargo"])]
        serv = [d for d in dd if d["codif"] not in codifs_ano and d not in pend]
        pessoas = defaultdict(set)
        regs = []
        for d in serv:
            pessoas[d["cargo"] or "Não informado"].add(d["codif"])
        por_cargo = defaultdict(lambda: [0, 0])
        for d in serv:
            a = por_cargo[d["cargo"] or "Não informado"]; a[0] += 1; a[1] += liq(d)
        grupos = [{"cargo": c, "pessoas": len(pessoas[c]), "lancamentos": q, "valor": v} for c, (q, v) in por_cargo.items() if len(pessoas[c]) >= config.K_ANONIMATO]
        peq = [c for c in por_cargo if len(pessoas[c]) < config.K_ANONIMATO]
        if peq:
            ps = set().union(*[pessoas[c] for c in peq])
            if len(ps) >= config.K_ANONIMATO:
                grupos.append({"cargo": "Outros cargos (grupos com menos de %d pessoas)" % config.K_ANONIMATO, "pessoas": len(ps),
                               "lancamentos": sum(por_cargo[c][0] for c in peq), "valor": sum(por_cargo[c][1] for c in peq)})
        grupos.sort(key=lambda g: normaliza_nome(g["cargo"]))
        pago14 = conn.execute("SELECT COALESCE(SUM(pago),0) FROM empenho WHERE entidade=? AND exercicio=? AND elemento='14'", (E, ano)).fetchone()[0]
        diarias_out[ano] = {
            "total": sum(liq(d) for d in dd), "lancamentos": len(dd), "pago_elemento_14": pago14,
            "vereadores": {"valor": sum(liq(d) for d in vereadores_d), "lancamentos": len(vereadores_d)},
            "vereadores_pendentes": {"valor": sum(liq(d) for d in pend), "lancamentos": len(pend)},
            "servidores": {"valor": sum(liq(d) for d in serv), "lancamentos": len(serv), "por_cargo": grupos},
            "mensal": [{"mes": m, "valor": s} for m, s in sorted(_soma_mes([{"data": d["data"], "v": liq(d)} for d in dd], "v").items())],
            "passagens_e_locomocao": {"total": sum(liq(d) for d in diarias if ehpassagem(d["elemento"])),
                                      "atribuidas_a_vereador": sum(f["passagens"]["valor"] for f in fichas)},
        }
        # ---- despesas administrativas por fornecedor (nenhum nome de pessoa física é criado ou omitido: como no portal)
        adm = []
        for el in ELEMENTOS_ADMIN:
            tot = conn.execute("SELECT natureza, SUM(empenhado) e, SUM(liquidado) l, SUM(pago) p, COUNT(*) n FROM empenho WHERE entidade=? AND exercicio=? AND elemento=? GROUP BY natureza", (E, ano, el)).fetchall()
            if not tot:
                continue
            forn = []
            for f in conn.execute("SELECT f.nome, f.documento, SUM(e.empenhado) e, SUM(e.liquidado) l, SUM(e.pago) p, COUNT(*) n, f.tipo_documento tp, e.codif FROM empenho e JOIN fornecedor f ON f.entidade=e.entidade AND f.codif=e.codif "
                                  "WHERE e.entidade=? AND e.exercicio=? AND e.elemento=? GROUP BY e.codif, f.nome, f.documento, f.tipo_documento ORDER BY 3 DESC", (E, ano, el)):
                forn.append((ROTULO_PF, "", f["e"], f["l"], f["p"], f["n"]) if pf_oculta(f["tp"], el, f["codif"], todos_vereadores) else (f["nome"], f["documento"], f["e"], f["l"], f["p"], f["n"]))
            adm.append({"elemento": el, "nome": tot[0]["natureza"], "e": sum(t["e"] for t in tot), "l": sum(t["l"] for t in tot), "p": sum(t["p"] for t in tot), "n": sum(t["n"] for t in tot),
                        "fornecedores": [list(f) for f in forn]})
        admin_out[ano] = adm
        # ---- custo da Câmara
        r = conn.execute("SELECT SUM(empenhado) e, SUM(liquidado) l, SUM(pago) p FROM empenho WHERE entidade=? AND exercicio=?", (E, ano)).fetchone()
        comp_grupos = defaultdict(lambda: [0, 0, 0])
        for x in conn.execute("SELECT elemento, SUM(empenhado) e, SUM(liquidado) l, SUM(pago) p FROM empenho WHERE entidade=? AND exercicio=? GROUP BY elemento", (E, ano)):
            g = GRUPOS_ELEMENTO.get(x["elemento"], "Outros elementos")
            for i, k in enumerate(("e", "l", "p")):
                comp_grupos[g][i] += x[k]
        rec_corr = conn.execute("SELECT arrecadado FROM receita WHERE entidade='prefeitura' AND exercicio=? AND ordem=1 AND codigo LIKE '1000.%'", (ano,)).fetchone()
        rec_liq = conn.execute("SELECT SUM(arrecadado) FROM receita WHERE entidade='prefeitura' AND exercicio=? AND ordem=1", (ano,)).fetchone()[0]
        rep = conn.execute("SELECT mes, repasse, devolucao, previsto, data, pagadora, recebedora FROM transferencia WHERE entidade='prefeitura' AND exercicio=? ORDER BY linha", (ano,)).fetchall()
        recebido = [x for x in rep if "CAMARA" in normaliza_nome(x["recebedora"]) and x["repasse"]]
        devolvido = [x for x in rep if "CAMARA" in normaliza_nome(x["pagadora"]) and x["devolucao"]]
        repasse = sum(x["repasse"] for x in recebido); devol = sum(x["devolucao"] for x in devolvido)
        hab = pop.get(ano)
        custo_out[ano] = {
            "despesa": {"e": r["e"], "l": r["l"], "p": r["p"]}, "habitantes": hab,
            "por_habitante": {k: (round(r[k] / hab) if hab else None) for k in ("e", "l", "p")},
            "receita_corrente_prefeitura": rec_corr[0] if rec_corr else None, "receita_liquida_prefeitura": rec_liq,
            "pct_receita_corrente": {k: (r[k] / rec_corr[0] if rec_corr and rec_corr[0] else None) for k in ("e", "l", "p")},
            "repasse_recebido": repasse, "devolucao": devol, "repasse_liquido": repasse - devol,
            "repasse_mensal": [{"mes": x["mes"], "valor": x["repasse"], "data": x["data"], "previsto": x["previsto"]} for x in recebido],
            "devolucoes": [{"mes": x["mes"], "valor": x["devolucao"], "data": x["data"]} for x in devolvido],
            "pago_sobre_repasse_liquido": (r["p"] / (repasse - devol)) if repasse - devol else None,
            "composicao": [{"grupo": g, "e": v[0], "l": v[1], "p": v[2]} for g, v in sorted(comp_grupos.items(), key=lambda kv: kv[0])],
            "parcial": ano == __import__("datetime").date.today().year,
        }
    pend = _rows(conn, "SELECT v.codif, ve.nome vereador, v.nota, COALESCE(f.nome, d.fav) cadastro FROM vereador_vinculo v JOIN vereador ve ON ve.id=v.vereador_id "
                       "LEFT JOIN fornecedor f ON f.entidade='camara' AND f.codif=v.codif "
                       "LEFT JOIN (SELECT codif, MAX(favorecido) fav FROM diaria GROUP BY codif) d ON d.codif=v.codif WHERE v.status='sugerido' ORDER BY ve.nome")
    for p in pend:
        p["valor_pago_93_14"] = conn.execute("SELECT COALESCE(SUM(pago),0) FROM empenho WHERE entidade='camara' AND codif=? AND elemento IN ('93','14')", (p["codif"],)).fetchone()[0]
    _grava(base / "vereadores.json", {"anos": vereadores})
    _grava(base / "comparativo.json", comp)
    _grava(base / "verba.json", {"anos": verba_out, "detalhamento": {"disponivel": False, "link_oficial": URL_OFICIAL_VI},
                                 "pendencias_de_vinculo": pend})
    _grava(base / "diarias.json", diarias_out)
    _grava(base / "administrativas.json", admin_out)
    _grava(base / "custo.json", custo_out)
    return {"anos": anos, "vereadores": {a: len(v) for a, v in vereadores.items()}, "pendencias": len(pend)}
