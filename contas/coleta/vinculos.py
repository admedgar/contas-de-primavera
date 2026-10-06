"""Quem é quem: liga cadastros de favorecido (CODIF) aos vereadores, SEM adivinhar.
 - 'confirmado' por regra: CPF mascarado idêntico E nome idêntico ignorando acento/caixa/espaços (cobre "HENRIQUEDE" × "HENRIQUE DE").
 - 'sugerido': nome idêntico mas documento diferente (ex.: cadastro com CNPJ), ou CPF mascarado idêntico com nome diferente,
   ou nome muito parecido. NÃO entra nas somas; fica como pendência até o cliente decidir em config/vinculos_vereadores.csv.
 - decisões do arquivo (confirmar/rejeitar) prevalecem sobre a regra."""
from __future__ import annotations

import csv
import difflib
from pathlib import Path

from .. import config, db
from ..parsers import normaliza_nome

ARQUIVO = config.RAIZ / "config" / "vinculos_vereadores.csv"


def squash(nome: str) -> str:
    return normaliza_nome(nome).replace(" ", "")


def similaridade(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, squash(a), squash(b)).ratio()


def registrar_vereador(conn, nome: str, cpf_mascarado: str) -> int:
    """Devolve o id do vereador; reconhece a mesma pessoa com grafia levemente diferente (mesmo CPF mascarado)."""
    for r in conn.execute("SELECT id, nome FROM vereador WHERE cpf_mascarado=?", (cpf_mascarado,)).fetchall():
        if squash(r["nome"]) == squash(nome) or similaridade(r["nome"], nome) >= 0.9:
            conn.execute("UPDATE vereador SET nome=?, nome_norm=? WHERE id=?", (nome, normaliza_nome(nome), r["id"]))
            return r["id"]
    return conn.execute("INSERT INTO vereador (nome, nome_norm, cpf_mascarado) VALUES (?,?,?)",
                        (nome, normaliza_nome(nome), cpf_mascarado)).lastrowid


def classifica(vereador: dict, nome: str, doc: str):
    """-> 'confirmado' | 'sugerido' | None"""
    mesmo_cpf = bool(doc) and doc == vereador["cpf_mascarado"]
    nome_igual = squash(nome) == squash(vereador["nome"])
    if mesmo_cpf and nome_igual:
        return "confirmado", "CPF mascarado e nome idênticos"
    if nome_igual:
        return "sugerido", f"nome idêntico, documento diferente ({doc or 'sem documento'})"
    if mesmo_cpf:
        return "sugerido", "CPF mascarado idêntico, nome diferente"
    if similaridade(nome, vereador["nome"]) >= 0.93:
        return "sugerido", "nome muito parecido"
    return None, None


def candidatos(conn, entidade: str) -> dict:
    """{codif: (nome, documento)} de fornecedores e de favorecidos de diárias."""
    c = {r["codif"]: (r["nome"], r["documento"] or "") for r in conn.execute("SELECT codif, nome, documento FROM fornecedor WHERE entidade=?", (entidade,))}
    for r in conn.execute("SELECT DISTINCT codif, favorecido, cpf_mascarado FROM diaria WHERE entidade=? AND codif IS NOT NULL AND favorecido IS NOT NULL", (entidade,)):
        c.setdefault(r["codif"], (r["favorecido"], r["cpf_mascarado"] or ""))
    return c


def le_decisoes(caminho: Path = ARQUIVO) -> list:
    if not Path(caminho).exists():
        return []
    linhas = [l for l in Path(caminho).read_text(encoding="utf-8").splitlines() if l.strip() and not l.lstrip().startswith("#")]
    return list(csv.DictReader(linhas, delimiter=";"))


def vincular(conn, entidade: str = "camara", arquivo: Path = ARQUIVO) -> dict:
    ver = [dict(r) for r in conn.execute("SELECT * FROM vereador")]
    manual = {}
    for d in le_decisoes(arquivo):
        alvo = next((v for v in ver if squash(v["nome"]) == squash(d["vereador"])), None)
        if alvo is None:
            raise ValueError(f"vinculos_vereadores.csv: vereador '{d['vereador']}' não existe na folha coletada")
        if d["decisao"].strip() not in ("confirmar", "rejeitar"):
            raise ValueError(f"vinculos_vereadores.csv: decisão inválida '{d['decisao']}' (use confirmar ou rejeitar)")
        manual[d["codif"].strip()] = (alvo["id"], "confirmado" if d["decisao"].strip() == "confirmar" else "rejeitado", d.get("nota", "").strip())
    conn.execute("DELETE FROM vereador_vinculo")
    for codif, (nome, doc) in candidatos(conn, entidade).items():
        if codif in manual:
            vid, st, nota = manual[codif]
            conn.execute("INSERT INTO vereador_vinculo VALUES (?,?,?,?,?)", (codif, vid, st, "manual", nota or None))
            continue
        melhor = None
        for v in ver:
            st, motivo = classifica(v, nome, doc)
            if st and (melhor is None or (st == "confirmado" and melhor[1] != "confirmado")):
                melhor = (v["id"], st, motivo)
        if melhor:
            conn.execute("INSERT INTO vereador_vinculo VALUES (?,?,?,?,?)", (codif, melhor[0], melhor[1], "regra", melhor[2]))
    conn.commit()
    return resumo_vinculos(conn)


def resumo_vinculos(conn) -> dict:
    r = {s: n for s, n in conn.execute("SELECT status, COUNT(*) FROM vereador_vinculo GROUP BY status")}
    return {"confirmado": r.get("confirmado", 0), "sugerido": r.get("sugerido", 0), "rejeitado": r.get("rejeitado", 0)}
