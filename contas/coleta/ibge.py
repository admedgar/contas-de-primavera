"""População estimada (IBGE, tabela 6579, variável 9324) para Primavera do Leste."""
from __future__ import annotations

from .. import config, db, http

URL = ("https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/-6/variaveis/9324"
       "?localidades=N6%5B{mun}%5D")


def extrai_serie(resp) -> dict:
    try:
        serie = resp[0]["resultados"][0]["series"][0]["serie"]
        return {int(a): int(v) for a, v in serie.items() if str(v).isdigit()}
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise RuntimeError(f"resposta do IBGE em formato inesperado: {e}") from e


def coletar_populacao(conn):
    url = URL.format(mun=config.IBGE_MUNICIPIO)
    with db.coleta(conn, "prefeitura", "ibge_populacao") as info:
        serie = extrai_serie(http.get_json_externo(url))
        if not serie:
            raise RuntimeError("IBGE não devolveu população")
        agora = db.agora()
        for ano, hab in serie.items():
            conn.execute("INSERT OR REPLACE INTO populacao VALUES (?,?,?,?,?)",
                         (ano, hab, "IBGE – Estimativas da População (SIDRA, tabela 6579)", url, agora))
        info.update(url=url, registros=len(serie))
