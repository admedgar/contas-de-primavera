"""Folha: lê os servidores, AGREGA em memória e grava só agregados. Nomes de servidores nunca são gravados nesta etapa
(a exceção, os vereadores, é tratada na coleta da Câmara).
Grupos com menos de K servidores viram 'Outros' para não expor o salário de uma pessoa identificável pelo cargo."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

from .. import config, db, http
from ..parsers import centavos, limpa

log = logging.getLogger("contas.pessoal")
OUTROS = "Outros (grupos com menos de %d servidores)" % config.K_ANONIMATO


def agrega(servidores: list, chave_fn, k: int = config.K_ANONIMATO) -> list:
    """servidores: [{'proventos':int,'descontos':int,...}] -> [(chave, qtd, proventos, descontos, liquido)] com supressão."""
    g = defaultdict(lambda: [0, 0, 0])
    for s in servidores:
        a = g[chave_fn(s) or "Não informado"]
        a[0] += 1; a[1] += s["proventos"]; a[2] += s["descontos"]
    grandes = [(c, q, p, d, p - d) for c, (q, p, d) in g.items() if q >= k]
    peq = [(q, p, d) for q, p, d in g.values() if q < k]
    if peq:
        q, p, d = (sum(x[i] for x in peq) for i in range(3))
        if q >= k:               # só mostra "Outros" se o agrupado também não identifica ninguém
            grandes.append((OUTROS, q, p, d, p - d))
    return sorted(grandes, key=lambda x: -x[2])


def _mes_disponivel(entidade: str, ano: int, mes: int):
    dados, url, n = http.get_json(entidade, "Pessoal", {
        "ConectarExercicio": ano, "Listagem": "Servidores", "Empresa": 1, "Ano": ano, "MesFinalPeriodo": f"{mes:02d}"})
    return dados, url, n


def coletar_folha(conn, entidade: str, ano: int):
    with db.coleta(conn, entidade, "servidores", ano) as info:
        hoje = date.today()
        a, m = (ano, hoje.month if ano == hoje.year else 12)
        for _ in range(3):                       # mês corrente pode ainda não ter folha: recua até 2 meses
            dados, url, n = _mes_disponivel(entidade, a, m)
            if dados:
                break
            a, m = (a, m - 1) if m > 1 else (a - 1, 12)
        else:
            raise http.FonteIndisponivel("nenhuma folha encontrada nos últimos 3 meses")
        obrig = {"CARGO", "DIVISAO", "VINCULO", "PROVENTOS", "DESCONTOS"}
        faltam = obrig - set(dados[0])
        if faltam:
            raise RuntimeError(f"Servidores: campos ausentes {sorted(faltam)}")
        regs = [{"cargo": limpa(r["CARGO"]), "divisao": limpa(r["DIVISAO"]), "vinculo": limpa(r["VINCULO"]),
                 "proventos": centavos(r["PROVENTOS"]), "descontos": centavos(r["DESCONTOS"])} for r in dados]
        del dados                                # nomes saem da memória aqui
        conn.execute("DELETE FROM servidor_agregado WHERE entidade=? AND ref_ano=? AND ref_mes=?", (entidade, a, m))
        tp, td = sum(r["proventos"] for r in regs), sum(r["descontos"] for r in regs)
        linhas = [("total", "Todos os servidores", len(regs), tp, td, tp - td)]
        for dim in ("cargo", "divisao", "vinculo"):
            linhas += [(dim, c, q, p, d, l) for c, q, p, d, l in agrega(regs, lambda s, dim=dim: s[dim])]
        conn.executemany("INSERT INTO servidor_agregado VALUES (?,?,?,?,?,?,?,?,?)",
                         [(entidade, a, m, *x) for x in linhas])
        info.update(url=url, bytes=n, registros=len(regs), mensagem=f"folha de {m:02d}/{a}")
