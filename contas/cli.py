"""Linha de comando:  python3 -m contas <comando>
  iniciar                          cria o banco
  coletar  [--entidade E] [--anos 2026 2025] [--so fontes...] [--force]
  derivar  [--entidade camara]     vínculos de vereadores + verba indenizatória (sem rede)
  validar  [--entidade E] [--anos ...]
  publicar [--entidade E]          gera web/data/*.json
  alertas                          detecta novos registros acima dos limites e publica alertas.json/alertas.xml
  notificar                        envia os alertas novos ao webhook (se ALERTA_WEBHOOK_URL definido)
  build    [--saida dist]          monta o site pronto para hospedar (metadados, cartão de compartilhamento, status)
  diario   [--entidade E|todas] [--completo]
                                   o que o agendador roda: coleta, valida, alerta, publica (ambas as entidades)
Códigos de saída:  0 ok · 1 falha de coleta em alguma fonte · 2 divergência de validação (não publicar) · 3 = 1+2"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date

from . import alertas as alr, config, db, publicar as pub, publicar_camara as pubc, publicar_receitas as pubr, validar as val
from .coleta import camara as cam, despesas, entradas, ibge, licitacoes, mensal, pessoal, receitas, siconfi, vinculos

FONTES_ANO = {
    "despesas": lambda c, e, a, f: despesas.coletar_empenhos(c, e, a, force=f),
    "totais": lambda c, e, a, f: despesas.coletar_totais_portal(c, e, a),
    "mensal": lambda c, e, a, f: mensal.coletar_mensal(c, e, a),
    "receitas": lambda c, e, a, f: receitas.coletar_receitas(c, e, a),
    "extra": lambda c, e, a, f: entradas.coletar_extra(c, e, a) if e == "prefeitura" else None,
}
FONTES_ENTIDADE = {   # não dependem do ano de referência (portal devolve vários exercícios / mês mais recente)
    "licitacoes": licitacoes.coletar_licitacoes,
    "contratos": licitacoes.coletar_contratos,
}
FONTES_ENTIDADE_PREFEITURA = {                                      # Prefeitura
    "folha": pessoal.coletar_folha,                                 # só o mês mais recente, agregado
    "emendas": entradas.coletar_emendas,
    "siconfi": siconfi.coletar_siconfi,                             # DCA/RREO do Tesouro Nacional (muda pouco: semanal)
}
FONTES_ANO_CAMARA = {                                              # Câmara: folha mês a mês (vereadores nominais), diárias, repasses
    "folha": lambda c, e, a, f: cam.coletar_folha_camara(c, e, a),
    "diarias": lambda c, e, a, f: cam.coletar_diarias(c, e, a),
    "transferencias": lambda c, e, a, f: (cam.coletar_transferencias(c, "prefeitura", a), cam.coletar_transferencias(c, "camara", a)),
}
JANELA_ANOS = 3          # histórico mantido: ano corrente e os dois anteriores


def coletar(conn, entidade, anos, so=None, force=False) -> int:
    erros = 0

    def tenta(nome, fn):
        nonlocal erros
        try:
            fn()
        except Exception as e:  # noqa: BLE001  (a falha fica registrada em execucao_coleta; segue para as próximas fontes)
            erros += 1
            logging.error("falha em %s: %s", nome, e)
    if not so or "ibge" in so:
        tenta("ibge", lambda: ibge.coletar_populacao(conn))
    por_ano = dict(FONTES_ANO)
    por_entidade = dict(FONTES_ENTIDADE)
    if entidade == "camara":
        por_ano.update(FONTES_ANO_CAMARA)
    else:
        por_entidade.update(FONTES_ENTIDADE_PREFEITURA)
    for ano in anos:
        for nome, fn in por_ano.items():
            if not so or nome in so:
                tenta(f"{nome}/{ano}", lambda fn=fn, ano=ano: fn(conn, entidade, ano, force))
    ano_ref = max(anos)
    for nome, fn in por_entidade.items():
        if not so or nome in so:
            tenta(nome, lambda fn=fn: fn(conn, entidade, ano_ref))
    if entidade == "camara":
        derivar(conn, anos)
    return erros


def derivar(conn, anos):
    """Passos locais (sem rede): vínculos nome↔vereador e verba indenizatória derivada do elemento 93."""
    r = vinculos.vincular(conn, "camara")
    logging.info("vínculos de vereadores: %s", r)
    for ano in anos:
        cam.derivar_verba(conn, "camara", ano)


def plano_diario(conn, entidade: str, hoje: date = None, completo: bool = False) -> dict:
    """Decide o que coletar hoje. Ano corrente: sempre, completo. Anos anteriores da janela: toda segunda-feira (ou --completo),
    e imediatamente se não houver dado no banco (ex.: cache perdido). Funciona também num banco vazio (reconstrói tudo)."""
    hoje = hoje or date.today()
    janela = [hoje.year - i for i in range(JANELA_ANOS - 1, 0, -1)]            # anos fechados, do mais antigo ao mais recente
    faltando = [a for a in janela if conn.execute("SELECT COUNT(*) FROM empenho WHERE entidade=? AND exercicio=?", (entidade, a)).fetchone()[0] == 0]
    revisar = janela if (completo or hoje.weekday() == 0) else faltando
    return {"corrente": [hoje.year], "fechados": sorted(set(revisar) | set(faltando)), "faltando": faltando}


def siconfi_devido(conn, hoje: date = None, completo: bool = False) -> bool:
    """SICONFI só muda quando a prefeitura declara (bimestral/anual): coleta às segundas, com --completo ou se ainda não houver dado."""
    hoje = hoje or date.today()
    vazio = conn.execute("SELECT COUNT(*) FROM siconfi_receita").fetchone()[0] == 0
    return completo or vazio or hoje.weekday() == 0


def fontes_fechadas(entidade: str) -> list:      # a receita do portal só existe para o exercício corrente
    return ["despesas", "totais", "mensal"] + (["folha", "diarias", "transferencias"] if entidade == "camara" else [])


TENTATIVAS_CONFERENCIA = 2
ESPERA_ENTRE_TENTATIVAS_S = 60


def _validar_e_imprimir(conn, ent, ano) -> int:
    res = val.validar(conn, ent, ano)
    n, div, avs = val.resumo(res)
    print(f"[validação {ent} {ano}] {n} checagens: {n - div - avs} ok, {avs} avisos, {div} divergências")
    for r in res:
        if r["status"] != "ok":
            print(f"   {r['status'].upper():10s} {r['checagem']}: esperado={r['esperado']} obtido={r['obtido']} dif={r['diferenca']}  {r['detalhe'][:200]}")
    return div


def diario(conn, entidades, completo=False, force=False) -> int:
    rc = 0
    ibge_feito = False
    todas = list(FONTES_ANO) + list(FONTES_ENTIDADE) + list(FONTES_ENTIDADE_PREFEITURA) + list(FONTES_ANO_CAMARA)
    for ent in entidades:
        plano = plano_diario(conn, ent, completo=completo)
        logging.info("plano %s: %s", ent, plano)
        if plano["fechados"]:
            rc |= 1 if coletar(conn, ent, plano["fechados"], so=fontes_fechadas(ent), force=force) else 0
        so = [x for x in todas if not (x == "siconfi" and not siconfi_devido(conn, completo=completo))]
        if ibge_feito:
            so = [x for x in so if x != "ibge"]                               # população do IBGE: uma vez por execução
        else:
            so.append("ibge")
        rc |= 1 if coletar(conn, ent, plano["corrente"], so=so, force=force) else 0
        ibge_feito = True
        for ano in sorted(set(plano["corrente"]) | set(plano["fechados"])):
            div = _validar_e_imprimir(conn, ent, ano)
            tentativas = 0
            while div and ano in plano["corrente"] and tentativas < TENTATIVAS_CONFERENCIA:
                # O portal é um sistema vivo: um lançamento entre o download dos empenhos e a consulta dos totais gera divergência
                # falsa. Antes de bloquear, baixa tudo de novo (sem usar o download do dia) e confere outra vez.
                tentativas += 1
                logging.warning("divergência em %s/%s; nova coleta e conferência (%d/%d)", ent, ano, tentativas, TENTATIVAS_CONFERENCIA)
                time.sleep(ESPERA_ENTRE_TENTATIVAS_S)
                coletar(conn, ent, [ano], so=["despesas", "totais"], force=True)
                div = _validar_e_imprimir(conn, ent, ano)
            rc |= 2 if div else 0
    novos_total = []
    if rc & 2:
        print("DIVERGÊNCIA na validação: nada foi publicado (o site continua com a última versão boa).")
    else:
        for ent in entidades:
            novos = alr.registrar_novos(conn, ent)
            novos_total += novos
            print(f"[alertas {ent}] {len(novos)} novo(s)")
            pub.publicar(conn, ent)
            if ent == "camara":
                print("Câmara:", pubc.publicar_camara(conn))
            if ent == "prefeitura":
                print("Receitas:", pubr.publicar_receitas(conn))
        alr.publicar_alertas(conn, url_site=_site().get("url_site"))
        print(f"JSONs publicados em {config.WEB_DATA}; {len(novos_total)} alerta(s) novo(s) nesta execução")
    (config.RAIZ / "data").mkdir(exist_ok=True)
    (config.RAIZ / "data" / "alertas_novos.json").write_text(
        json.dumps([{**x, "texto": alr.texto(x)} for x in novos_total], ensure_ascii=False, indent=1), encoding="utf-8")
    return rc


def _site() -> dict:
    try:
        return json.loads(config.ARQ_SITE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="contas", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=["iniciar", "coletar", "derivar", "validar", "publicar", "alertas", "notificar", "build", "diario"])
    ap.add_argument("--entidade", default=None, choices=list(config.ENTIDADES) + ["todas"])
    ap.add_argument("--anos", nargs="*", type=int)
    ap.add_argument("--so", nargs="*", choices=sorted(set(FONTES_ANO) | set(FONTES_ENTIDADE) | set(FONTES_ENTIDADE_PREFEITURA) | set(FONTES_ANO_CAMARA) | {"ibge"}))
    ap.add_argument("--force", action="store_true", help="baixa de novo mesmo se já houver download de hoje")
    ap.add_argument("--completo", action="store_true", help="diario: revisa também os anos fechados da janela")
    ap.add_argument("--saida", default=None, help="build: pasta de saída (padrão dist/)")
    ap.add_argument("--db", default=None)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = db.conectar(a.db)
    anos = a.anos or [date.today().year]
    ent_arg = a.entidade or ("todas" if a.comando == "diario" else "prefeitura")
    entidades = list(config.ENTIDADES) if ent_arg == "todas" else [ent_arg]
    if a.comando == "iniciar":
        print("banco pronto em", a.db or config.DB_PADRAO); return 0
    if a.comando == "diario":
        return diario(conn, entidades, completo=a.completo, force=a.force)
    if a.comando == "notificar":
        from . import notificar
        novos = json.loads((config.RAIZ / "data" / "alertas_novos.json").read_text(encoding="utf-8")) if (config.RAIZ / "data" / "alertas_novos.json").exists() else []
        ok = notificar.enviar(novos, url_site=_site().get("url_site") or "")
        print(f"{len(novos)} alerta(s); webhook {'enviado' if ok else 'não enviado (sem alertas ou sem ALERTA_WEBHOOK_URL)'}"); return 0
    if a.comando == "build":
        from . import site
        print(site.montar(conn, a.saida)); return 0
    if a.comando == "alertas":
        novos = []
        for ent in (list(config.ENTIDADES) if a.entidade in (None, "todas") else [a.entidade]):
            novos += alr.registrar_novos(conn, ent)
        alr.publicar_alertas(conn, url_site=_site().get("url_site"))
        (config.RAIZ / "data" / "alertas_novos.json").write_text(json.dumps([{**x, "texto": alr.texto(x)} for x in novos], ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(novos)} alerta(s) novo(s)")
        for n in novos:
            print(" -", alr.texto(n))
        return 0
    rc = 0
    for ent in entidades:
        if a.comando == "coletar":
            rc |= 1 if coletar(conn, ent, anos, a.so, a.force) else 0
        if a.comando == "derivar" and ent == "camara":
            derivar(conn, anos)
        if a.comando == "validar":
            for ano in anos:
                res = val.validar(conn, ent, ano)
                n, div, avs = val.resumo(res)
                print(f"[validação {ent} {ano}] {n} checagens: {n - div - avs} ok, {avs} avisos, {div} divergências")
                for r in res:
                    if r["status"] != "ok":
                        print(f"   {r['status'].upper():10s} {r['checagem']}: esperado={r['esperado']} obtido={r['obtido']} dif={r['diferenca']}  {r['detalhe'][:200]}")
                rc |= 2 if div else 0
        if a.comando == "publicar":
            pub.publicar(conn, ent)
            if ent == "camara":
                print("Câmara:", pubc.publicar_camara(conn))
            if ent == "prefeitura":
                print("Receitas:", pubr.publicar_receitas(conn))
            print("JSONs publicados em", config.WEB_DATA)
    return rc


if __name__ == "__main__":
    sys.exit(main())
