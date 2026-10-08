import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from contas import cli, db, validar
from contas.coleta import entradas, receitas, siconfi
from contas import publicar_receitas as pr


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.conn = db.conectar(Path(self.tmp.name) / "t.sqlite"); self.addCleanup(self.conn.close)


class Arvore(unittest.TestCase):
    def test_no_com_mesmo_codigo_do_pai_nao_aponta_para_si(self):
        """Regressão: deduções do Fundeb têm o mesmo código nos níveis 3 e 7; isso travou a tela (laço infinito)."""
        linhas = [{"ordem": 1, "codigo": "9000"}, {"ordem": 2, "codigo": "9500"}, {"ordem": 3, "codigo": "9510"}, {"ordem": 7, "codigo": "9510"}]
        n = pr.arvore(linhas)
        self.assertEqual([(x["codigo"], x["ordem"], x["pai"], x["pai_ordem"]) for x in n],
                         [("9000", 1, None, None), ("9500", 2, "9000", 1), ("9510", 3, "9500", 2), ("9510", 7, "9510", 3)])
        self.assertNotEqual((n[3]["codigo"], n[3]["ordem"]), (n[3]["pai"], n[3]["pai_ordem"]))

    def test_ignora_nivel_10_e_reata_pai_correto(self):
        linhas = [{"ordem": 2, "codigo": "1100"}, {"ordem": 4, "codigo": "1112"}, {"ordem": 7, "codigo": "1112.50"}, {"ordem": 10, "codigo": "1112.50.x"}, {"ordem": 7, "codigo": "1112.53"}]
        n = pr.arvore(linhas)
        self.assertEqual([(x["codigo"], x["pai"]) for x in n], [("1100", None), ("1112", "1100"), ("1112.50", "1112"), ("1112.53", "1112")])


class ReceitaPortal(Base):
    def _linha(self, ano, linha, ordem, cod, arr):
        self.conn.execute("INSERT INTO receita VALUES ('prefeitura',?,?,?,?,'x',0,0,?)", (ano, linha, ordem, cod, arr))

    def test_anos_fechados_zerados_sao_apagados_e_o_corrente_fica(self):
        self._linha(2025, 0, 1, "1000", 0); self._linha(2026, 0, 1, "1000", 500)
        self.conn.execute("INSERT INTO receita_mensal_topo VALUES ('prefeitura',2025,1,'1000','x',0)")
        self.assertEqual(receitas.limpar_exercicios_zerados(self.conn, "prefeitura", date(2026, 10, 8)), 2)
        self.assertEqual([r[0] for r in self.conn.execute("SELECT DISTINCT exercicio FROM receita")], [2026])

    def test_ano_fechado_nao_chama_o_portal(self):
        with mock.patch.object(receitas.http, "get_json", side_effect=AssertionError("não deveria consultar")):
            receitas.coletar_receitas(self.conn, "prefeitura", 2025, hoje=date(2026, 10, 8))
        self.assertIn("ignorado", self.conn.execute("SELECT mensagem FROM execucao_coleta ORDER BY id DESC").fetchone()[0])

    def test_anos_fechados_nao_sao_revisados_para_receita(self):
        self.assertNotIn("receitas", cli.fontes_fechadas("prefeitura"))

    def test_validacao_da_arvore(self):
        for i, (o, c, a) in enumerate([(1, "1000", 100), (2, "1100", 100), (3, "1110", 100), (4, "1112", 100), (7, "1112.50", 60), (7, "1112.53", 40)]):
            self._linha(2026, i, o, c, a)
        self.conn.commit()
        r = {x["checagem"]: x for x in validar.checagens_receitas(self.conn, 2026)}
        self.assertEqual(r["receita_arvore_fecha_entre_niveis"]["status"], "ok")
        self.conn.execute("UPDATE receita SET arrecadado=61 WHERE codigo='1112.50'"); self.conn.commit()
        r = {x["checagem"]: x for x in validar.checagens_receitas(self.conn, 2026)}
        self.assertEqual(r["receita_arvore_fecha_entre_niveis"]["status"], "divergente")


