import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from unittest import mock

from contas import alertas as alr, cli, config, db, notificar, site, validar

CFG = dict(alr.PADRAO, janela_dias=45)
HOJE = date(2026, 10, 6)             # terça-feira


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.conn = db.conectar(Path(self.tmp.name) / "t.sqlite"); self.addCleanup(self.conn.close)
        self.conn.execute("INSERT INTO orgao VALUES ('prefeitura','0206','SECRETARIA DE EDUCAÇÃO')")
        for cod, nome, doc, tp in (("1", "EMPRESA GRANDE LTDA", "11.111.111/0001-11", "cnpj"), ("2", "FULANA BENEFICIARIA", "222.XXX.XXX-22", "cpf_mascarado"),
                                   ("3", "PREFEITURA MUNICIPAL DE PRIMAVERA DO LE", "01.974.088/0001-05", "cnpj")):
            self.conn.execute("INSERT INTO fornecedor VALUES ('prefeitura',?,?,?,?)", (cod, nome, doc, tp))
        self.n = 0

    def emp(self, valor_reais, codif="1", tipo="OR", modalidade="", elemento="39", data="2026-10-05", ano=2026, historico="OBJETO"):
        self.n += 1
        self.conn.execute("INSERT INTO empenho VALUES ('prefeitura',?,?,?,?,NULL,?,?, '0206','020601','Educação','','','',?,'x','',?,?,?,?,?)",
                          (ano, f"p{self.n}", str(self.n), tipo, codif, data, elemento, modalidade, historico, round(valor_reais * 100), 0, 0))
        self.conn.commit()


class Plano(Base):
    def test_banco_vazio_reconstroi_anos_anteriores(self):
        p = cli.plano_diario(self.conn, "prefeitura", HOJE)
        self.assertEqual(p, {"corrente": [2026], "fechados": [2024, 2025], "faltando": [2024, 2025]})

    def test_terca_nao_revisa_anos_com_dados(self):
        self.emp(1, ano=2024); self.emp(1, ano=2025)
        self.assertEqual(cli.plano_diario(self.conn, "prefeitura", HOJE)["fechados"], [])

    def test_segunda_e_completo_revisam(self):
        self.emp(1, ano=2024); self.emp(1, ano=2025)
        self.assertEqual(cli.plano_diario(self.conn, "prefeitura", date(2026, 10, 5))["fechados"], [2024, 2025])
        self.assertEqual(cli.plano_diario(self.conn, "prefeitura", HOJE, completo=True)["fechados"], [2024, 2025])

    def test_so_o_ano_que_falta(self):
        self.emp(1, ano=2025)
        self.assertEqual(cli.plano_diario(self.conn, "prefeitura", HOJE)["fechados"], [2024])


