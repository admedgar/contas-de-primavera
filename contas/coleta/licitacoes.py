"""Licitações e contratos. O portal devolve vários exercícios de uma vez; a tabela é substituída por inteiro a cada coleta."""
from __future__ import annotations

from .. import db, http
from ..parsers import ano_2dig, centavos, data_iso, limpa
from .despesas import verifica_campos


def coletar_licitacoes(conn, entidade: str, ano: int):
    with db.coleta(conn, entidade, "licitacoes", ano) as info:
        dados, info["url"], info["bytes"] = http.get_json(entidade, "LicitacoesEContratos", {
            "ConectarExercicio": ano, "Listagem": "Licitacoes", "Ano": ano, "Empresa": 1, "MostraDadosConsolidado": "False"})
        verifica_campos(dados, {"ANO", "NUMERO", "LICIT", "LICITACAO", "DATAE", "VALOR", "SITUACAO", "DISCR"}, "Licitacoes")
        conn.execute("DELETE FROM licitacao WHERE entidade=?", (entidade,))
        conn.executemany(
            "INSERT INTO licitacao (entidade, exercicio, numero, processo, modalidade, sequencial, objeto, data, "
            "data_encerramento, situacao, valor, valor_complementar, registro_preco, fundamento) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(entidade, ano_2dig(r["ANO"]), limpa(r["NUMERO"]), limpa(r.get("PROCLIC")), limpa(r["LICIT"]) or None,
              limpa(r["LICITACAO"]), limpa(r["DISCR"], 600), data_iso(r["DATAE"]), data_iso(r.get("DTENC")),
              limpa(r["SITUACAO"]), centavos(r["VALOR"]), centavos(r.get("VALOR1")), limpa(r.get("REGISTROPRECO")) or None,
              limpa(r.get("ARTIGO_INCISO")) or None) for r in dados])
        info["registros"] = len(dados)


def coletar_contratos(conn, entidade: str, ano: int):
    with db.coleta(conn, entidade, "contratos", ano) as info:
        dados, info["url"], info["bytes"] = http.get_json(entidade, "LicitacoesEContratos", {
            "ConectarExercicio": ano, "Listagem": "Contratos", "Ano": ano, "Empresa": 1,
            "MostraDadosConsolidado": "False", "ContratosApenasPublicados": "False"})
        verifica_campos(dados, {"CODIGO", "ANO", "FORNECEDOR", "VALCON", "DTASSI", "OBJETO", "MODALI"}, "Contratos")
        conn.execute("DELETE FROM contrato WHERE entidade=?", (entidade,))
        conn.executemany(
            "INSERT INTO contrato (entidade, codigo, exercicio, fornecedor, documento, objeto, modalidade, valor, aditado, "
            "empenhado, liquidado, data_assinatura, vigencia_inicio, vigencia_fim, vigencia_atual, encerramento, anulacao) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(entidade, limpa(r["CODIGO"]), int(r["ANO"]) if str(r["ANO"]).strip().isdigit() else None,
              limpa(r["FORNECEDOR"]), limpa(r.get("INSMF")), limpa(r["OBJETO"], 600), limpa(r["MODALI"]),
              centavos(r["VALCON"]), centavos(r.get("ADITADO")), centavos(r.get("EMPENHADO")), centavos(r.get("LIQUIDADO")),
              data_iso(r["DTASSI"]), data_iso(r.get("VIGENI")), data_iso(r.get("VIGENF")), data_iso(r.get("VENCIMENTO_ATUAL")),
              data_iso(r.get("DTENCERRAMENTO")), data_iso(r.get("DTANULA"))) for r in dados])
        info["registros"] = len(dados)
