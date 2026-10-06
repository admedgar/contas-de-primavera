"""Monta a pasta pronta para hospedar (dist/): copia web/, injeta metadados de compartilhamento, gera og.png e status.json."""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

from . import cartao, config, db
from .alertas import carregar_config  # noqa: F401  (valida o arquivo de alertas no build)


def _meta_tags(site: dict, titulo: str, descricao: str) -> str:
    url = (site.get("url_site") or "").rstrip("/")
    t = [f'<meta property="og:type" content="website">', f'<meta property="og:locale" content="pt_BR">',
         f'<meta property="og:title" content="{titulo}">', f'<meta property="og:description" content="{descricao}">',
         '<meta name="twitter:card" content="summary_large_image">',
         '<link rel="alternate" type="application/atom+xml" title="Novos registros" href="data/alertas.xml">']
    if url:
        t += [f'<link rel="canonical" href="{url}/">', f'<meta property="og:url" content="{url}/">',
              f'<meta property="og:image" content="{url}/og.png">', f'<meta name="twitter:image" content="{url}/og.png">']
    return "\n".join(t)


def status(conn) -> dict:
    out = {"gerado_em": db.agora(), "entidades": {}}
    for ent in config.ENTIDADES:
        fontes = []
        for r in conn.execute("SELECT fonte, MAX(id) mid FROM execucao_coleta WHERE entidade=? GROUP BY fonte", (ent,)):
            ult = conn.execute("SELECT * FROM execucao_coleta WHERE id=?", (r["mid"],)).fetchone()
            ok = conn.execute("SELECT fim FROM execucao_coleta WHERE entidade=? AND fonte=? AND status='ok' ORDER BY id DESC LIMIT 1", (ent, r["fonte"])).fetchone()
            fontes.append({"fonte": r["fonte"], "ultimo_ok": ok["fim"] if ok else None, "ultima_tentativa": ult["fim"] or ult["inicio"],
                           "status": ult["status"], "erro": (ult["mensagem"] or "").splitlines()[0][:200] if ult["status"] == "erro" else None})
        out["entidades"][ent] = {"fontes": sorted(fontes, key=lambda f: f["fonte"])}
    return out


def montar(conn, saida=None) -> str:
    dist = Path(saida or config.DIST)
    if dist.exists():
        shutil.rmtree(dist)
    shutil.copytree(config.RAIZ / "web", dist)
    try:
        site = json.loads(config.ARQ_SITE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        site = {}
    (dist / ".nojekyll").write_text("")
    # valores reais para a imagem de prévia
    res = json.loads((dist / "data" / "prefeitura" / "resumo.json").read_text(encoding="utf-8"))
    ano = str(max(int(a) for a in res["anos"]))
    r = res["anos"][ano]
    pago = r["pago"]
    coleta = (r.get("coleta_empenhos") or "")[:10]
    data_br = f"{coleta[8:10]}/{coleta[5:7]}/{coleta[:4]}" if coleta else "—"
    titulo = f"Gasto da Prefeitura em {ano}"
    desc = f"Quanto a Prefeitura e a Câmara de Primavera do Leste gastaram em {ano}, com dados do Portal da Transparência oficial. Projeto independente."
    og = cartao.gerar(dist / "og.png", titulo, pago, "Pago", data_br, round(pago / r["habitantes"]) if r.get("habitantes") else None)
    html = (dist / "index.html").read_text(encoding="utf-8")
    html = html.replace("</head>", _meta_tags(site, "Contas de Primavera", desc) + "\n</head>", 1)
    (dist / "index.html").write_text(html, encoding="utf-8")
    (dist / "data" / "status.json").write_text(json.dumps(status(conn), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (dist / "data" / "site.json").write_text(json.dumps({k: v for k, v in site.items() if not k.startswith("_")}, ensure_ascii=False), encoding="utf-8")
    url = (site.get("url_site") or "").rstrip("/")
    (dist / "robots.txt").write_text("User-agent: *\nAllow: /\n" + (f"Sitemap: {url}/sitemap.xml\n" if url else ""))
    if url:
        (dist / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{url}/</loc><lastmod>{date.today().isoformat()}</lastmod></url></urlset>')
    tam = sum(p.stat().st_size for p in dist.rglob("*") if p.is_file())
    return f"site montado em {dist} ({tam / 1e6:.1f} MB; og.png {'gerado' if og else 'NÃO gerado (Pillow ausente)'}; url_site {'definida' if url else 'não definida'})"