class Alertas(Base):
    def roda(self, **kw):
        return alr.registrar_novos(self.conn, "prefeitura", CFG, HOJE, **kw) if False else alr.registrar_novos(self.conn, "prefeitura", CFG, HOJE)

    def test_primeira_carga_e_so_linha_de_base(self):
        self.emp(5_000_000)
        self.assertEqual(self.roda(), [])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM visto").fetchone()[0], 1)

    def test_novo_acima_do_limite_alerta_uma_unica_vez(self):
        self.emp(10); self.roda()
        self.emp(1_500_000)
        a = self.roda()
        self.assertEqual([x["motivos"] for x in a], [["valor_alto"]]); self.assertEqual(a[0]["secretaria"], "SECRETARIA DE EDUCAÇÃO")
        self.assertEqual(self.roda(), [])                                    # reexecutar não duplica
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM alerta").fetchone()[0], 1)

    def test_abaixo_do_limite_nao_alerta_e_dispensa_tem_limite_proprio(self):
        self.emp(10); self.roda()
        self.emp(900_000)                                                     # < 1 mi e sem dispensa
        self.emp(150_000, modalidade="DISPENSA")                              # ≥ 100 mil em dispensa
        self.emp(50_000, modalidade="DISPENSA")                               # < 100 mil
        self.emp(200_000, modalidade="INEXIGIBILIDADE")
        m = [x["motivos"] for x in self.roda()]
        self.assertEqual(m, [["dispensa"], ["inexigibilidade"]])

    def test_ignora_anulacao_folha_e_registros_antigos(self):
        self.emp(10); self.roda()
        self.emp(2_000_000, tipo="AN"); self.emp(2_000_000, codif="3"); self.emp(2_000_000, data="2025-01-10")
        self.assertEqual(self.roda(), [])

    def test_pessoa_fisica_beneficiaria_sai_mascarada_no_alerta(self):
        self.emp(10); self.roda()
        self.emp(1_200_000, codif="2", elemento="48", historico="AUXILIO PARA FULANO DOENTE")
        a = self.roda()[0]
        self.assertEqual((a["fornecedor"], a["documento"], a["descricao"]), ("Pessoa física (nome omitido)", "", ""))
        self.assertNotIn("DOENTE", alr.texto(a)); self.assertNotIn("FULANA", alr.texto(a))

    def test_contratos_novos(self):
        self.conn.execute("INSERT INTO contrato (entidade, codigo, exercicio, fornecedor, documento, objeto, modalidade, valor, aditado, empenhado, liquidado, data_assinatura) "
                          "VALUES ('prefeitura','0001/26',2026,'ACME','1','x','PREGÃO ELETRÔNICO',100,0,0,0,'2026-01-01')"); self.conn.commit()
        self.roda()
        self.conn.execute("INSERT INTO contrato (entidade, codigo, exercicio, fornecedor, documento, objeto, modalidade, valor, aditado, empenhado, liquidado, data_assinatura) "
                          "VALUES ('prefeitura','0002/26',2026,'ACME','1','obra','DISPENSA',200000000,0,0,0,'2026-10-02')"); self.conn.commit()
        a = self.roda()
        self.assertEqual((a[0]["tipo"], a[0]["motivos"]), ("contrato", ["valor_alto", "dispensa"]))

    def test_texto_neutro_e_feed_valido(self):
        self.emp(10); self.roda(); self.emp(1_500_000); self.roda()
        itens = alr.itens_publicados(self.conn, CFG)
        t = itens[0]["texto"]
        self.assertIn("R$ 1.500.000,00", t); self.assertIn("Fonte: portal oficial", t)
        self.assertIn("registro de 05/10/2026", t)                 # a data vem do banco no campo data_registro
        raiz = ET.fromstring(alr.feed_atom(itens, "https://exemplo.org"))
        self.assertEqual(len(raiz.findall("{http://www.w3.org/2005/Atom}entry")), 1)

    def test_configuracao_do_repositorio_e_valida(self):
        cfg = alr.carregar_config()
        for k in ("empenho_valor_minimo", "dispensa_valor_minimo", "contrato_valor_minimo"):
            self.assertEqual(set(cfg[k]), {"prefeitura", "camara"})


class Conhecidas(unittest.TestCase):
    def _r(self, dif):
        return [{"checagem": "liquidado_vs_portal_por_fornecedor", "status": "divergente", "esperado": 1, "obtido": 1 + dif, "diferenca": dif, "detalhe": "x"}]

    LISTA = [{"entidade": "prefeitura", "exercicio": 2024, "checagem": "liquidado_vs_portal_por_fornecedor", "diferenca": -100, "nota": "da fonte"}]

    def test_so_vale_com_a_diferenca_exata(self):
        r = self._r(-100); validar.aplica_conhecidas("prefeitura", 2024, r, self.LISTA)
        self.assertEqual(r[0]["status"], "aviso"); self.assertIn("CONHECIDA", r[0]["detalhe"])
        r = self._r(-101); validar.aplica_conhecidas("prefeitura", 2024, r, self.LISTA)
        self.assertEqual(r[0]["status"], "divergente")
        r = self._r(-100); validar.aplica_conhecidas("prefeitura", 2025, r, self.LISTA)
        self.assertEqual(r[0]["status"], "divergente")


class Webhook(unittest.TestCase):
    def test_corpo_limita_itens(self):
        a = [{"texto": f"t{i}"} for i in range(25)]
        c = notificar.corpo(a, "https://x.org/")
        self.assertIn("25 novo(s)", c["text"]); self.assertIn("e mais 15", c["text"]); self.assertIn("https://x.org/#/novidades", c["text"])
        self.assertLessEqual(len(c["content"]), 1900)

    def test_sem_url_ou_sem_alertas_nao_envia(self):
        with mock.patch.dict("os.environ", {"ALERTA_WEBHOOK_URL": ""}):
            self.assertFalse(notificar.enviar([{"texto": "x"}]))
        self.assertFalse(notificar.enviar([], url="http://invalido.invalid"))


