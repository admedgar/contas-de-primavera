"""Gera os JSONs estáticos que o site consome (o site NUNCA consulta a API do portal). Valores em centavos."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import config, db
from .coleta.receitas import topo  # noqa: F401  (regra documentada: topo = ORDEM 1)

TZ_CUIABA = timezone(timedelta(hours=-4))
LINKS_PORTAL = {
    "prefeitura": "https://scpi.primaveradoleste.mt.gov.br/transparencia/",
    "camara": "https://scpi.primaveradoleste.mt.gov.br/transparenciacamara/",
}
ROTULOS_FONTE = {
    "despesas_gerais": "Despesas – empenhos do ano (DespesasGerais)",
    "totais_portal": "Totais do portal (DespesasPorOrgao/Unidade/Fornecedor)",
    "mensal": "Despesas mês a mês (DespesasPorFornecedor, DespesasPorOrgao)",
    "receita_orcamentaria": "Receita orçamentária",
    "licitacoes": "Licitações", "contratos": "Contratos", "servidores": "Folha de pagamento (agregada)",
    "ibge_populacao": "População estimada (IBGE)",
}


def _grava(caminho: Path, obj):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _rows(conn, sql, *a):
    return [dict(r) for r in conn.execute(sql, a)]


def anos_com_dados(conn, entidade):
    return [r[0] for r in conn.execute("SELECT DISTINCT exercicio FROM empenho WHERE entidade=? ORDER BY 1", (entidade,))]


def contador(conn, entidade: str, ano: int, tot: dict, coleta_iso: str, habitantes):
    """Parâmetros do contador (ESTIMATIVA linear): taxa média por segundo desde 1º/jan até o momento da coleta."""
    if ano != date.today().year or not coleta_iso:
        return None
    ini = datetime(ano, 1, 1, tzinfo=TZ_CUIABA)
    fim = datetime.strptime(coleta_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    seg = max((fim - ini).total_seconds(), 1.0)
    dias = seg / 86400
    return {"ano": ano, "coleta_em": coleta_iso, "inicio_ano": ini.isoformat(), "dias_decorridos": round(dias, 2),
            "medidas": {m: {"base": tot[m], "centavos_por_segundo": tot[m] / seg} for m in ("empenhado", "liquidado", "pago")},
            "habitantes": habitantes}


def pf_oculta(tipo_doc, elemento, codif, vereadores_ok) -> bool:
    """Política de privacidade para PESSOA FÍSICA em listas publicadas (por linha de empenho). Vereadores confirmados ficam nominais.
    - CPF mascarado: oculto quando o elemento não é de serviço/material (config.ELEMENTOS_PF_VISIVEIS).
    - Qualquer documento: oculto nos elementos 'sempre pessoa' (diárias, auxílios a pessoas físicas, premiações)."""
    if codif in vereadores_ok or config.PF_POLITICA == "portal":
        return False
    if config.PF_POLITICA == "todos" and tipo_doc == "cpf_mascarado":
        return True
    if elemento in config.ELEMENTOS_SEMPRE_PESSOA:
        return True
    return tipo_doc == "cpf_mascarado" and elemento not in config.ELEMENTOS_PF_VISIVEIS


ROTULO_PF = "Pessoa física (nome omitido)"


def publicar(conn, entidade: str, saida: Path = None) -> dict:
    saida = Path(saida or config.WEB_DATA)
    base = saida / entidade
    anos = anos_com_dados(conn, entidade)
    pop = {r["ano"]: dict(r) for r in conn.execute("SELECT * FROM populacao")}
    nomes_orgao = {r["codigo"]: r["nome"] for r in conn.execute("SELECT codigo, nome FROM orgao WHERE entidade=?", (entidade,))}
    nomes_unid = {r["codigo"]: r["nome"] for r in conn.execute("SELECT codigo, nome FROM unidade WHERE entidade=?", (entidade,))}

    def ult_coleta(fonte, ano=None):
        fontes = (fonte,) if isinstance(fonte, str) else tuple(fonte)
        r = conn.execute(f"SELECT fim FROM execucao_coleta WHERE entidade=? AND fonte IN ({','.join('?' * len(fontes))}) AND status='ok' "
                         + ("AND exercicio=? " if ano else "") + "ORDER BY id DESC LIMIT 1",
                         (entidade, *fontes, *((ano,) if ano else ()))).fetchone()
        return r["fim"] if r else None

    resumo, mensal, secretarias, funcoes, elementos, fornecedores_idx = {}, {}, {}, {}, {}, {}
    vereadores_ok = {r[0] for r in conn.execute("SELECT codif FROM vereador_vinculo WHERE status='confirmado'")}
    for ano in anos:
        t = dict(conn.execute("SELECT SUM(empenhado) empenhado, SUM(liquidado) liquidado, SUM(pago) pago, COUNT(*) qtd, MAX(data) ultimo "
                              "FROM empenho WHERE entidade=? AND exercicio=?", (entidade, ano)).fetchone())
        dot = conn.execute("SELECT SUM(dotacao_atualizada) d FROM orgao_total_portal WHERE entidade=? AND exercicio=?", (entidade, ano)).fetchone()["d"]
        hab = (pop.get(ano) or {}).get("habitantes")
        coleta = ult_coleta("despesas_gerais", ano)
        resumo[ano] = {**t, "dotacao_atualizada": dot, "habitantes": hab, "coleta_empenhos": coleta,
                       "contador": contador(conn, entidade, ano, t, coleta, hab)}
        mensal[ano] = _rows(conn, "SELECT mes, SUM(empenhado) e, SUM(liquidado) l, SUM(pago) p FROM mensal_orgao "
                                  "WHERE entidade=? AND exercicio=? GROUP BY mes ORDER BY mes", entidade, ano)
        sec = []
        for o in _rows(conn, "SELECT t.orgao codigo, t.empenhado e, t.liquidado l, t.pago p, t.dotacao_atualizada dot "
                             "FROM orgao_total_portal t WHERE t.entidade=? AND t.exercicio=? ORDER BY t.empenhado DESC", entidade, ano):
            o["nome"] = nomes_orgao.get(o["codigo"], o["codigo"])
            o["mensal"] = _rows(conn, "SELECT mes, empenhado e, liquidado l, pago p FROM mensal_orgao "
                                      "WHERE entidade=? AND exercicio=? AND orgao=? ORDER BY mes", entidade, ano, o["codigo"])
            sec.append(o)
        secretarias[ano] = sec
        funcoes[ano] = _rows(conn, "SELECT COALESCE(NULLIF(funcao,''),'Não informada') nome, SUM(empenhado) e, SUM(liquidado) l, SUM(pago) p "
                                   "FROM empenho WHERE entidade=? AND exercicio=? GROUP BY 1 ORDER BY 2 DESC", entidade, ano)
        elementos[ano] = _rows(conn, "SELECT elemento codigo, natureza nome, SUM(empenhado) e, SUM(liquidado) l, SUM(pago) p "
                                     "FROM empenho WHERE entidade=? AND exercicio=? GROUP BY 1,2 ORDER BY 3 DESC", entidade, ano)
        cnpj_ente = config.ENTIDADES[entidade].get("cnpj") or "-"
        proprio = conn.execute("SELECT COALESCE(SUM(e.empenhado),0) e, COALESCE(SUM(e.liquidado),0) l, COALESCE(SUM(e.pago),0) p, COUNT(*) n "
                               "FROM empenho e JOIN fornecedor f ON f.entidade=e.entidade AND f.codif=e.codif "
                               "WHERE e.entidade=? AND e.exercicio=? AND f.documento=?", (entidade, ano, cnpj_ente)).fetchone()
        resumo[ano]["proprio_ente"] = dict(proprio)
        forn = conn.execute(
            "SELECT f.nome, f.documento doc, f.tipo_documento tipo, e.codif, e.elemento, SUM(e.empenhado) e, SUM(e.liquidado) l, SUM(e.pago) p, COUNT(*) n "
            "FROM empenho e JOIN fornecedor f ON f.entidade=e.entidade AND f.codif=e.codif "
            "WHERE e.entidade=? AND e.exercicio=? GROUP BY e.codif, f.nome, f.documento, f.tipo_documento, e.elemento", (entidade, ano)).fetchall()
        por_cod = {}
        for r in forn:
            por_cod.setdefault(r["codif"], []).append(r)
        linhas_f, ocultos, pessoas_omitidas = [], [0, 0, 0, 0], set()
        for cod, rs in por_cod.items():
            ocultas = [pf_oculta(r["tipo"], r["elemento"], cod, vereadores_ok) for r in rs]
            if rs[0]["tipo"] == "cpf_mascarado" and any(ocultas):        # pessoa física: sai inteira
                ocultas = [True] * len(rs)
            for r, o in zip(rs, ocultas):
                if o:
                    for i, k in enumerate(("e", "l", "p", "n")):
                        ocultos[i] += r[k]
                    pessoas_omitidas.add(cod)
            vis = [r for r, o in zip(rs, ocultas) if not o]
            if vis:
                linhas_f.append([vis[0]["nome"], vis[0]["doc"], vis[0]["tipo"], sum(r["e"] for r in vis), sum(r["l"] for r in vis),
                                 sum(r["p"] for r in vis), sum(r["n"] for r in vis), 1 if vis[0]["doc"] == cnpj_ente else 0])
        linhas_f.sort(key=lambda l: -l[5])
        if pessoas_omitidas:
            linhas_f.append([f"{ROTULO_PF}: {len(pessoas_omitidas)} pessoas somadas", "", "cpf_mascarado", *ocultos, 0])
        _grava(base / f"fornecedores_{ano}.json", {"campos": ["nome", "doc", "tipo", "e", "l", "p", "n", "proprio"], "linhas": linhas_f,
                                                    "politica_pf": config.PF_POLITICA, "pf_omitidas": len(pessoas_omitidas)})
        emp = conn.execute(
            "SELECT e.numero, e.tipo, e.data, f.nome, f.documento, e.orgao, e.elemento, e.funcao, e.empenhado, e.liquidado, e.pago, "
            "e.historico, e.modalidade_licitacao, f.tipo_documento, e.codif FROM empenho e JOIN fornecedor f ON f.entidade=e.entidade AND f.codif=e.codif "
            "WHERE e.entidade=? AND e.exercicio=? ORDER BY e.data DESC, CAST(e.numero AS INTEGER) DESC", (entidade, ano))
        linhas_e = []
        for r in emp:
            l = list(r)
            if pf_oculta(r["tipo_documento"], r["elemento"], r["codif"], vereadores_ok):
                l[3], l[4], l[11] = ROTULO_PF, "", ""            # nome, documento e histórico (pode citar pacientes, beneficiários…)
            linhas_e.append(l[:13])
        _grava(base / f"empenhos_{ano}.json", {"campos": ["numero", "tipo", "data", "fornecedor", "doc", "orgao", "elemento", "funcao",
                                                           "e", "l", "p", "historico", "modalidade"], "linhas": linhas_e, "politica_pf": config.PF_POLITICA})

    # receita
    receita = {}
    for ano in anos:
        topo_rows = _rows(conn, "SELECT codigo, nome, previsao_atualizada prev, arrecadado a FROM receita WHERE entidade=? AND exercicio=? AND ordem=1 ORDER BY codigo", entidade, ano)
        if not topo_rows:
            continue
        mens = _rows(conn, "SELECT mes, codigo, arrecadado a FROM receita_mensal_topo WHERE entidade=? AND exercicio=? ORDER BY mes, codigo", entidade, ano)
        receita[ano] = {"topo": topo_rows, "mensal": mens, "liquida": sum(r["a"] for r in topo_rows),
                        "previsao_liquida": sum(r["prev"] for r in topo_rows), "coleta": ult_coleta("receita_orcamentaria", ano)}

    # licitações e contratos
    lic = conn.execute("SELECT exercicio, numero, modalidade, objeto, data, situacao, valor, registro_preco FROM licitacao "
                       "WHERE entidade=? AND exercicio>=? ORDER BY data DESC", (entidade, (anos[0] if anos else 2024)))
    contratos = conn.execute("SELECT codigo, fornecedor, documento, objeto, modalidade, valor, data_assinatura, vigencia_inicio, vigencia_atual, "
                             "encerramento, anulacao FROM contrato WHERE entidade=? AND (exercicio>=? OR vigencia_atual>=?) ORDER BY data_assinatura DESC",
                             (entidade, (anos[0] if anos else 2024), date.today().isoformat()))
    _grava(base / "licitacoes.json", {"campos": ["ano", "numero", "modalidade", "objeto", "data", "situacao", "valor", "registro_preco"],
                                       "linhas": [[r[0], r[1], r[2], (r[3] or "")[:260], r[4], r[5], r[6], r[7]] for r in lic], "coleta": ult_coleta("licitacoes")})
    _grava(base / "contratos.json", {"campos": ["codigo", "fornecedor", "doc", "objeto", "modalidade", "valor", "assinatura", "vigencia_inicio", "vigencia_fim", "encerramento", "anulacao"],
                                      "linhas": [[r[0], r[1], r[2], (r[3] or "")[:260], *r[4:]] for r in contratos], "coleta": ult_coleta("contratos")})

    # folha agregada
    ref = conn.execute("SELECT ref_ano, ref_mes FROM servidor_agregado WHERE entidade=? ORDER BY ref_ano DESC, ref_mes DESC LIMIT 1", (entidade,)).fetchone()
    folha = None
    if ref:
        rows = _rows(conn, "SELECT dimensao, chave, qtd, proventos, descontos, liquido FROM servidor_agregado WHERE entidade=? AND ref_ano=? AND ref_mes=? ORDER BY proventos DESC",
                     entidade, ref["ref_ano"], ref["ref_mes"])
        folha = {"ref": f"{ref['ref_mes']:02d}/{ref['ref_ano']}", "coleta": ult_coleta(("servidores", "servidores_mensal")),
                 "k": config.K_ANONIMATO, **{d: [r for r in rows if r["dimensao"] == d] for d in ("total", "cargo", "divisao", "vinculo")}}

    # validação e metodologia
    val = _rows(conn, "SELECT exercicio, checagem, status, esperado, obtido, diferenca, detalhe, em FROM validacao WHERE entidade=? ORDER BY exercicio DESC, checagem", entidade)
    fontes = []
    for f, rot in ROTULOS_FONTE.items():
        r = conn.execute("SELECT fim, registros, url, status FROM execucao_coleta WHERE entidade=? AND fonte=? AND status='ok' ORDER BY id DESC LIMIT 1", ("prefeitura" if f == "ibge_populacao" else entidade, f)).fetchone()
        if r:
            fontes.append({"fonte": f, "rotulo": rot, "coletado_em": r["fim"], "registros": r["registros"], "url": r["url"]})

    _grava(base / "resumo.json", {"anos": resumo, "orgaos": nomes_orgao, "unidades": nomes_unid})
    _grava(base / "mensal.json", mensal)
    _grava(base / "secretarias.json", secretarias)
    _grava(base / "funcoes.json", funcoes)
    _grava(base / "elementos.json", elementos)
    _grava(base / "receita.json", receita)
    _grava(base / "folha.json", folha)
    _grava(base / "validacao.json", val)

    # meta global (mescla com o que já existe para as outras entidades)
    meta_p = saida / "meta.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {"entidades": {}}
    meta["gerado_em"] = db.agora()
    meta["populacao"] = {str(a): {"habitantes": p["habitantes"], "fonte": p["fonte"], "url": p["url"], "coletado_em": p["coletado_em"]} for a, p in pop.items() if a >= 2024}
    meta["entidades"][entidade] = {"nome": config.ENTIDADES[entidade]["nome"], "anos": anos, "portal": LINKS_PORTAL[entidade],
                                   "fontes": fontes, "ultimo_empenho": {str(a): resumo[a]["ultimo"] for a in anos}}
    _grava(meta_p, meta)
    return meta
