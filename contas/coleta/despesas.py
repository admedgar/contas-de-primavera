"""Empenhos do ano (DespesasGerais, ~42 MB na Prefeitura): UMA carga pesada por dia, gravada em disco e processada localmente."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from .. import config, db, http
from ..parsers import centavos, data_iso, limpa, tipo_documento

log = logging.getLogger("contas.despesas")

OBRIGATORIOS = {"PKEMP", "CODIGO", "TPEM", "CODIF", "NOMEFOR", "DATAE", "CODLO", "ELEMENTO",
                "EMPENHADO", "LIQUIDADO", "PAGO", "CPFFORMATADO"}


class FormatoMudou(RuntimeError):
    """A resposta do portal não tem os campos que o coletor espera."""


def periodo(ano: int, mes_ini: int = 1, mes_fim: int = 12) -> dict:
    import calendar
    return {"DiaInicioPeriodo": "01", "MesInicialPeriodo": f"{mes_ini:02d}",
            "DiaFinalPeriodo": f"{calendar.monthrange(ano, mes_fim)[1]:02d}", "MesFinalPeriodo": f"{mes_fim:02d}",
            "Ano": ano}


def params_base(ano: int, listagem: str, mes_ini: int = 1, mes_fim: int = 12, **extra) -> dict:
    p = {"ConectarExercicio": ano, "Listagem": listagem, **periodo(ano, mes_ini, mes_fim),
         "Empresa": 1, "MostraDadosConsolidado": "False"}
    p.update(extra)
    return p


def verifica_campos(registros: list, obrigatorios: set, fonte: str):
    if not registros:
        return
    faltam = obrigatorios - set(registros[0].keys())
    if faltam:
        raise FormatoMudou(f"{fonte}: campos ausentes {sorted(faltam)} (o portal mudou o formato?)")


def converte_empenho(entidade: str, ano: int, r: dict) -> tuple:
    orgao = r["CODLO"][:4]
    return (entidade, ano, r["PKEMP"], limpa(r["CODIGO"]), limpa(r["TPEM"]), limpa(r.get("PKEMPA")) or None,
            limpa(r["CODIF"]), data_iso(r["DATAE"]), orgao, r["CODLO"],
            limpa(r.get("FUNCAONOME")), limpa(r.get("SUBFUNCAONOME")), limpa(r.get("PROGRAMANOME")),
            limpa(r.get("PROJETO_ATIVIDADE_NOME")), limpa(r["ELEMENTO"]), limpa(r.get("NATUREZA")),
            limpa(r.get("FONTE_STNDESC") or r.get("DESCFONREC")),
            limpa(r.get("DESCLICIT_DETALHESEMPENHO")), limpa(r.get("PRODU"), 400),
            centavos(r["EMPENHADO"]), centavos(r["LIQUIDADO"]), centavos(r["PAGO"]))


def _baixar_com_cache(entidade: str, ano: int, force: bool):
    hoje = date.today().isoformat()
    destino = config.RAW_DIR / f"{entidade}_despesas_gerais_{ano}_{hoje}.json"
    params = params_base(ano, "DespesasGerais", MostrarFornecedor="True", UFParaFiltroCOVID="",
                         MostrarCNPJFornecedor="True", ApenasIDEmpenho="False")
    if destino.exists() and not force:
        log.info("reutilizando download de hoje: %s", destino.name)
        dados = http._decodifica(destino.read_bytes(), str(destino))
        return dados, http.url_consulta(entidade, "Despesas", params), destino.stat().st_size
    dados, url, n = http.baixar(entidade, "Despesas", params, destino)
    for velho in config.RAW_DIR.glob(f"{entidade}_despesas_gerais_{ano}_*.json"):
        if velho != destino and velho.stat().st_mtime < destino.stat().st_mtime - 3 * 86400:
            velho.unlink()
    return dados, url, n


def coletar_empenhos(conn, entidade: str, ano: int, force: bool = False) -> int:
    with db.coleta(conn, entidade, "despesas_gerais", ano) as info:
        dados, info["url"], info["bytes"] = _baixar_com_cache(entidade, ano, force)
        if not isinstance(dados, list):
            raise FormatoMudou("DespesasGerais não devolveu uma lista")
        verifica_campos(dados, OBRIGATORIOS, "DespesasGerais")
        linhas, forn, avisos = [], {}, []
        vistos = set()
        for r in dados:
            if r["PKEMP"] in vistos:
                raise FormatoMudou(f"PKEMP duplicado na resposta: {r['PKEMP']}")
            vistos.add(r["PKEMP"])
            linhas.append(converte_empenho(entidade, ano, r))
            doc = limpa(r["CPFFORMATADO"])
            novo = (limpa(r["NOMEFOR"]), doc)
            if r["CODIF"] in forn and forn[r["CODIF"]] != novo:
                avisos.append(f"CODIF {r['CODIF']} com nomes/documentos diferentes")
            forn[r["CODIF"]] = novo
        conn.execute("DELETE FROM empenho WHERE entidade=? AND exercicio=?", (entidade, ano))
        conn.executemany("INSERT INTO empenho VALUES (" + ",".join("?" * 22) + ")", linhas)
        conn.executemany(
            "INSERT INTO fornecedor VALUES (?,?,?,?,?) ON CONFLICT(entidade, codif) DO UPDATE SET "
            "nome=excluded.nome, documento=excluded.documento, tipo_documento=excluded.tipo_documento",
            [(entidade, c, n, d, tipo_documento(d)) for c, (n, d) in forn.items()])
        info["registros"] = len(linhas)
        if avisos:
            info["mensagem"] = f"{len(avisos)} aviso(s): " + "; ".join(avisos[:5])
        return len(linhas)


def coletar_totais_portal(conn, entidade: str, ano: int):
    """Totais que o próprio portal informa (para conferência) + nomes de órgãos e unidades."""
    with db.coleta(conn, entidade, "totais_portal", ano) as info:
        orgaos, url, n1 = http.get_json(entidade, "Despesas", params_base(ano, "DespesasPorOrgao"))
        unidades, _, n2 = http.get_json(entidade, "Despesas", params_base(ano, "DespesasPorUnidade"))
        forn, _, n3 = http.get_json(entidade, "Despesas",
                                    params_base(ano, "DespesasPorFornecedor", MostrarFornecedor="True"))
        info.update(url=url, bytes=n1 + n2 + n3, registros=len(orgaos) + len(unidades) + len(forn))
        verifica_campos(orgaos, {"CODIGO", "DESCRICAO", "EMPENHADO", "LIQUIDADO", "PAGO"}, "DespesasPorOrgao")
        verifica_campos(forn, {"CODIGO", "DESCRICAO", "EMPENHADO", "LIQUIDADO", "PAGO"}, "DespesasPorFornecedor")
        agora = db.agora()
        soma = lambda L, k: sum(centavos(r[k]) for r in L)
        dot = sum(centavos(r.get("DOTACAO_ATUALIZADA")) for r in orgaos)
        conn.execute("DELETE FROM orgao_total_portal WHERE entidade=? AND exercicio=?", (entidade, ano))
        for o in orgaos:
            conn.execute("INSERT OR REPLACE INTO orgao VALUES (?,?,?)", (entidade, o["CODIGO"], limpa(o["DESCRICAO"])))
            conn.execute("INSERT INTO orgao_total_portal VALUES (?,?,?,?,?,?,?)",
                         (entidade, ano, o["CODIGO"], centavos(o["EMPENHADO"]), centavos(o["LIQUIDADO"]),
                          centavos(o["PAGO"]), centavos(o.get("DOTACAO_ATUALIZADA"))))
        for u in unidades:
            conn.execute("INSERT OR REPLACE INTO unidade VALUES (?,?,?,?)",
                         (entidade, u["CODIGO"], u["CODIGO"][:4], limpa(u["DESCRICAO"])))
        for origem, L, d in (("por_orgao", orgaos, dot), ("por_fornecedor", forn, None)):
            conn.execute("INSERT OR REPLACE INTO total_portal VALUES (?,?,?,?,?,?,?,?)",
                         (entidade, ano, origem, soma(L, "EMPENHADO"), soma(L, "LIQUIDADO"), soma(L, "PAGO"), d, agora))


def totais_orgao_ate(entidade: str, ano: int, data_iso: str) -> dict:
    """Empenhado por órgão de 1º/jan até a data (consulta de totais do portal). Usado para provar que o detalhe está completo até a data."""
    d = date.fromisoformat(data_iso)
    p = {"ConectarExercicio": ano, "Listagem": "DespesasPorOrgao", "DiaInicioPeriodo": "01", "MesInicialPeriodo": "01",
         "DiaFinalPeriodo": f"{d.day:02d}", "MesFinalPeriodo": f"{d.month:02d}", "Ano": ano, "Empresa": 1, "MostraDadosConsolidado": "False"}
    linhas, _, _ = http.get_json(entidade, "Despesas", p)
    return {r["CODIGO"]: centavos(r["EMPENHADO"]) for r in linhas}
