"""Relatórios mensais (Prefeitura e Câmara): cada relatório cobre do dia 1 ao último dia do mês, com base no que o portal já registrou.

Regra de ouro: TODOS os números são calculados aqui, por código, a partir do banco (o que o portal informou). A IA só escreve o
texto a partir de uma "ficha" já formatada, e o que ela escrever é verificado: qualquer número que não conste da ficha, qualquer
palavra de juízo de valor ou resposta fora do formato faz o texto ser descartado e trocado pelo modelo fixo (sem IA).
Sem ANTHROPIC_API_KEY o relatório sai com o modelo fixo e é rotulado como tal."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import date, timedelta

from . import config, db
from .publicar import ROTULO_PF, pf_oculta
from .publicar_camara import _dias, ehdiaria
from .coleta.camara import eh_vereador

log = logging.getLogger(__name__)

MESES_HISTORICO = 5          # meses anteriores (além do corrente) gerados/mantidos
MODELO_PADRAO = "claude-opus-5-5"
NOMES = {"prefeitura": "Prefeitura", "camara": "Câmara"}
MIN_DIAS_MES = 8              # o mês corrente só é o principal quando já tem este número de dias com registro
JUIZO = ("absurd", "exorbitan", "excessiv", "suspeit", "irregular", "ilegal", "escândalo", "escandalo", "desvio", "superfatur",
         "corrup", "gastança", "gastanca", "abusiv", "vergonh", "preocupante", "alarmante", "culpa", "roubo", "mau uso", "malversa")

# ---------------------------------------------------------------- formatação (única fonte dos textos numéricos)


def brl(c: int) -> str:
    s = f"{abs(c) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if c < 0 else "") + "R$ " + s


def compacto(c: int) -> str:
    v, sinal = abs(c) / 100, ("-" if c < 0 else "")
    if v >= 1e9:
        n = f"{v / 1e9:.2f}".replace(".", ",")
        return f"{sinal}R$ {n} {'bilhão' if v < 2e9 else 'bilhões'}"
    if v >= 1e6:
        n = f"{v / 1e6:.1f}".replace(".", ",")
        return f"{sinal}R$ {n} {'milhão' if v < 2e6 else 'milhões'}"
    if v >= 1e3:
        return f"{sinal}R$ {v / 1e3:.1f} mil".replace(".", ",")
    return brl(c)


def pct(x: float) -> str:
    return f"{x:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def num(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def plural(n: int, um: str, varios: str) -> str:
    return f"{num(n)} {um if n == 1 else varios}"


def dbr(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def dcurto(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

# ---------------------------------------------------------------- períodos


def mes_de(d: date):
    ini = d.replace(day=1)
    prox = (ini + timedelta(days=32)).replace(day=1)
    return f"{d.year}-{d.month:02d}", ini, prox - timedelta(days=1)


def periodos(ref: date):
    """Meses a gerar para a data de referência do portal: o mês dela (dia 1 até hoje) e os anteriores."""
    out, d = [], ref.replace(day=1)
    for _ in range(MESES_HISTORICO + 1):
        ch, a, b = mes_de(d)
        out.append(("mes", ch, a, b))
        d = (a - timedelta(days=1)).replace(day=1)
    return out


def rotulo(tipo: str, ini: date, fim: date, chave: str) -> str:
    return f"{MESES[ini.month - 1].capitalize()} de {ini.year}"


def referencia_portal(conn, entidade: str, hoje: date | None = None):
    """Último dia com empenho registrado no portal (é a data até onde os números valem)."""
    hoje = hoje or date.today()
    r = conn.execute("SELECT MAX(data) d FROM empenho WHERE entidade=? AND data<=?", (entidade, hoje.isoformat())).fetchone()
    return date.fromisoformat(r["d"][:10]) if r and r["d"] else None


# ---------------------------------------------------------------- fatos (números)


def _janela(conn, ent, ini: date, fim: date):
    return conn.execute(
        "SELECT e.tipo, e.data, e.orgao, e.elemento, e.natureza, e.modalidade_licitacao mod, e.empenhado, e.liquidado, e.pago, e.codif, "
        "f.nome fnome, f.documento fdoc, f.tipo_documento ftipo FROM empenho e LEFT JOIN fornecedor f ON f.entidade=e.entidade AND f.codif=e.codif "
        "WHERE e.entidade=? AND e.data BETWEEN ? AND ?", (ent, ini.isoformat(), fim.isoformat())).fetchall()


def _soma_emp(conn, ent, ini: date, fim: date):
    r = conn.execute("SELECT COALESCE(SUM(empenhado),0) e, COALESCE(SUM(CASE WHEN tipo='OR' THEN 1 ELSE 0 END),0) n FROM empenho "
                     "WHERE entidade=? AND data BETWEEN ? AND ?", (ent, ini.isoformat(), fim.isoformat())).fetchone()
    return r["e"], r["n"]


def _anterior(tipo: str, ini: date, ate: date):
    """Mesma janela do mês anterior (dia 1 até o mesmo dia do mês), para comparar parcial com parcial."""
    pf = ini - timedelta(days=1)
    pi = pf.replace(day=1)
    return pi, min(pf, pi + (ate - ini))


def _top(d: dict, n=5):
    return sorted(((k, v) for k, v in d.items() if v > 0), key=lambda kv: -kv[1])[:n]


def _diarias(conn, ent: str, ini: date, ate: date) -> dict:
    """Diárias do período (mesmo critério da aba Câmara: elemento de diária, líquido de anulações, sem passagens).
    Vereadores com vínculo confirmado e com folha no ano aparecem com nome; os demais servidores só entram somados (sem nomes)."""
    rows = [dict(r) for r in conn.execute("SELECT * FROM diaria WHERE entidade=? AND data BETWEEN ? AND ?", (ent, ini.isoformat(), ate.isoformat()))
            if ehdiaria(r["elemento"])]
    anos = {ini.year, ate.year}
    ver = {}
    for r in conn.execute("SELECT DISTINCT vi.codif, v.id vid, v.nome FROM vereador_vinculo vi JOIN vereador v ON v.id=vi.vereador_id "
                          "JOIN vereador_folha f ON f.vereador_id=v.id WHERE vi.status='confirmado' AND f.ano IN (%s)" % ",".join("?" * len(anos)), tuple(anos)):
        ver[r["codif"]] = (r["vid"], r["nome"])
    liq = lambda d: d["valor"] - d["valor_anulado"]
    por_ver, pend, serv = {}, [], []
    for d in rows:
        if d["codif"] in ver:
            vid, nome = ver[d["codif"]]
            a = por_ver.setdefault(vid, {"nome": nome, "qtd": 0, "dias": 0.0, "valor": 0})
            a["qtd"] += 1; a["dias"] += _dias(d["quantidade"]); a["valor"] += liq(d)
        elif eh_vereador(d["cargo"]):
            pend.append(d)
        else:
            serv.append(d)
    lista = sorted(({**a, "dias": round(a["dias"], 2)} for a in por_ver.values()), key=lambda a: (-a["valor"], a["nome"]))
    pessoas = len({d["codif"] for d in serv})
    return {"qtd": len(rows), "valor": sum(liq(d) for d in rows), "vereadores": lista,
            "vereadores_valor": sum(a["valor"] for a in lista), "vereadores_qtd": sum(a["qtd"] for a in lista),
            "pendentes": {"qtd": len(pend), "valor": sum(liq(d) for d in pend)},
            "servidores": {"qtd": len(serv), "valor": sum(liq(d) for d in serv), "pessoas": pessoas if pessoas >= config.K_ANONIMATO else None}}


def fatos(conn, ent: str, tipo: str, chave: str, ini: date, fim: date, ref: date) -> dict | None:
    """Números do período, até a data de referência do portal. None se o portal ainda não tem nada no período."""
    ate = min(fim, ref)
    if ate < ini:
        return None
    rows = _janela(conn, ent, ini, ate)
    if not rows:
        return None
    cnpj_ente = config.ENTIDADES[ent].get("cnpj") or "-"
    nomes_org = {r["codigo"]: r["nome"] for r in conn.execute("SELECT codigo, nome FROM orgao WHERE entidade=?", (ent,))}
    tot = sum(r["empenhado"] for r in rows)
    tot_pos = sum(r["empenhado"] for r in rows if r["empenhado"] > 0)
    f = {"entidade": ent, "nome": NOMES[ent], "tipo": tipo, "chave": chave, "rotulo": rotulo(tipo, ini, fim, chave),
         "inicio": ini.isoformat(), "fim": fim.isoformat(), "ate": ate.isoformat(), "parcial": ate < fim,
         "dias_com_registro": len({r["data"][:10] for r in rows}),
         "emissao": {"qtd": sum(1 for r in rows if r["tipo"] == "OR"), "empenhado": tot,
                     "anulado": sum(r["empenhado"] for r in rows if r["tipo"] == "AN"),
                     "liquidado": sum(r["liquidado"] for r in rows), "pago": sum(r["pago"] for r in rows)}}
    pi, pf = _anterior(tipo, ini, ate)
    e_ant, n_ant = _soma_emp(conn, ent, pi, pf)
    f["comparacao"] = {"inicio": pi.isoformat(), "fim": pf.isoformat(), "empenhado": e_ant, "qtd": n_ant,
                       "variacao_pct": round((tot - e_ant) / e_ant * 100, 1) if e_ant > 0 else None}
    if True:
        def oficial(ano, mes):
            r = conn.execute("SELECT SUM(empenhado) e, SUM(liquidado) l, SUM(pago) p, COUNT(*) n FROM mensal_orgao WHERE entidade=? AND exercicio=? AND mes=?",
                             (ent, ano, mes)).fetchone()
            return {"empenhado": r["e"], "liquidado": r["l"], "pago": r["p"]} if r and r["n"] else None
        pm = (ini - timedelta(days=1))
        f["oficial_mes"] = {"mes": oficial(ini.year, ini.month), "mes_anterior": oficial(pm.year, pm.month) and {**oficial(pm.year, pm.month), "rotulo": f"{MESES[pm.month - 1]} de {pm.year}"},
                            "mesmo_mes_ano_anterior": oficial(ini.year - 1, ini.month) and {**oficial(ini.year - 1, ini.month), "rotulo": f"{MESES[ini.month - 1]} de {ini.year - 1}"}}
    por_dia = {}
    for r in rows:
        por_dia[r["data"][:10]] = por_dia.get(r["data"][:10], 0) + r["empenhado"]
    pico = max(por_dia.items(), key=lambda kv: kv[1])
    f["dia_pico"] = {"data": pico[0], "empenhado": pico[1], "pct": round(pico[1] / tot_pos * 100, 1) if tot_pos and pico[1] > 0 else None}
    por_orgao, por_elem, por_forn, por_mod, nome_forn = {}, {}, {}, {}, {}
    pf_valor, pf_qtd, pf_cod = 0, 0, set()
    for r in rows:
        por_orgao[r["orgao"]] = por_orgao.get(r["orgao"], 0) + r["empenhado"]
        k = (r["elemento"], r["natureza"] or "")
        por_elem[k] = por_elem.get(k, 0) + r["empenhado"]
        if r["tipo"] != "AN":
            m = (r["mod"] or "").strip().lower().capitalize() or "Não informada"
            por_mod[m] = por_mod.get(m, 0) + r["empenhado"]
    # pessoas físicas: nunca nomeadas no relatório (política mais estrita que a das listas do site)
    ocultar = {r["codif"] for r in rows if r["ftipo"] == "cpf_mascarado" or pf_oculta(r["ftipo"], r["elemento"], r["codif"], set())}
    for r in rows:
        if r["codif"] in ocultar:
            pf_valor += r["empenhado"]; pf_qtd += 1 if r["tipo"] == "OR" else 0; pf_cod.add(r["codif"])
        elif r["fdoc"] != cnpj_ente:
            por_forn[r["codif"]] = por_forn.get(r["codif"], 0) + r["empenhado"]
            nome_forn[r["codif"]] = r["fnome"] or r["codif"]
    f["orgaos"] = [{"nome": nomes_org.get(k, k), "empenhado": v, "pct": round(v / tot_pos * 100, 1) if tot_pos else None} for k, v in _top(por_orgao)]
    f["elementos"] = [{"nome": (nat or f"Elemento {el}"), "empenhado": v, "pct": round(v / tot_pos * 100, 1) if tot_pos else None}
                      for (el, nat), v in _top(por_elem)]
    f["fornecedores"] = [{"nome": nome_forn[k], "empenhado": v} for k, v in _top(por_forn)]
    f["pessoas_fisicas"] = {"empenhado": pf_valor, "pessoas": len(pf_cod)} if pf_cod else None
    f["maiores"] = [{"data": r["data"][:10], "fornecedor": ROTULO_PF if r["codif"] in ocultar else (r["fnome"] or r["codif"]),
                     "orgao": nomes_org.get(r["orgao"], r["orgao"]), "elemento": r["natureza"] or r["elemento"],
                     "modalidade": (r["mod"] or "").strip().lower().capitalize() or None, "valor": r["empenhado"]}
                    for r in sorted((r for r in rows if r["tipo"] == "OR" and r["fdoc"] != cnpj_ente), key=lambda r: -r["empenhado"])[:5]]
    tot_mod = sum(v for v in por_mod.values() if v > 0)
    f["modalidades"] = [{"nome": k, "empenhado": v, "pct": round(v / tot_mod * 100, 1) if tot_mod else None} for k, v in _top(por_mod, 4)]
    lic = conn.execute("SELECT modalidade, valor FROM licitacao WHERE entidade=? AND data BETWEEN ? AND ?", (ent, ini.isoformat(), ate.isoformat())).fetchall()
    ctr = conn.execute("SELECT valor FROM contrato WHERE entidade=? AND data_assinatura BETWEEN ? AND ?", (ent, ini.isoformat(), ate.isoformat())).fetchall()
    pm_l = {}
    for r in lic:
        k = (r["modalidade"] or "Não informada").strip().lower().capitalize()
        pm_l[k] = pm_l.get(k, 0) + 1
    f["licitacoes"] = {"qtd": len(lic), "valor": sum(r["valor"] or 0 for r in lic), "por_modalidade": [{"nome": k, "qtd": v} for k, v in sorted(pm_l.items(), key=lambda kv: -kv[1])[:3]]}
    f["contratos"] = {"qtd": len(ctr), "valor": sum(r["valor"] or 0 for r in ctr)}
    if ent == "camara":
        f["camara"] = {"diarias": _diarias(conn, ent, ini, ate), "verba": {}}
        v = conn.execute("SELECT categoria, COUNT(*) n, SUM(empenhado) e, SUM(pago) p FROM verba_indenizatoria WHERE entidade=? AND data_empenho BETWEEN ? AND ? GROUP BY categoria",
                         (ent, ini.isoformat(), ate.isoformat())).fetchall()
        f["camara"]["verba"] = {r["categoria"]: {"qtd": r["n"], "empenhado": r["e"], "pago": r["p"]} for r in v}
    return f


# ---------------------------------------------------------------- ficha (texto numérico pronto) e modelo fixo


def ficha(f: dict) -> dict:
    """Tudo o que a IA pode citar, já formatado. É também a lista de números permitidos na verificação."""
    e, c = f["emissao"], f["comparacao"]
    x = {"instituicao": f["nome"] + " de Primavera do Leste", "periodo": f["rotulo"],
         "situacao": (f"período em andamento: dados do portal até {dbr(f['ate'])}" if f["parcial"] else
                      f"período completo (dados do portal até {dbr(f['ate'])})"),
         "dias_com_registro_no_portal": f["dias_com_registro"],
         "empenhos_emitidos": num(e["qtd"]), "empenhado_liquido_no_periodo": compacto(e["empenhado"]),
         "anulacoes_de_empenho": compacto(e["anulado"]) if e["anulado"] else None,
         "desses_empenhos_ja_liquidado": compacto(e["liquidado"]), "desses_empenhos_ja_pago": compacto(e["pago"])}
    if c["variacao_pct"] is not None:
        x["comparacao"] = (f"mesma janela do período anterior ({dcurto(c['inicio'])} a {dcurto(c['fim'])}): "
                           f"{compacto(c['empenhado'])} em {plural(c['qtd'], 'empenho', 'empenhos')}; variação de {pct(abs(c['variacao_pct']))} "
                           f"{'acima' if c['variacao_pct'] >= 0 else 'abaixo'}")
    p = f["dia_pico"]
    if p["pct"] is not None and f["dias_com_registro"] > 1:
        x["dia_de_maior_empenhado"] = f"{dbr(p['data'])}: {compacto(p['empenhado'])}, {pct(p['pct'])} do total positivo do período"
    if f.get("oficial_mes"):
        o = f["oficial_mes"]
        if o["mes"]:
            x["totais_oficiais_do_mes_no_portal"] = (f"empenhado {compacto(o['mes']['empenhado'])}, liquidado {compacto(o['mes']['liquidado'])}, "
                                                    f"pago {compacto(o['mes']['pago'])}")
        for k in ("mes_anterior", "mesmo_mes_ano_anterior"):
            if o.get(k):
                x[f"totais_oficiais_{k}"] = (f"{o[k]['rotulo']}: empenhado {compacto(o[k]['empenhado'])}, liquidado {compacto(o[k]['liquidado'])}, "
                                             f"pago {compacto(o[k]['pago'])}")
    x["maiores_orgaos_por_empenhado"] = [f"{i['nome']}: {compacto(i['empenhado'])} ({pct(i['pct'])})" for i in f["orgaos"]]
    x["maiores_naturezas_de_despesa"] = [f"{i['nome']}: {compacto(i['empenhado'])} ({pct(i['pct'])})" for i in f["elementos"]]
    x["maiores_fornecedores_pessoa_juridica"] = [f"{i['nome']}: {compacto(i['empenhado'])}" for i in f["fornecedores"]]
    if f["pessoas_fisicas"]:
        x["pagamentos_a_pessoas_fisicas_nomes_omitidos"] = f"{compacto(f['pessoas_fisicas']['empenhado'])} ({f['pessoas_fisicas']['pessoas']} pessoas)"
    x["maiores_empenhos"] = [f"{dcurto(i['data'])} · {i['fornecedor']} · {i['orgao']} · {i['elemento']}" + (f" · {i['modalidade']}" if i["modalidade"] else "")
                             + f" · {compacto(i['valor'])}" for i in f["maiores"]]
    x["empenhado_por_modalidade_de_compra"] = [f"{i['nome']}: {compacto(i['empenhado'])} ({pct(i['pct'])})" for i in f["modalidades"]]
    l, ct = f["licitacoes"], f["contratos"]
    x["licitacoes_do_periodo"] = (f"{plural(l['qtd'], 'processo', 'processos')}, valor {compacto(l['valor'])}" +
                                  ("; " + ", ".join(f"{m['nome']} ({m['qtd']})" for m in l["por_modalidade"]) if l["por_modalidade"] else "")) if l["qtd"] else "nenhum processo registrado no período"
    x["contratos_assinados_no_periodo"] = f"{plural(ct['qtd'], 'contrato', 'contratos')}, valor {compacto(ct['valor'])}" if ct["qtd"] else "nenhum contrato assinado no período"
    if f.get("camara"):
        cm = f["camara"]
        dr = cm["diarias"]
        x["diarias_no_periodo"] = (f"{plural(dr['qtd'], 'registro', 'registros')}, {compacto(dr['valor'])} no total; vereadores: {compacto(dr['vereadores_valor'])} "
                                   f"({plural(dr['vereadores_qtd'], 'registro', 'registros')}); demais servidores: {compacto(dr['servidores']['valor'])} "
                                   f"({plural(dr['servidores']['qtd'], 'registro', 'registros')})" + (f"; aguardando vínculo: {compacto(dr['pendentes']['valor'])}" if dr["pendentes"]["qtd"] else "")
                                   if dr["qtd"] else "nenhuma diária registrada no período")
        if cm["verba"]:
            x["verba_indenizatoria_e_reembolsos_empenhados_no_periodo"] = "; ".join(
                f"{'verba indenizatória' if k == 'verba' else 'reembolsos'}: {compacto(v['empenhado'])} empenhado, {compacto(v['pago'])} pago ({plural(v['qtd'], 'empenho', 'empenhos')})" for k, v in cm["verba"].items())
    return {k: v for k, v in x.items() if v not in (None, [])}


def modelo_fixo(f: dict) -> dict:
    """Texto deterministico (sem IA). Mesma forma do texto da IA."""
    x, e, c = ficha(f), f["emissao"], f["comparacao"]
    base = f"{f['nome']}: {f['rotulo']}"
    situ = f"dados do portal até {dbr(f['ate'])}, período em andamento" if f["parcial"] else f"período completo, dados do portal até {dbr(f['ate'])}"
    resumo = (f"{f['rotulo']} ({situ}): o portal registra {plural(e['qtd'], 'empenho', 'empenhos')} da {f['nome']}, "
              f"somando {compacto(e['empenhado'])} empenhados em {plural(f['dias_com_registro'], 'dia', 'dias')} com registro")
    if c["variacao_pct"] is not None:
        resumo += f", {pct(abs(c['variacao_pct']))} {'acima' if c['variacao_pct'] >= 0 else 'abaixo'} da mesma janela do período anterior"
    resumo += "."
    pontos = []
    if f["orgaos"]:
        o = f["orgaos"][0]
        pontos.append(f"Maior órgão em valor empenhado: {o['nome']}, com {compacto(o['empenhado'])} ({pct(o['pct'])} do total positivo).")
    if f["elementos"]:
        o = f["elementos"][0]
        pontos.append(f"Principal natureza de despesa: {o['nome']}, com {compacto(o['empenhado'])} ({pct(o['pct'])}).")
    if f["maiores"]:
        m = f["maiores"][0]
        pontos.append(f"Maior empenho individual: {compacto(m['valor'])}, em {dcurto(m['data'])}, {m['orgao']}.")
    p = f["dia_pico"]
    if p["pct"] is not None and p["pct"] >= 40 and f["dias_com_registro"] > 1:
        pontos.append(f"Concentração: o dia {dbr(p['data'])} reuniu {compacto(p['empenhado'])}, {pct(p['pct'])} do total positivo do período; por isso, comparações com outros períodos podem oscilar bastante.")
    if f["modalidades"]:
        m = f["modalidades"][0]
        pontos.append(f"Modalidade registrada no portal com maior valor empenhado: \u201c{m['nome']}\u201d, {pct(m['pct'])} do total.")
    if x.get("licitacoes_do_periodo") or x.get("contratos_assinados_no_periodo"):
        pontos.append(f"Licitações: {x['licitacoes_do_periodo']}. Contratos: {x['contratos_assinados_no_periodo']}.")
    if f.get("camara") and x.get("diarias_no_periodo"):
        pontos.append(f"Diárias: {x['diarias_no_periodo']}.")
    obs = ["Empenhado é a reserva de orçamento para a despesa; liquidado indica que o bem ou serviço foi recebido e pago indica o desembolso. "
           "Os valores de liquidado e pago acima são dos empenhos emitidos no período, até a coleta.",
           "Os números vêm do Portal da Transparência e podem receber lançamentos com atraso."]
    return {"titulo": base, "resumo": resumo, "pontos": pontos, "observacoes": obs}


# ---------------------------------------------------------------- IA e verificação

SCHEMA = {"type": "object", "properties": {
    "titulo": {"type": "string"}, "resumo": {"type": "string"},
    "pontos": {"type": "array", "items": {"type": "string"}}, "observacoes": {"type": "array", "items": {"type": "string"}}},
    "required": ["titulo", "resumo", "pontos", "observacoes"], "additionalProperties": False}

SISTEMA = """Você redige resumos curtos, em português do Brasil, sobre gastos públicos do município de Primavera do Leste (MT), para um site de transparência apartidário e independente. Os leitores são cidadãos comuns.

