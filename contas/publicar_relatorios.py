"""Publica os relatórios (semana/mês) do banco em web/data/relatorios/. O site só lê estes JSONs."""
from __future__ import annotations

import json
from pathlib import Path

from . import config, db
from .publicar import LINKS_PORTAL, _grava
from .relatorio import MIN_DIAS_MES, MIN_DIAS_SEMANA

PUBLICAR_SEMANAS = 12
PUBLICAR_MESES = 12


def publicar_relatorios(conn, saida: Path | None = None) -> dict:
    base = Path(saida or config.WEB_DATA) / "relatorios"
    itens, padrao = {}, {}
    for ent in config.ENTIDADES:
        itens[ent], padrao[ent] = {}, {}
        coleta = conn.execute("SELECT fim FROM execucao_coleta WHERE entidade=? AND fonte='despesas_gerais' AND status='ok' ORDER BY id DESC LIMIT 1", (ent,)).fetchone()
        for tipo, limite in (("semana", PUBLICAR_SEMANAS), ("mes", PUBLICAR_MESES)):
            rows = conn.execute("SELECT * FROM relatorio WHERE entidade=? AND tipo=? ORDER BY chave DESC LIMIT ?", (ent, tipo, limite)).fetchall()
            lista = []
            for r in rows:
                f, t = json.loads(r["fatos"]), json.loads(r["texto"])
                lista.append({"chave": r["chave"], "rotulo": f["rotulo"], "inicio": f["inicio"], "fim": f["fim"], "ate": f["ate"], "parcial": f["parcial"],
                              "dias": f["dias_com_registro"], "origem": r["origem"]})
                _grava(base / f"{ent}_{tipo}_{r['chave']}.json",
                       {"fatos": f, "texto": t, "origem": r["origem"], "modelo": r["modelo"], "gerado_em": r["gerado_em"],
                        "coleta": coleta["fim"] if coleta else None, "portal": LINKS_PORTAL[ent]})
            itens[ent][tipo] = lista
            if lista:
                atual = lista[0]
                # período corrente com pouco dado (início da semana/do mês) não é o principal: mostra o último completo
                minimo = MIN_DIAS_SEMANA if tipo == "semana" else MIN_DIAS_MES
                usar = 1 if (atual["parcial"] and atual["dias"] < minimo and len(lista) > 1) else 0
                padrao[ent][tipo] = lista[usar]["chave"]
    idx = {"gerado_em": db.agora(), "itens": itens, "padrao": padrao,
           "ia_em_uso": any(i["origem"] == "ia" for ent in itens.values() for lst in ent.values() for i in lst[:1])}
    _grava(base / "index.json", idx)
    return idx
