"""Coletas específicas da Câmara: folha com vereadores nominais, diárias, repasses; e derivação da verba indenizatória."""
from __future__ import annotations

import re
from collections import defaultdict

from .. import db, http
from ..parsers import centavos, data_iso, limpa, normaliza_nome
from .despesas import params_base, verifica_campos
from .mensal import ate_mes
from .pessoal import _mes_disponivel, agrega
from .vinculos import registrar_vereador

def eh_vereador(cargo: str) -> bool:
    """Cargo que COMEÇA com VEREADOR (VEREADOR, VEREADORA, VEREADOR SUPLENTE). 'ASSESSOR DE VEREADOR' não conta."""
    n = normaliza_nome(cargo)
    return n == "VEREADOR" or n.startswith("VEREADOR ") or n == "VEREADORA" or n.startswith("VEREADORA ")


def coletar_folha_camara(conn, entidade: str, ano: int):
    """Folha mês a mês. NOMINAL somente para o cargo VEREADOR; todos os demais entram só em agregados (com supressão de grupos pequenos)."""
    with db.coleta(conn, entidade, "servidores_mensal", ano) as info:
        obrig = {"NOME", "CPFFORMATADO", "CARGO", "DIVISAO", "VINCULO", "DATAADMISSAO", "PROVENTOS", "DESCONTOS"}
        conn.execute("DELETE FROM vereador_folha WHERE ano=?", (ano,))
        n_reg, n_bytes, meses_ok, url = 0, 0, [], None
        for mes in range(1, ate_mes(ano) + 1):
            dados, url, b = _mes_disponivel(entidade, ano, mes)
            n_bytes += b
            if not dados:
                continue
            verifica_campos(dados, obrig, "Servidores")
            n_reg += len(dados)
            meses_ok.append(mes)
            regs, por_vereador = [], defaultdict(lambda: [None, 0, 0, 0, None, None])
            for r in dados:
                reg = {"cargo": limpa(r["CARGO"]), "divisao": limpa(r["DIVISAO"]), "vinculo": limpa(r["VINCULO"]),
                       "proventos": centavos(r["PROVENTOS"]), "descontos": centavos(r["DESCONTOS"])}
                regs.append(reg)
                if eh_vereador(r["CARGO"]):
                    vid = registrar_vereador(conn, limpa(r["NOME"]), limpa(r["CPFFORMATADO"]))
                    a = por_vereador[vid]
                    a[0] = limpa(r["VINCULO"]); a[5] = limpa(r["CARGO"]); a[1] += reg["proventos"]; a[2] += reg["descontos"]; a[3] += 1; a[4] = data_iso(r["DATAADMISSAO"])
            for vid, (vinc, p, d, n, adm, cargo) in por_vereador.items():
                conn.execute("INSERT INTO vereador_folha VALUES (?,?,?,?,?,?,?,?,?)", (vid, ano, mes, cargo, vinc, adm, p, d, n))
            conn.execute("DELETE FROM servidor_agregado WHERE entidade=? AND ref_ano=? AND ref_mes=?", (entidade, ano, mes))
            tp, td = sum(x["proventos"] for x in regs), sum(x["descontos"] for x in regs)
            linhas = [("total", "Todos os servidores", len(regs), tp, td, tp - td)]
            for dim in ("cargo", "divisao", "vinculo"):
                linhas += [(dim, c, q, p, d, l) for c, q, p, d, l in agrega(regs, lambda s, dim=dim: s[dim])]
            conn.executemany("INSERT INTO servidor_agregado VALUES (?,?,?,?,?,?,?,?,?)", [(entidade, ano, mes, *x) for x in linhas])
            del dados, regs                     # nomes de servidores não vereadores saem da memória aqui
        info.update(url=url, bytes=n_bytes, registros=n_reg, mensagem=f"meses com folha: {meses_ok}")


