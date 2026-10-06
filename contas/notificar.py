"""Aviso opcional de alertas novos por webhook (Slack, Discord, Telegram via ponte, Zapier, n8n...).
Só envia se ALERTA_WEBHOOK_URL estiver definida (segredo do repositório). O corpo traz `text` (Slack/genérico) e `content` (Discord)."""
from __future__ import annotations

import json
import os
import urllib.request

from . import config

MAX_ITENS = 10


def corpo(alertas: list, url_site: str = "") -> dict:
    linhas = [f"• {a['texto']}" for a in alertas[:MAX_ITENS]]
    if len(alertas) > MAX_ITENS:
        linhas.append(f"… e mais {len(alertas) - MAX_ITENS}.")
    cab = f"Contas de Primavera: {len(alertas)} novo(s) registro(s) acima dos limites configurados."
    rodape = f"\nVeja todos: {url_site.rstrip('/')}/#/novidades" if url_site else ""
    texto = cab + "\n" + "\n".join(linhas) + rodape
    return {"text": texto, "content": texto[:1900]}


def enviar(alertas: list, url: str = None, url_site: str = "") -> bool:
    url = url or os.environ.get("ALERTA_WEBHOOK_URL", "").strip()
    if not url or not alertas:
        return False
    req = urllib.request.Request(url, data=json.dumps(corpo(alertas, url_site), ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": config.USER_AGENT}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return 200 <= r.status < 300