class Build(unittest.TestCase):
    def test_monta_site_com_metadados_e_status(self):
        with tempfile.TemporaryDirectory() as t:
            raiz = Path(t) / "r"; (raiz / "web" / "data" / "prefeitura").mkdir(parents=True); (raiz / "config").mkdir()
            (raiz / "web" / "index.html").write_text("<html><head><title>x</title></head><body></body></html>")
            (raiz / "web" / "data" / "prefeitura" / "resumo.json").write_text(json.dumps({"anos": {"2026": {"pago": 50350406960, "habitantes": 99053, "coleta_empenhos": "2026-10-06T15:49:21Z"}}}))
            (raiz / "config" / "site.json").write_text(json.dumps({"url_site": "https://exemplo.org/", "contato": "a@b.c"}))
            conn = db.conectar(Path(t) / "x.sqlite")
            with mock.patch.object(config, "RAIZ", raiz), mock.patch.object(config, "ARQ_SITE", raiz / "config" / "site.json"):
                msg = site.montar(conn, Path(t) / "dist")
            dist = Path(t) / "dist"
            html = (dist / "index.html").read_text()
            self.assertIn('og:image" content="https://exemplo.org/og.png"', html); self.assertIn("alertas.xml", html)
            self.assertTrue((dist / "data" / "status.json").exists()); self.assertTrue((dist / ".nojekyll").exists())
            self.assertEqual(json.loads((dist / "data" / "site.json").read_text())["contato"], "a@b.c")
            self.assertIn("sitemap", (dist / "robots.txt").read_text().lower())
            conn.close()


class Workflow(unittest.TestCase):
    def test_agendamento_e_portao_de_publicacao(self):
        y = (config.RAIZ / ".github" / "workflows" / "diario.yml").read_text(encoding="utf-8")
        self.assertIn("cron:", y); self.assertIn("python -m contas diario", y); self.assertIn("deploy-pages", y)
        self.assertIn("rc == '0' || steps.diario.outputs.rc == '1'", y)      # divergência (2/3) nunca publica
        self.assertNotIn("hotmail", y.lower())

    def test_deploy_vercel_e_opcional_e_so_com_dados_conferidos(self):
        y = (config.RAIZ / ".github" / "workflows" / "diario.yml").read_text(encoding="utf-8")
        i = y.index("Publicar na Vercel")
        passo = y[i:i + 400]
        self.assertIn("env.VERCEL_TOKEN != ''", passo); self.assertIn("rc == '0'", passo)    # sem token ou com divergência, não publica
        self.assertIn("secrets.VERCEL_TOKEN", y)                                            # token só como segredo
        v = json.loads((config.RAIZ / "web" / "vercel.json").read_text(encoding="utf-8"))
        self.assertTrue(any("/data/" in h["source"] for h in v["headers"]))

    def test_nenhum_email_pessoal_no_codigo(self):
        for p in list((config.RAIZ / "contas").rglob("*.py")) + list((config.RAIZ / "web").glob("*.js")) + list((config.RAIZ / "config").glob("*.json")):
            self.assertNotIn("hotmail", p.read_text(encoding="utf-8").lower(), p)


if __name__ == "__main__":
    unittest.main()


