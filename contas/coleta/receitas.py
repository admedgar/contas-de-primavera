"""Receita orçamentária do PORTAL. A fonte é uma ÁRVORE (códigos repetidos em níveis diferentes: o nível 10 só repete o nível 7 dividido por
vinculação), então somar tudo triplica o total. Os totais confiáveis estão nas linhas ORDEM 1 (categorias) e, abaixo, 2, 3, 4 e 7 (rubricas).
IMPORTANTE: a consulta só entrega arrecadação do exercício CORRENTE; para anos fechados devolve o plano do ano atual com tudo zerado.
Esses zeros nunca são gravados (e os já gravados são apagados); o histórico vem do SICONFI (coleta/siconfi.py)."""
from __future__ import annotations

from datetime import date

from .. import db, http
from ..parsers import centavos, limpa
from .despesas import params_base, verifica_campos
from .mensal import ate_mes

OBRIG = {"ORDEM", "CODIGO", "NOME", "PREVISAO_INICIAL", "PREVISAO_ATUALIZADA", "ARRECADADO_PERIODO", "ARRECADADO_TOTAL"}
NIVEIS_UTEIS = (1, 2, 3, 4, 7)


def topo(linhas: list) -> list:
    return [r for r in linhas if str(r["ORDEM"]).strip() == "1"]


def limpar_exercicios_zerados(conn, entidade: str, hoje: date = None) -> int:
    """Apaga receita de exercícios FECHADOS cuja arrecadação total é zero (resíduo do comportamento da API descrito acima)."""
    ano_atual = (hoje or date.today()).year
    n = 0
    for (ano,) in conn.execute("SELECT DISTINCT exercicio FROM receita WHERE entidade=? AND exercicio<?", (entidade, ano_atual)).fetchall():
        if conn.execute("SELECT COALESCE(SUM(ABS(arrecadado)),0) FROM receita WHERE entidade=? AND exercicio=?", (entidade, ano)).fetchone()[0] == 0:
            for t in ("receita", "receita_mensal_topo", "receita_mensal"):
                n += conn.execute(f"DELETE FROM {t} WHERE entidade=? AND exercicio=?", (entidade, ano)).rowcount
    conn.commit()
    return n


def coletar_receitas(conn, entidade: str, ano: int, hoje: date = None):
    hoje = hoje or date.today()
    with db.coleta(conn, entidade, "receita_orcamentaria", ano) as info:
        apagados = limpar_exercicios_zerados(conn, entidade, hoje)
        if ano != hoje.year:
            info["mensagem"] = "ignorado: o portal só informa arrecadação do exercício corrente" + (f"; {apagados} linhas zeradas removidas" if apagados else "")
            info["registros"] = 0
            return
        dados, info["url"], b = http.get_json(entidade, "Receitas", params_base(ano, "ReceitaOrcamentaria"))
        verifica_campos(dados, OBRIG, "ReceitaOrcamentaria")
        conn.execute("DELETE FROM receita WHERE entidade=? AND exercicio=?", (entidade, ano))
        conn.executemany("INSERT INTO receita VALUES (?,?,?,?,?,?,?,?,?)", [
            (entidade, ano, i, int(r["ORDEM"] or 0), r["CODIGO"], limpa(r["NOME"]),
             centavos(r["PREVISAO_INICIAL"]), centavos(r["PREVISAO_ATUALIZADA"]), centavos(r["ARRECADADO_TOTAL"]))
            for i, r in enumerate(dados)])
        conn.execute("DELETE FROM receita_mensal_topo WHERE entidade=? AND exercicio=?", (entidade, ano))
        conn.execute("DELETE FROM receita_mensal WHERE entidade=? AND exercicio=?", (entidade, ano))
        n = len(dados)
        for mes in range(1, ate_mes(ano) + 1):
            m, _, b2 = http.get_json(entidade, "Receitas", params_base(ano, "ReceitaOrcamentaria", mes, mes))
            b += b2
            n += len(m)
            for r in m:
                o = int(str(r["ORDEM"]).strip() or 0)
                if o in NIVEIS_UTEIS:
                    v = centavos(r["ARRECADADO_PERIODO"])
                    conn.execute("INSERT OR REPLACE INTO receita_mensal VALUES (?,?,?,?,?,?,?)", (entidade, ano, mes, r["CODIGO"], o, limpa(r["NOME"]), v))
                    if o == 1:
                        conn.execute("INSERT OR REPLACE INTO receita_mensal_topo VALUES (?,?,?,?,?,?)", (entidade, ano, mes, r["CODIGO"], limpa(r["NOME"]), v))
        info["registros"], info["bytes"] = n, b
