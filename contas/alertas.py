"""Alertas de NOVOS registros (empenhos e contratos) acima de limites configuráveis (config/alertas.json).
Informação neutra: um alerta diz que um registro novo apareceu no portal e por qual critério objetivo foi listado; não afirma nada além disso.
- A primeira carga de uma entidade é só a "linha de base" (nada é alertado).
- Só alerta registro cuja data esteja dentro da janela (padrão 45 dias): recargas históricas não geram enxurrada.
- Nome, documento e histórico de pessoas físicas beneficiárias seguem a MESMA política de privacidade das listas publicadas."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from . import config, db
from .parsers import normaliza_nome
from .publicar import ROTULO_PF, pf_oculta

PADRAO = {
    "empenho_valor_minimo": {"prefeitura": 1_000_000, "camara": 100_000},
    "dispensa_valor_minimo": {"prefeitura": 100_000, "camara": 10_000},
    "contrato_valor_minimo": {"prefeitura": 1_000_000, "camara": 100_000},
    "modalidades_destacadas": ["DISPENSA", "INEXIGIBILIDADE"],
    "ignorar_empenhos_em_nome_do_proprio_ente": True,
    "ignorar_anulacoes": True,
    "janela_dias": 45,
    "maximo_no_feed": 300,
}


def carregar_config(caminho: Path = None) -> dict:
    cfg = dict(PADRAO)
    caminho = Path(caminho or config.ARQ_ALERTAS)
    if caminho.exists():
        cfg.update({k: v for k, v in json.loads(caminho.read_text(encoding="utf-8")).items() if not k.startswith("_")})
    return cfg


def _limite(cfg, chave, ent) -> int:
    return int(round(float(cfg[chave].get(ent, 0)) * 100))


def destaque(cfg, modalidade: str):
    """'dispensa' | 'inexigibilidade' | None, conforme as modalidades destacadas (texto da própria fonte)."""
    n = normaliza_nome(modalidade or "")
    for m in cfg["modalidades_destacadas"]:
        if normaliza_nome(m) in n:
            return normaliza_nome(m).lower()
    return None


def motivos_empenho(cfg, ent, r) -> list:
    """r: dict com tipo, empenhado, modalidade_licitacao, documento."""
    if cfg["ignorar_anulacoes"] and r["tipo"] in ("AN", "DA"):
        return []
    if cfg["ignorar_empenhos_em_nome_do_proprio_ente"] and r.get("documento") and r["documento"] == config.ENTIDADES[ent].get("cnpj"):
        return []
    v, m = r["empenhado"], []
    if v >= _limite(cfg, "empenho_valor_minimo", ent) > 0:
        m.append("valor_alto")
    d = destaque(cfg, r.get("modalidade_licitacao"))
    if d and v >= _limite(cfg, "dispensa_valor_minimo", ent) > 0:
        m.append(d)
    return m


def _grava_alerta(conn, ent, tipo, chave, motivos, a):
    conn.execute("INSERT OR IGNORE INTO alerta (criado_em, entidade, tipo, chave, motivos, data_registro, valor, secretaria, fornecedor, documento, elemento, modalidade, descricao) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (db.agora(), ent, tipo, chave, ";".join(motivos), a.get("data"), a["valor"], a.get("secretaria"), a.get("fornecedor"),
                  a.get("documento"), a.get("elemento"), a.get("modalidade"), a.get("descricao")))


def registrar_novos(conn, ent: str, cfg: dict = None, hoje: date = None) -> list:
    """Compara com o que já foi visto; devolve os alertas CRIADOS nesta execução (lista de dicts)."""
    cfg = cfg or carregar_config()
    hoje = hoje or date.today()
    desde = (hoje - timedelta(days=int(cfg["janela_dias"]))).isoformat()
    agora = db.agora()
    criados = []
    vereadores_ok = {r[0] for r in conn.execute("SELECT codif FROM vereador_vinculo WHERE status='confirmado'")}
    orgaos = {r["codigo"]: r["nome"] for r in conn.execute("SELECT codigo, nome FROM orgao WHERE entidade=?", (ent,))}

    # ---- empenhos
    base = conn.execute("SELECT COUNT(*) FROM visto WHERE entidade=? AND tipo='empenho'", (ent,)).fetchone()[0] == 0
    novos = conn.execute(
        "SELECT e.exercicio, e.pkemp, e.numero, e.tipo, e.data, e.orgao, e.elemento, e.modalidade_licitacao, e.historico, e.empenhado, e.codif, "
        "f.nome, f.documento, f.tipo_documento FROM empenho e JOIN fornecedor f ON f.entidade=e.entidade AND f.codif=e.codif "
        "WHERE e.entidade=? AND NOT EXISTS (SELECT 1 FROM visto v WHERE v.entidade=e.entidade AND v.tipo='empenho' AND v.chave = e.exercicio || ':' || e.pkemp)", (ent,)).fetchall()
    for r in novos:
        conn.execute("INSERT OR IGNORE INTO visto VALUES (?,?,?,?)", (ent, "empenho", f"{r['exercicio']}:{r['pkemp']}", agora))
        if base or (r["data"] or "") < desde:
            continue
        m = motivos_empenho(cfg, ent, dict(r, documento=r["documento"]))
        if not m:
            continue
        oculto = pf_oculta(r["tipo_documento"], r["elemento"], r["codif"], vereadores_ok)
        a = {"data": r["data"], "valor": r["empenhado"], "secretaria": orgaos.get(r["orgao"], r["orgao"]),
             "fornecedor": ROTULO_PF if oculto else r["nome"], "documento": "" if oculto else r["documento"], "elemento": r["elemento"],
             "modalidade": r["modalidade_licitacao"], "descricao": "" if oculto else (r["historico"] or "")[:200]}
        _grava_alerta(conn, ent, "empenho", f"{r['exercicio']}:{r['pkemp']}", m, a)
        criados.append({**a, "entidade": ent, "tipo": "empenho", "motivos": m, "numero": r["numero"]})

    # ---- contratos
    base_c = conn.execute("SELECT COUNT(*) FROM visto WHERE entidade=? AND tipo='contrato'", (ent,)).fetchone()[0] == 0
    for r in conn.execute("SELECT codigo, exercicio, fornecedor, documento, objeto, modalidade, valor, data_assinatura FROM contrato WHERE entidade=?", (ent,)).fetchall():
        chave = f"{r['exercicio']}:{r['codigo']}"
        if conn.execute("SELECT 1 FROM visto WHERE entidade=? AND tipo='contrato' AND chave=?", (ent, chave)).fetchone():
            continue
        conn.execute("INSERT OR IGNORE INTO visto VALUES (?,?,?,?)", (ent, "contrato", chave, agora))
        if base_c or (r["data_assinatura"] or "") < desde:
            continue
        m = []
        if r["valor"] >= _limite(cfg, "contrato_valor_minimo", ent) > 0:
            m.append("valor_alto")
        d = destaque(cfg, r["modalidade"])
        if d and r["valor"] >= _limite(cfg, "dispensa_valor_minimo", ent) > 0:
            m.append(d)
        if m:
            a = {"data": r["data_assinatura"], "valor": r["valor"], "fornecedor": r["fornecedor"], "documento": r["documento"],
                 "modalidade": r["modalidade"], "descricao": (r["objeto"] or "")[:200], "secretaria": None, "elemento": None}
            _grava_alerta(conn, ent, "contrato", chave, m, a)
            criados.append({**a, "entidade": ent, "tipo": "contrato", "motivos": m, "numero": r["codigo"]})
    conn.commit()
    return criados


ROT_MOTIVO = {"valor_alto": "valor acima do limite configurado", "dispensa": "contratação por dispensa", "inexigibilidade": "contratação por inexigibilidade"}
NOME_ENT = {"prefeitura": "Prefeitura", "camara": "Câmara"}


def _reais(c) -> str:
    return ("R$ " + f"{c / 100:,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


def _dt(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else "—"


def texto(a: dict) -> str:
    quem = a.get("fornecedor") or "—"
    tipo = "novo contrato" if a["tipo"] == "contrato" else "novo empenho"
    motivos = a["motivos"] if isinstance(a["motivos"], list) else str(a["motivos"]).split(";")
    return (f"{NOME_ENT[a['entidade']]} · {tipo} de {_reais(a['valor'])} · {quem} · registro de {_dt(a.get('data'))} · "
            f"critério: {'; '.join(ROT_MOTIVO.get(m, m) for m in motivos)}. Fonte: portal oficial.")


def itens_publicados(conn, cfg) -> list:
    out = []
    for r in conn.execute("SELECT * FROM alerta ORDER BY id DESC LIMIT ?", (int(cfg["maximo_no_feed"]),)):
        d = dict(r)
        d["motivos"] = d["motivos"].split(";")
        d["texto"] = texto(d)
        out.append(d)
    return out


def feed_atom(itens: list, url_site: str = None, gerado_em: str = None) -> str:
    base = (url_site or "").rstrip("/")
    ent = "".join(
        f"<entry><id>tag:contas-de-primavera,2026:alerta-{i['id']}</id><title>{escape(NOME_ENT[i['entidade']] + ': ' + ('novo contrato' if i['tipo'] == 'contrato' else 'novo empenho') + ' de ' + _reais(i['valor']))}</title>"
        f"<updated>{i['criado_em']}</updated><link href=\"{escape(base)}/#/novidades\"/><summary>{escape(i['texto'])}</summary></entry>" for i in itens)
    return ('<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Contas de Primavera: novos registros</title>'
            f'<id>tag:contas-de-primavera,2026:alertas</id><updated>{gerado_em or db.agora()}</updated><link href="{escape(base)}/"/>{ent}</feed>')


def publicar_alertas(conn, saida: Path = None, cfg: dict = None, url_site: str = None) -> list:
    saida = Path(saida or config.WEB_DATA)
    cfg = cfg or carregar_config()
    itens = itens_publicados(conn, cfg)
    saida.mkdir(parents=True, exist_ok=True)
    criterios = {k: cfg[k] for k in ("empenho_valor_minimo", "dispensa_valor_minimo", "contrato_valor_minimo", "modalidades_destacadas", "janela_dias")}
    (saida / "alertas.json").write_text(json.dumps({"gerado_em": db.agora(), "criterios": criterios, "itens": itens}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (saida / "alertas.xml").write_text(feed_atom(itens, url_site), encoding="utf-8")
    return itens