class Retentativa(Base):
    """diario: divergência no ano corrente => baixa de novo (force=True) e confere outra vez; só então bloqueia."""
    def _roda(self, resultados):
        chamadas = []
        div_iter = iter(resultados)
        with mock.patch.object(cli, "coletar", side_effect=lambda conn, ent, anos, so=None, force=False: chamadas.append((tuple(anos), tuple(so or ()), force)) or 0), \
             mock.patch.object(cli, "_validar_e_imprimir", side_effect=lambda *a: next(div_iter)), \
             mock.patch.object(cli.time, "sleep"), mock.patch.object(cli.alr, "registrar_novos", return_value=[]), \
             mock.patch.object(cli.pub, "publicar"), mock.patch.object(cli.alr, "publicar_alertas"), \
             mock.patch.object(cli, "plano_diario", return_value={"corrente": [2026], "fechados": [], "faltando": []}), \
             mock.patch.object(config, "RAIZ", Path(self.tmp.name)):
            rc = cli.diario(self.conn, ["prefeitura"])
        return rc, chamadas

    def test_divergencia_passageira_e_resolvida_na_segunda_coleta(self):
        rc, ch = self._roda([3, 0])
        self.assertEqual(rc, 0)
        self.assertTrue(any(f for (_, _, f) in ch))                       # houve recoleta forçada
        self.assertEqual(ch[-1][1], ("despesas", "totais"))

    def test_divergencia_persistente_bloqueia_a_publicacao(self):
        rc, ch = self._roda([3, 3, 3])
        self.assertEqual(rc, 2)
        self.assertEqual(sum(1 for (_, _, f) in ch if f), 2)               # duas recoletas e então desiste
        self.assertEqual((Path(self.tmp.name) / "data" / "alertas_novos.json").read_text(), "[]")


class Defasagem(Base):
    """O detalhe de empenhos pode ficar atrás dos totais do portal; só vira 'aviso' se fechar ao centavo até a última data."""
    def _res(self, dif, esperado=1_000_000):
        return [{"checagem": "empenhado_vs_portal_por_orgao", "status": "divergente", "esperado": esperado, "obtido": esperado + dif, "diferenca": dif, "detalhe": "x"},
                {"checagem": "por_orgao_confere", "status": "divergente", "esperado": 0, "obtido": 1, "diferenca": 1, "detalhe": "y"}]

    def test_detalhe_fecha_ate_a_data_e_diferenca_pequena_vira_aviso(self):
        self.emp(100, data="2026-10-06"); self.emp(50, data="2026-10-05")
        r = self._res(2000)
        validar.explica_defasagem(self.conn, "prefeitura", 2026, r, lambda *a: {"0206": 15_000})      # totais do portal até 06/10 = soma da lista
        self.assertEqual([x["status"] for x in r], ["aviso", "aviso"]); self.assertIn("DEFASAGEM", r[0]["detalhe"])

    def test_se_o_detalhe_nao_fecha_ate_a_data_continua_divergente(self):
        self.emp(100, data="2026-10-06")
        r = self._res(2000)
        validar.explica_defasagem(self.conn, "prefeitura", 2026, r, lambda *a: {"0206": 9_999})        # faltam R$ 0,01 já no passado
        self.assertEqual([x["status"] for x in r], ["divergente", "divergente"])

    def test_diferenca_grande_nao_e_explicada(self):
        self.emp(100, data="2026-10-06")
        r = self._res(50_000)                                                                          # 5% do total
        validar.explica_defasagem(self.conn, "prefeitura", 2026, r, lambda *a: {"0206": 10_000})
        self.assertEqual(r[0]["status"], "divergente")


class Preflight(Base):
    def test_portal_fora_do_ar_pula_a_coleta_e_registra(self):
        with mock.patch.object(cli.http, "sonda", return_value=(False, "HTTP 530")), mock.patch.object(cli.time, "sleep"), \
             mock.patch.object(cli, "coletar", side_effect=AssertionError("não deveria coletar")), mock.patch.object(config, "RAIZ", Path(self.tmp.name)), \
             mock.patch.object(cli.pub, "publicar"), mock.patch.object(cli.alr, "publicar_alertas"), mock.patch.object(cli.alr, "registrar_novos", return_value=[]):
            rc = cli.diario(self.conn, ["prefeitura", "camara"])
        self.assertEqual(rc & 1, 1)
        r = self.conn.execute("SELECT status, mensagem FROM execucao_coleta WHERE fonte='portal_no_ar'").fetchall()
        self.assertEqual(len(r), 2); self.assertIn("530", r[0]["mensagem"])

    def test_agendamento_em_horario_comercial_com_segunda_chance(self):
        y = (config.RAIZ / ".github" / "workflows" / "diario.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "17 15 * * *"', y); self.assertIn('cron: "17 21 * * *"', y)
        self.assertIn("needs: decidir", y); self.assertIn("rodar == 'true'", y)
