"""Conversões puras (sem rede, sem banco): números, datas, nomes e documentos."""
from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Optional

_MILHAR = re.compile(r"^-?\d{1,3}(\.\d{3})+$")


def centavos(valor) -> int:
    """'31729665,47' -> 3172966547. Vazio/None -> 0. Arredonda para centavos (a API às vezes traz '8690576,35999999')."""
    if valor is None:
        return 0
    s = str(valor).strip()
    if s in ("", "-"):
        return 0
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif _MILHAR.match(s):
        s = s.replace(".", "")
    try:
        return int((Decimal(s) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except InvalidOperation as e:
        raise ValueError(f"valor monetário inválido: {valor!r}") from e


def data_iso(valor) -> Optional[str]:
    """'05/01/2026 00:00:00' ou '05/01/2026' -> '2026-01-05'. Vazio -> None."""
    if not valor:
        return None
    m = re.match(r"^\s*(\d{2})/(\d{2})/(\d{4})", str(valor))
    if not m:
        raise ValueError(f"data inválida: {valor!r}")
    d, mth, a = m.groups()
    return f"{a}-{mth}-{d}"


def ano_2dig(valor) -> int:
    """'26' -> 2026; '2026' -> 2026. Licitações usam ano de 2 dígitos."""
    a = int(str(valor).strip())
    return a + 2000 if a < 100 else a


def normaliza_nome(s: str) -> str:
    """Maiúsculas, sem acentos, espaços colapsados. Usado só para PISTA de vínculo, nunca como prova."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().upper()


def tipo_documento(doc: str) -> str:
    """'cnpj' | 'cpf_mascarado' | 'outro'. O CPF nunca é desmascarado."""
    d = (doc or "").strip()
    if re.match(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$", d):
        return "cnpj"
    if "X" in d.upper():
        return "cpf_mascarado"
    return "outro"


def limpa(s, limite: Optional[int] = None) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s[:limite] if limite else s
