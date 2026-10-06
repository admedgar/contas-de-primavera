"""Cliente HTTP educado: User-Agent identificado, pausa entre chamadas, retry com espera, download em streaming."""
from __future__ import annotations

import gzip
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from . import config

log = logging.getLogger("contas.http")
_ultima = 0.0


class FonteIndisponivel(RuntimeError):
    """O portal respondeu erro, HTML ou JSON inválido."""


def url_consulta(entidade: str, rota: str, params: dict) -> str:
    portal = config.ENTIDADES[entidade]["portal"]
    qs = urllib.parse.urlencode(params, safe="/,")
    return f"{config.BASE_URL}/{portal}/VersaoJson/{rota}/?{qs}"


def _pausa():
    global _ultima
    falta = config.PAUSA_ENTRE_REQUISICOES_S - (time.time() - _ultima)
    if falta > 0:
        time.sleep(falta)
    _ultima = time.time()


def _abrir(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": config.USER_AGENT, "Accept": "application/json", "Accept-Encoding": "gzip"})
    return urllib.request.urlopen(req, timeout=config.TIMEOUT_S)


def _com_retry(fn, url: str):
    ultimo: Optional[Exception] = None
    for i in range(config.TENTATIVAS):
        _pausa()
        try:
            return fn()
        except urllib.error.HTTPError as e:
            ultimo = e
            if e.code < 500 and e.code != 429:
                raise FonteIndisponivel(f"HTTP {e.code} em {url}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            ultimo = e
        espera = config.ESPERA_RETRY_S[min(i, len(config.ESPERA_RETRY_S) - 1)]
        log.warning("falha (%s); nova tentativa em %ss: %s", ultimo, espera, url)
        time.sleep(espera)
    raise FonteIndisponivel(f"falhou após {config.TENTATIVAS} tentativas: {url} ({ultimo})")


def _decodifica(corpo: bytes, url: str):
    try:
        return json.loads(corpo.decode("utf-8-sig"))
    except ValueError as e:
        raise FonteIndisponivel(f"resposta não é JSON ({corpo[:120]!r}) em {url}") from e


def get_json(entidade: str, rota: str, params: dict):
    """GET pequeno, em memória. Devolve (dados, url, bytes)."""
    url = url_consulta(entidade, rota, params)

    def chamada():
        with _abrir(url) as r:
            corpo = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                corpo = gzip.decompress(corpo)
            return corpo

    corpo = _com_retry(chamada, url)
    return _decodifica(corpo, url), url, len(corpo)


def baixar(entidade: str, rota: str, params: dict, destino: Path):
    """GET grande: grava em disco em blocos (sem manter 40 MB na rede), depois lê o JSON. Devolve (dados, url, bytes)."""
    url = url_consulta(entidade, rota, params)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".part")

    def chamada():
        with _abrir(url) as r, open(tmp, "wb") as f:
            src = gzip.GzipFile(fileobj=r) if r.headers.get("Content-Encoding") == "gzip" else r
            while True:
                bloco = src.read(1 << 20)
                if not bloco:
                    break
                f.write(bloco)

    _com_retry(chamada, url)
    tmp.replace(destino)
    corpo = destino.read_bytes()
    return _decodifica(corpo, url), url, len(corpo)


def get_json_externo(url: str):
    """APIs de terceiros (IBGE)."""
    def chamada():
        with _abrir(url) as r:
            corpo = r.read()
            return gzip.decompress(corpo) if r.headers.get("Content-Encoding") == "gzip" else corpo
    return _decodifica(_com_retry(chamada, url), url)