Regras obrigatórias:
1. Use SOMENTE a ficha recebida. Nunca invente, estime nem recalcule valores. Copie valores e percentuais exatamente como estão escritos na ficha (por exemplo "R$ 3,2 milhões" e "12,5%"). Não some nem subtraia números da ficha.
2. Linguagem neutra: descreva o que o portal registra. Proibido: julgar (alto, baixo, excessivo, preocupante), supor causas ou intenções, sugerir irregularidade, opinar sobre pessoas, partidos ou gestores. Comparações só com as palavras "acima" e "abaixo" e o percentual da ficha.
3. Informe sempre o período e até que data o portal tem dados. Se o período estiver em andamento, diga que é parcial.
4. Explique em linguagem simples a diferença entre empenhado (reserva de orçamento), liquidado (bem ou serviço recebido) e pago, sempre que citar mais de um deles.
5. Não cite pessoas físicas. Se a ficha trouxer valores de pessoas físicas com nomes omitidos, apenas diga que os nomes são omitidos.
6. Se a ficha trouxer "dia_de_maior_empenhado" com mais de 40% do período, mencione essa concentração, sobretudo ao citar a comparação com o período anterior.
7. Seja breve: "resumo" com no máximo 3 frases; "pontos" com 3 a 6 itens de uma frase; "observacoes" com 1 a 3 itens sobre limites dos dados.
Responda apenas no formato JSON pedido."""

_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def numeros(texto: str) -> set[str]:
    return set(_NUM.findall(texto))


def verificar(saida: dict, fich: dict) -> list[str]:
    """Problemas encontrados no texto da IA (lista vazia = aprovado)."""
    problemas = []
    if not isinstance(saida, dict) or any(k not in saida for k in ("titulo", "resumo", "pontos", "observacoes")):
        return ["formato fora do esperado"]
    txt = " ".join([saida["titulo"], saida["resumo"], *saida["pontos"], *saida["observacoes"]])
    permitidos = numeros(json.dumps(fich, ensure_ascii=False))
    for n in sorted(numeros(txt) - permitidos):
        if not (n.isdigit() and int(n) <= 10):
            problemas.append(f"número que não está na ficha: {n}")
    low = txt.lower()
    for p in JUIZO:
        if p in low:
            problemas.append(f"palavra de juízo de valor: {p}")
    if not 1 <= len(saida["pontos"]) <= 8 or not saida["resumo"].strip():
        problemas.append("quantidade de pontos ou resumo vazio")
    return problemas


def _cliente():
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("pacote 'anthropic' não instalado: relatório sai com o modelo fixo")
        return None
    return anthropic.Anthropic(timeout=180.0)


def texto_ia(fich: dict, cliente=None, modelo: str | None = None) -> tuple[dict | None, str | None]:
    """Chama a IA e verifica. Devolve (texto, modelo) ou (None, None) se não houver chave, falhar ou for reprovado duas vezes."""
    cliente = cliente or _cliente()
    if cliente is None:
        return None, None
    modelo = modelo or os.environ.get("RELATORIO_MODELO") or MODELO_PADRAO
    msgs = [{"role": "user", "content": "Ficha do período (única fonte permitida):\n" + json.dumps(fich, ensure_ascii=False, indent=1)}]
    for tentativa in (1, 2):
        try:
            r = cliente.messages.create(
                model=modelo, max_tokens=4000, system=SISTEMA, messages=msgs,
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}})
        except Exception as e:                                      # falha de rede, cota, chave inválida…: sem IA, nunca bloqueia o site
            log.warning("IA indisponível (%s: %s): usando o modelo fixo", type(e).__name__, str(e)[:300])
            return None, None
        if getattr(r, "stop_reason", None) == "refusal":
            log.warning("IA recusou o pedido: usando o modelo fixo")
            return None, None
        bruto = next((b.text for b in r.content if b.type == "text"), "")
        try:
            saida = json.loads(bruto)
        except ValueError:
            saida = None
        problemas = verificar(saida, fich)
        if not problemas:
            return saida, modelo
        log.warning("texto da IA reprovado (tentativa %d): %s", tentativa, "; ".join(problemas[:4]))
        msgs += [{"role": "assistant", "content": bruto or "{}"},
                 {"role": "user", "content": "Reprovado na verificação: " + "; ".join(problemas[:6]) +
                  ". Reescreva usando apenas números e palavras da ficha, sem juízo de valor."}]
    return None, None


# ---------------------------------------------------------------- orquestração


def _hash(f: dict) -> str:
    return hashlib.sha256(json.dumps(f, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def gerar(conn, entidades=None, hoje: date | None = None, cliente=None, usar_ia: bool = True) -> dict:
    """Gera/atualiza os relatórios no banco. Só chama a IA quando os números mudaram (ou quando o texto atual é do modelo fixo e há IA)."""
    ia_disponivel = usar_ia and (cliente is not None or _cliente() is not None)
    cli = cliente or (_cliente() if usar_ia else None)
    cont = {"gerados": 0, "ia": 0, "modelo_fixo": 0, "mantidos": 0}
    conn.execute("DELETE FROM relatorio WHERE tipo<>'mes'")      # relatórios semanais de versões anteriores deixaram de existir
    conn.commit()
    for ent in (entidades or config.ENTIDADES):
        ref = referencia_portal(conn, ent, hoje)
        if not ref:
            continue
        for tipo, chave, ini, fim in periodos(ref):
            f = fatos(conn, ent, tipo, chave, ini, fim, ref)
            if not f:
                continue
            h = _hash(f)
            atual = conn.execute("SELECT hash, origem FROM relatorio WHERE entidade=? AND tipo=? AND chave=?", (ent, tipo, chave)).fetchone()
            if atual and atual["hash"] == h and atual["origem"] == "ia":
                cont["mantidos"] += 1                      # texto da IA já gerado para estes mesmos números: não paga de novo
                continue
            texto, modelo = texto_ia(ficha(f), cli) if usar_ia and cli else (None, None)
            if texto is None:
                texto, origem = modelo_fixo(f), "modelo"
            else:
                origem = "ia"
            conn.execute("INSERT OR REPLACE INTO relatorio (entidade, tipo, chave, fatos, texto, origem, modelo, hash, gerado_em) VALUES (?,?,?,?,?,?,?,?,?)",
                         (ent, tipo, chave, json.dumps(f, ensure_ascii=False), json.dumps(texto, ensure_ascii=False), origem, modelo, h, db.agora()))
            conn.commit()
            cont["gerados"] += 1
            cont["ia" if origem == "ia" else "modelo_fixo"] += 1
    return cont
