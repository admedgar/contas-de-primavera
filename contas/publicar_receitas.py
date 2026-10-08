"""receitas.json: de onde vem o dinheiro da Prefeitura.
 1. 'portal'  – árvore de receita do exercício corrente (portal), mês a mês, SEM dupla contagem (níveis 1,2,3,4,7).
 2. 'dca'     – SICONFI/DCA: receita bruta realizada por classificação, anos fechados (+ deduções).
 3. 'rreo'    – SICONFI/RREO: mesmo bimestre em 4 anos (comparação do mesmo período).
 4. 'extra' e 'emendas' – outras entradas (as extraorçamentárias NÃO são receita).
As fontes nunca são somadas nem comparadas entre si (perímetro e convenção diferentes)."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import config, db
from .publicar import _grava, _rows

E = "prefeitura"
CTX = {
    "portal": "Portal da Transparência da Prefeitura (somente a administração direta, valores brutos; as deduções do Fundeb aparecem à parte).",
    "siconfi": "Demonstrativos que a prefeitura declara ao Tesouro Nacional. O perímetro é o consolidado do município, que inclui receitas do regime próprio de previdência e intra-orçamentárias, e nas linhas do RREO os valores já vêm líquidos da parcela do Fundeb. Por isso estes números não coincidem com os do portal e só são comparados entre si.",
}


def arvore(linhas: list) -> list:
    """linhas: dicts em ordem de exibição com 'ordem' e 'codigo'. Devolve nós (níveis 1,2,3,4,7) com código e nível do pai.
    Atenção: um nó pode ter o MESMO código do pai (ex.: deduções do Fundeb, nível 3 e 7); o nó é identificado por (código, nível)."""
    saida, pilha = [], []
    for r in linhas:
        o = r["ordem"]
        if o not in (1, 2, 3, 4, 7):
            continue
        while pilha and pilha[-1]["ordem"] >= o:
            pilha.pop()
        no = dict(r, pai=pilha[-1]["codigo"] if pilha else None, pai_ordem=pilha[-1]["ordem"] if pilha else None)
        saida.append(no)
        pilha.append(no)
    return saida


def nivel_dca(cod: str) -> int:
    """'RO1.1.1.2.50.0.0' -> profundidade 1..7 (categoria, origem, espécie, subespécie, rubrica, alínea, subalínea)."""
    seg = cod[2:].split(".")
    if len(seg) != 7:
        return 0
    a, b, c, d, e, f, g = seg
    if b == "0": return 1
    if c == "0": return 2
    if d == "0": return 3
    if e == "00": return 4
    if f == "0": return 5
    if g == "0": return 6
    return 7


def chave_ordem(cod: str):
    return [int(x) for x in cod[2:].split(".")]


def limpa_nome_dca(conta: str) -> str:
    return re.sub(r"^[\d.]+\s*-\s*", "", conta).strip()


def dca(conn) -> dict:
    anos = [r[0] for r in conn.execute("SELECT DISTINCT exercicio FROM siconfi_receita WHERE origem='dca' ORDER BY 1")]
    if not anos:
        return None
    linhas = conn.execute("SELECT exercicio, coluna, cod_conta, conta, valor FROM siconfi_receita WHERE origem='dca'").fetchall()
    contas, tot = {}, {a: {"bruta": 0, "fundeb": 0, "outras": 0} for a in anos}
    for r in linhas:
        if r["cod_conta"] == "ReceitasExcetoIntraOrcamentarias":
            k = {"Receitas Brutas Realizadas": "bruta", "Deduções - FUNDEB": "fundeb", "Outras Deduções da Receita": "outras"}[r["coluna"]]
            tot[r["exercicio"]][k] = r["valor"]
        elif r["cod_conta"].startswith("RO") and r["coluna"] == "Receitas Brutas Realizadas":
            c = contas.setdefault(r["cod_conta"], {"c": r["cod_conta"], "n": limpa_nome_dca(r["conta"]), "o": nivel_dca(r["cod_conta"]), "v": {}})
            c["v"][str(r["exercicio"])] = r["valor"]
    for a in tot:
        tot[a]["liquida"] = tot[a]["bruta"] - tot[a]["fundeb"] - tot[a]["outras"]
    return {"anos": anos, "totais": {str(a): v for a, v in tot.items()},
            "contas": sorted((c for c in contas.values() if c["o"]), key=lambda c: chave_ordem(c["c"]))}


def rreo(conn) -> dict:
    ano_atual = conn.execute("SELECT MAX(exercicio) FROM siconfi_receita WHERE origem='rreo'").fetchone()[0]
    if not ano_atual:
        return None
    bim = conn.execute("SELECT MAX(periodo) FROM siconfi_receita WHERE origem='rreo' AND exercicio=?", (ano_atual,)).fetchone()[0]
    anos = [r[0] for r in conn.execute("SELECT DISTINCT exercicio FROM siconfi_receita WHERE origem='rreo' AND periodo=? ORDER BY 1", (bim,))]
    ordem, nomes = [], {}
    for r in conn.execute("SELECT cod_conta, conta FROM siconfi_receita WHERE origem='rreo' AND exercicio=? AND periodo=? AND coluna='Até o Bimestre (c)' ORDER BY rowid", (ano_atual, bim)):
        ordem.append(r["cod_conta"]); nomes[r["cod_conta"]] = r["conta"]
    vals = {(r["exercicio"], r["cod_conta"], r["coluna"]): r["valor"] for r in conn.execute(
        "SELECT exercicio, cod_conta, coluna, valor FROM siconfi_receita WHERE origem='rreo' AND periodo=?", (bim,))}
    linhas = []
    for cod in ordem:
        if cod.endswith("Intra") or cod == "ReceitasIntraOrcamentarias":
            continue                                           # detalhe intra-orçamentário fica de fora; o total aparece abaixo
        nome = nomes[cod]
        o = 1 if cod == "ReceitasExcetoIntraOrcamentarias" else (2 if cod in ("ReceitasCorrentes", "ReceitasDeCapital") else (3 if nome.isupper() else 4))
        if cod in ("ReceitasIntraOrcamentariasTotal", "SubtotalDasReceitas", "TotalReceitas", "TotalReceitasComDeficit"):
            if cod != "ReceitasIntraOrcamentariasTotal" and cod != "SubtotalDasReceitas":
                continue
            o = 1
        linhas.append({"c": cod, "n": nome, "o": o, "v": {str(a): vals.get((a, cod, "Até o Bimestre (c)")) for a in anos},
                       "prev": vals.get((ano_atual, cod, "PREVISÃO ATUALIZADA (a)"))})
    return {"bimestre": bim, "ano": ano_atual, "anos": anos, "mes_fim": bim * 2, "linhas": linhas}


def portal(conn) -> dict:
    ano = conn.execute("SELECT MAX(exercicio) FROM receita WHERE entidade=?", (E,)).fetchone()[0]
    if not ano:
        return None
    base = _rows(conn, "SELECT linha, ordem, codigo, nome, previsao_inicial pi, previsao_atualizada prev, arrecadado arr FROM receita WHERE entidade=? AND exercicio=? ORDER BY linha", E, ano)
    mens = {}
    for r in conn.execute("SELECT mes, codigo, ordem, arrecadado FROM receita_mensal WHERE entidade=? AND exercicio=?", (E, ano)):
        mens.setdefault((r["codigo"], r["ordem"]), {})[r["mes"]] = r["arrecadado"]
    meses = sorted({r[0] for r in conn.execute("SELECT DISTINCT mes FROM receita_mensal WHERE entidade=? AND exercicio=?", (E, ano))})
    nos = []
    for n in arvore(base):
        m = mens.get((n["codigo"], n["ordem"]), {})
        nos.append({"c": n["codigo"], "n": n["nome"], "o": n["ordem"], "p": n["pai"], "po": n["pai_ordem"], "prev": n["prev"], "arr": n["arr"],
                    "m": [m.get(i, 0) for i in range(1, 13)]})
    ult = conn.execute("SELECT fim FROM execucao_coleta WHERE entidade=? AND fonte='receita_orcamentaria' AND status='ok' AND registros>0 ORDER BY id DESC LIMIT 1", (E,)).fetchone()
    return {"ano": ano, "meses_com_dados": meses, "mes_corrente": date.today().month if ano == date.today().year else 12,
            "coleta": ult["fim"] if ult else None, "nos": nos}


def publicar_receitas(conn, saida: Path = None) -> dict:
    saida = Path(saida or config.WEB_DATA)
    ext = _rows(conn, "SELECT exercicio, grupo, valor, lancamentos FROM ingresso_extra WHERE entidade=? ORDER BY valor DESC", E)
    ano_ext = max((r["exercicio"] for r in ext), default=None)
    emendas = _rows(conn, "SELECT numero, ano, esfera, tipo, transferencia, autor, valor_total, empenhado, pago FROM emenda_recebida WHERE entidade=? ORDER BY ano DESC, numero", E)

    def ult(fonte):
        r = conn.execute("SELECT fim, url FROM execucao_coleta WHERE entidade=? AND fonte=? AND status='ok' ORDER BY id DESC LIMIT 1", (E, fonte)).fetchone()
        return (r["fim"], r["url"]) if r else (None, None)
    doc = {"contexto": CTX, "portal": portal(conn), "dca": dca(conn), "rreo": rreo(conn),
           "extra": {"ano": ano_ext, "grupos": [r for r in ext if r["exercicio"] == ano_ext], "coleta": ult("ingressos_extra")[0]} if ext else None,
           "emendas": {"itens": emendas, "coleta": ult("emendas")[0]},
           "coletas": {"siconfi_dca": ult("siconfi_dca"), "siconfi_rreo": ult("siconfi_rreo")}, "gerado_em": db.agora()}
    _grava(saida / E / "receitas.json", doc)
    return {"portal_nos": len(doc["portal"]["nos"]) if doc["portal"] else 0, "dca_contas": len(doc["dca"]["contas"]) if doc["dca"] else 0,
            "rreo_linhas": len(doc["rreo"]["linhas"]) if doc["rreo"] else 0}