class Siconfi(Base):
    def test_centavos_sem_erro_de_float(self):
        self.assertEqual(siconfi.centavos_float(772833631.09), 77283363109)
        self.assertEqual(siconfi.centavos_float(0.1 + 0.2), 30)

    def test_paginacao(self):
        paginas = iter([{"items": [{"a": 1}, {"a": 2}], "hasMore": True}, {"items": [{"a": 3}], "hasMore": False}])
        with mock.patch.object(siconfi.http, "get_json_externo", side_effect=lambda url: next(paginas)):
            self.assertEqual(len(siconfi.consulta("dca", x=1)), 3)

    def _dca(self, valor):
        it = lambda col, cod, v: {"coluna": col, "cod_conta": cod, "conta": cod, "valor": v}
        return [it("Receitas Brutas Realizadas", "ReceitasExcetoIntraOrcamentarias", valor), it("Deduções - FUNDEB", "ReceitasExcetoIntraOrcamentarias", 10.5),
                it("Outras Deduções da Receita", "ReceitasExcetoIntraOrcamentarias", 4.0), it("Receitas Brutas Realizadas", "RO1.0.0.0.00.0.0", valor)]

    def test_dca_idempotente_e_nao_apaga_com_resposta_vazia(self):
        with mock.patch.object(siconfi, "consulta", return_value=self._dca(1000.0)):
            siconfi.coletar_dca(self.conn, [2024]); siconfi.coletar_dca(self.conn, [2024])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM siconfi_receita").fetchone()[0], 4)
        with mock.patch.object(siconfi, "consulta", return_value=[]):
            siconfi.coletar_dca(self.conn, [2024])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM siconfi_receita").fetchone()[0], 4)      # ano ainda não declarado: mantém

    def test_campo_ausente_levanta(self):
        with mock.patch.object(siconfi, "consulta", return_value=[{"coluna": "x"}]):
            with self.assertRaises(siconfi.FormatoMudou):
                siconfi.coletar_dca(self.conn, [2024])

    def test_dca_publicada_com_liquida_e_ordem(self):
        with mock.patch.object(siconfi, "consulta", return_value=self._dca(1000.0)):
            siconfi.coletar_dca(self.conn, [2024])
        d = pr.dca(self.conn)
        self.assertEqual(d["totais"]["2024"], {"bruta": 100000, "fundeb": 1050, "outras": 400, "liquida": 98550})
        self.assertEqual(pr.nivel_dca("RO1.1.1.2.50.0.0"), 5); self.assertEqual(pr.nivel_dca("RO1.0.0.0.00.0.0"), 1)

    def test_siconfi_so_as_segundas_ou_se_vazio(self):
        self.assertTrue(cli.siconfi_devido(self.conn, date(2026, 10, 8)))                        # vazio
        self.conn.execute("INSERT INTO siconfi_receita VALUES ('dca',2024,0,'c','k','n',1,'x')"); self.conn.commit()
        self.assertFalse(cli.siconfi_devido(self.conn, date(2026, 10, 8)))                       # quinta-feira
        self.assertTrue(cli.siconfi_devido(self.conn, date(2026, 10, 5)))                        # segunda-feira
        self.assertTrue(cli.siconfi_devido(self.conn, date(2026, 10, 8), completo=True))


class Extra(unittest.TestCase):
    def test_agrupa_sem_expor_nomes(self):
        self.assertEqual(entradas.grupo_extra("12423 - PLANOS DE PREVIDENCIA E ASSISTENCIA MEDICA"), entradas.GRUPOS[1][0])
        self.assertEqual(entradas.grupo_extra("4985 - UNIMED COPARTICIPAÇÃO"), "Planos de saúde e odontológicos")
        self.assertEqual(entradas.grupo_extra("45464 - BANCO BRADESCO"), "Empréstimos consignados e instituições financeiras")
        self.assertEqual(entradas.grupo_extra("PENSAO ALIMENTICIA (F)"), "Pensão alimentícia e descontos judiciais")
        self.assertEqual(entradas.grupo_extra("KELLY JOANA FERREIRA - TERMO DE SESSÃO Nº 005/2026"), "Garantias, cauções e depósitos")
        self.assertEqual(entradas.grupo_extra("FULANO DE TAL"), entradas.OUTROS)


if __name__ == "__main__":
    unittest.main()