def coletar_diarias(conn, entidade: str, ano: int):
    with db.coleta(conn, entidade, "diarias", ano) as info:
        dados, info["url"], info["bytes"] = http.get_json(entidade, "Despesas", params_base(ano, "Diarias"))
        verifica_campos(dados, {"PKEMP", "NEMPG", "DATA", "VALOR", "VALORANULADO", "NOME_ELEMENTO", "FAVORECIDO", "CARGO", "CODIF", "CPFFORMATADO", "DESCRICAO"}, "Diarias")
        conn.execute("DELETE FROM diaria WHERE entidade=? AND exercicio=?", (entidade, ano))
        conn.executemany(
            "INSERT INTO diaria (entidade, exercicio, pkemp, empenho, liquidacao, ordem_pagamento, data, valor, valor_anulado, quantidade, "
            "elemento, descricao, codif, favorecido, cargo, cpf_mascarado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(entidade, ano, limpa(r["PKEMP"]), limpa(r["NEMPG"]), limpa(r.get("NUMEROLIQUIDACAO")), limpa(r.get("ORDEMPAGAMENTO")),
              data_iso(r["DATA"]), centavos(r["VALOR"]), centavos(r["VALORANULADO"]), limpa(r.get("QUANT")), limpa(r["NOME_ELEMENTO"]),
              limpa(r["DESCRICAO"], 700), limpa(r["CODIF"]), limpa(r["FAVORECIDO"]), limpa(r["CARGO"]), limpa(r["CPFFORMATADO"])) for r in dados])
        info["registros"] = len(dados)


def coletar_transferencias(conn, entidade: str, ano: int):
    """Consulta Transf. A da Prefeitura traz repasse ao Legislativo (coluna REPASSE) e devolução (DEVOLUCAO) nos dois sentidos."""
    with db.coleta(conn, entidade, "transferencias", ano) as info:
        dados, info["url"], info["bytes"] = http.get_json(entidade, "Transferencias", {
            "ConectarExercicio": ano, "Listagem": "Transf", "Empresa": 1, "MostraDadosConsolidado": "False"})
        verifica_campos(dados, {"MES", "ENTIDADE_PAGADORA", "ENTIDADE_RECEBEDORA", "REPASSE", "DEVOLUCAO", "PREVISTO", "DTLAN"}, "Transf")
        conn.execute("DELETE FROM transferencia WHERE entidade=? AND exercicio=?", (entidade, ano))
        conn.executemany("INSERT INTO transferencia VALUES (?,?,?,?,?,?,?,?,?,?)", [
            (entidade, ano, i, int(r["MES"] or 0), limpa(r["ENTIDADE_PAGADORA"]), limpa(r["ENTIDADE_RECEBEDORA"]),
             centavos(r["REPASSE"]), centavos(r["DEVOLUCAO"]), centavos(r["PREVISTO"]), data_iso(r["DTLAN"])) for i, r in enumerate(dados)])
        info["registros"] = len(dados)


_MESES = {m: i + 1 for i, m in enumerate("JANEIRO FEVEREIRO MARCO ABRIL MAIO JUNHO JULHO AGOSTO SETEMBRO OUTUBRO NOVEMBRO DEZEMBRO".split())}


def competencia(historico: str):
    """AAAA-MM se o histórico a informa ('REF: 01/2026' ou 'MES DE MAIO 2026'); senão None."""
    h = normaliza_nome(historico)
    m = re.search(r"REF\.?:?\s*(\d{1,2})\s*/\s*(\d{4})", h)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    m = re.search(r"MES DE (" + "|".join(_MESES) + r")\s*(?:DE\s*)?(\d{4})", h)
    return f"{m.group(2)}-{_MESES[m.group(1)]:02d}" if m else None


def categoria_93(historico: str) -> str:
    return "verba" if "VERBA INDENIZAT" in normaliza_nome(historico) else "reembolso"


def derivar_verba(conn, entidade: str, ano: int) -> int:
    """Elemento 93 (Indenizações e Restituições): separa 'verba' (histórico cita verba indenizatória) de 'reembolso'."""
    vinc = {r["codif"]: r["vereador_id"] for r in conn.execute("SELECT codif, vereador_id FROM vereador_vinculo WHERE status='confirmado'")}
    conn.execute("DELETE FROM verba_indenizatoria WHERE entidade=? AND exercicio=?", (entidade, ano))
    rows = conn.execute("SELECT pkemp, codif, data, historico, empenhado, liquidado, pago FROM empenho WHERE entidade=? AND exercicio=? AND elemento='93'", (entidade, ano)).fetchall()
    conn.executemany("INSERT INTO verba_indenizatoria VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
        (entidade, ano, r["pkemp"], vinc.get(r["codif"]), r["codif"], r["data"], competencia(r["historico"]), categoria_93(r["historico"]),
         r["empenhado"], r["liquidado"], r["pago"], r["historico"]) for r in rows])
    conn.commit()
    return len(rows)
