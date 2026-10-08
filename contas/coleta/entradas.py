"""Outras entradas que o portal informa além da receita orçamentária: ingressos extraorçamentários (NÃO são receita) e emendas recebidas."""
from __future__ import annotations

import re
from collections import defaultdict

from .. import db, http
from ..parsers import centavos, normaliza_nome
from .despesas import params_base, verifica_campos

GRUPOS = [   # (rótulo, padrão sobre o nome normalizado). Ordem importa; nunca publica o nome individual (pode ser de pessoa).
    ("Pensão alimentícia e descontos judiciais", r"PENS|JUDIC"),
    ("Previdência, INSS e encargos sociais (inclui planos de previdência e assistência médica)", r"INSS|IMPREV|PREVID|ASSISTENCIA MEDICA|FGTS|GILRAT|SENAR|SALARIO (MATERN|FAMIL)"),
    ("Planos de saúde e odontológicos", r"UNIMED|DENTAL|SAUDE"),
    ("Empréstimos consignados e instituições financeiras", r"BANCO|BANCOOB|SICOOB|SICREDI|PRIMACREDI|CONSG|CONSIGN|EMPREST|CAIXA ECON|SANTANDER|BRADESCO|CREDITO|COOPERATIVA"),
    ("Sindicatos e associações", r"SINDIC|SINTEP|SINDACS|ASSOCIA"),
    ("Imposto de renda e tributos retidos", r"IRRF|IMPOSTO|\bISS\b|RETENC"),
    ("Garantias, cauções e depósitos", r"GARANTIA|CAUC|DEPOSITO|TERMO DE SESSAO|RECEBIMENTOS? NAO IDENTIF"),
]
OUTROS = "Demais ingressos extraorçamentários"


def grupo_extra(nomenclatura: str) -> str:
    n = normaliza_nome(re.sub(r"^\d+\s*-\s*", "", nomenclatura or ""))
    for rotulo, padrao in GRUPOS:
        if re.search(padrao, n):
            return rotulo
    return OUTROS


def coletar_extra(conn, entidade: str, ano: int):
    from datetime import date
    with db.coleta(conn, entidade, "ingressos_extra", ano) as info:
        if ano != date.today().year:
            info["mensagem"] = "ignorado: consulta de receita só confiável no exercício corrente"
            return
        dados, info["url"], info["bytes"] = http.get_json(entidade, "Receitas", params_base(ano, "ReceitaExtraOrcamentaria"))
        verifica_campos(dados, {"NOMENCLATURA", "VALOR", "DTLAN"}, "ReceitaExtraOrcamentaria")
        g = defaultdict(lambda: [0, 0])
        for r in dados:
            a = g[grupo_extra(r["NOMENCLATURA"])]
            a[0] += centavos(r["VALOR"]); a[1] += 1
        conn.execute("DELETE FROM ingresso_extra WHERE entidade=? AND exercicio=?", (entidade, ano))
        conn.executemany("INSERT INTO ingresso_extra VALUES (?,?,?,?,?)", [(entidade, ano, k, v[0], v[1]) for k, v in g.items()])
        info["registros"] = len(dados)


def coletar_emendas(conn, entidade: str, ano: int):
    with db.coleta(conn, entidade, "emendas", ano) as info:
        dados, info["url"], info["bytes"] = http.get_json(entidade, "Transferencias", {
            "ConectarExercicio": ano, "Listagem": "CadEmendasImpositivas", "Empresa": 1, "MostraDadosConsolidado": "False"})
        verifica_campos(dados, {"NUMERO_EMENDA", "ANO", "ESFERA_ORIGEM_DESCR", "VALOR_TOTAL", "AUTOR"}, "CadEmendasImpositivas")
        recebidas = [r for r in dados if "MUNICIPAL" not in normaliza_nome(r["ESFERA_ORIGEM_DESCR"])]
        conn.execute("DELETE FROM emenda_recebida WHERE entidade=?", (entidade,))
        conn.executemany("INSERT OR REPLACE INTO emenda_recebida VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
            (entidade, r["NUMERO_EMENDA"].strip(), int(r["ANO"] or 0), " ".join(r["ESFERA_ORIGEM_DESCR"].split()).split(" – ")[0],
             " ".join(r.get("TIPO_EMENDA_DESCR", "").split()).split(" – ")[0], " ".join(r.get("TIPO_TRANSFERENCIA_DESCR", "").split()).split(" – ")[0],
             " ".join((r["AUTOR"] or "").split()), centavos(r["VALOR_TOTAL"]), centavos(r.get("RECEITAANT")), centavos(r.get("RECEITA")),
             centavos(r.get("EMPENHADO")), centavos(r.get("PAGO"))) for r in recebidas])
        info["registros"] = len(recebidas)
