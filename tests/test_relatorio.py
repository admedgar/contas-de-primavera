import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from contas import db, publicar_relatorios as pubrel, relatorio as rel

HOJE = date(2026, 10, 7)          # quarta-feira (semana ISO 41: 05/10 a 11/10)


class FakeIA:
    """Cliente falso da Anthropic: devolve respostas na ordem; um item Exception é lançado."""
    def __init__(self, *respostas):
        self.respostas, self.chamadas = list(respostas), 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.chamadas += 1
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=r if isinstance(r, str) else json.dumps(r))])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.conn = db.conectar(Path(self.tmp.name) / "t.sqlite"); self.addCleanup(self.conn.close)
        self.conn.execute("INSERT INTO orgao VALUES ('prefeitura','0206','SECRETARIA DE EDUCAÇÃO')")
        for cod, nome, doc, tp in (("1", "EMPRESA GRANDE LTDA", "11.111.111/0001-11", "cnpj"), ("2", "FULANA BENEFICIARIA", "222.XXX.XXX-22", "cpf_mascarado"),
                                   ("3", "PREFEITURA MUNICIPAL DE PRIMAVERA DO LE", "01.974.088/0001-05", "cnpj")):
            self.conn.execute("INSERT INTO fornecedor VALUES ('prefeitura',?,?,?,?)", (cod, nome, doc, tp))
        self.n = 0
        # semana anterior (28/09 a 02/10) e semana corrente (05/10 a 07/10)
        self.emp(1000, "1", data="2026-09-29"); self.emp(1000, "1", data="2026-09-30")
        self.emp(2000, "1", data="2026-10-05", modalidade="DISPENSA"); self.emp(500, "2", data="2026-10-05", elemento="48")
        self.emp(9000, "3", data="2026-10-06", elemento="11")            # folha em nome da própria Prefeitura
        self.emp(-300, "1", tipo="AN", data="2026-10-07")
        self.conn.execute("INSERT INTO mensal_orgao VALUES ('prefeitura',2026,10,'0206',123400,50000,40000)")
        self.conn.commit()

    def emp(self, reais, codif="1", tipo="OR", modalidade="", elemento="39", data="2026-10-05"):
        self.n += 1
        self.conn.execute("INSERT INTO empenho VALUES ('prefeitura',2026,?,?,?,NULL,?,?, '0206','020601','Educação','','','',?,'Serviços','',?,'HISTORICO PRIVADO',?,?,?)",
                          (f"p{self.n}", str(self.n), tipo, codif, data, elemento, modalidade, round(reais * 100), round(reais * 50), 0))
        self.conn.commit()


class Fatos(Base):
    def f(self, tipo="semana", chave="2026-W41", ini=date(2026, 10, 5), fim=date(2026, 10, 11)):
        return rel.fatos(self.conn, "prefeitura", tipo, chave, ini, fim, rel.referencia_portal(self.conn, "prefeitura", HOJE))

    def test_referencia_e_total_com_anulacao(self):
        self.assertEqual(rel.referencia_portal(self.conn, "prefeitura", HOJE), date(2026, 10, 7))
        f = self.f()
        self.assertTrue(f["parcial"])
        self.assertEqual(f["ate"], "2026-10-07")
        self.assertEqual(f["emissao"]["empenhado"], round((2000 + 500 + 9000 - 300) * 100))
        self.assertEqual(f["emissao"]["anulado"], -30000)
        self.assertEqual(f["emissao"]["qtd"], 3)              # AN não conta como empenho emitido
        self.assertEqual(f["dias_com_registro"], 3)

    def test_comparacao_mesmos_dias_da_semana_anterior(self):
        c = self.f()["comparacao"]
        self.assertEqual((c["inicio"], c["fim"]), ("2026-09-28", "2026-09-30"))
        self.assertEqual(c["empenhado"], 200000)
        self.assertEqual(c["variacao_pct"], round((1120000 - 200000) / 200000 * 100, 1))

    def test_pessoa_fisica_nunca_nomeada_e_ente_fora_dos_maiores(self):
        f = self.f()
        txt = json.dumps(f, ensure_ascii=False) + json.dumps(rel.ficha(f), ensure_ascii=False)
        self.assertNotIn("FULANA", txt)
        self.assertNotIn("HISTORICO PRIVADO", txt)              # histórico nunca entra
        self.assertEqual(f["pessoas_fisicas"]["pessoas"], 1)
        self.assertNotIn("PREFEITURA MUNICIPAL", " ".join(m["fornecedor"] for m in f["maiores"]))
        self.assertNotIn("PREFEITURA MUNICIPAL", " ".join(i["nome"] for i in f["fornecedores"]))
        self.assertEqual(f["maiores"][0]["fornecedor"], "EMPRESA GRANDE LTDA")

    def test_mes_traz_total_oficial_do_portal(self):
        f = self.f("mes", "2026-10", date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(f["oficial_mes"]["mes"], {"empenhado": 123400, "liquidado": 50000, "pago": 40000})

    def test_periodo_sem_dados_devolve_none(self):
        self.assertIsNone(rel.fatos(self.conn, "prefeitura", "semana", "2026-W30", date(2026, 7, 20), date(2026, 7, 26), date(2026, 10, 7)))

    def test_formatacao(self):
        self.assertEqual(rel.compacto(320000000), "R$ 3,2 milhões")
        self.assertEqual(rel.compacto(100000000), "R$ 1,0 milhão")
        self.assertEqual(rel.compacto(125000), "R$ 1,2 mil")
        self.assertEqual(rel.brl(123456), "R$ 1.234,56")
        self.assertEqual(rel.num(2189), "2.189")


class Diarias(Base):
    def dia(self, codif, cargo, reais, data="2026-10-05", elem="Diárias - Civil", anul=0, qtd="2"):
        self.conn.execute("INSERT INTO diaria (entidade, exercicio, data, valor, valor_anulado, quantidade, elemento, codif, favorecido, cargo) "
                          "VALUES ('camara',2026,?,?,?,?,?,?,'NOME','"+cargo+"')", (data, round(reais * 100), round(anul * 100), qtd, elem, codif))

    def setUp(self):
        super().setUp()
        self.conn.execute("INSERT INTO vereador (id, nome, nome_norm, cpf_mascarado) VALUES (1,'VEREADOR UM','VEREADOR UM','111.XXX.XXX-11'), (2,'VEREADORA DOIS','VEREADORA DOIS','222.XXX.XXX-22')")
        self.conn.execute("INSERT INTO vereador_folha VALUES (1,2026,10,'VEREADOR','x','',100,0,1), (2,2026,10,'VEREADOR','x','',100,0,1)")
        self.conn.execute("INSERT INTO vereador_vinculo VALUES ('c1',1,'confirmado','regra',NULL), ('c2',2,'sugerido','regra',NULL)")
        self.dia("c1", "VEREADOR", 1500, anul=200); self.dia("c1", "VEREADOR", 500, data="2026-10-06")
        self.dia("c2", "VEREADOR", 300)                                   # vínculo só sugerido: não é nominal
        for i in range(3): self.dia(f"s{i}", "ASSESSOR", 100)             # servidores: só somados
        self.dia("c1", "VEREADOR", 999, elem="Passagens Aéreas")          # passagem não é diária
        self.conn.commit()

    def test_vereadores_nominais_e_demais_somados(self):
        d = rel._diarias(self.conn, "camara", date(2026, 10, 5), date(2026, 10, 7))
        self.assertEqual(d["vereadores"], [{"nome": "VEREADOR UM", "qtd": 2, "dias": 4.0, "valor": 180000}])
        self.assertEqual(d["pendentes"], {"qtd": 1, "valor": 30000})
        self.assertEqual(d["servidores"], {"qtd": 3, "valor": 30000, "pessoas": 3})
        self.assertEqual(d["qtd"], 6)                                      # passagem fora
        self.assertEqual(d["valor"], 180000 + 30000 + 30000)

    def test_ficha_da_ia_nao_leva_nomes(self):
        d = rel._diarias(self.conn, "camara", date(2026, 10, 5), date(2026, 10, 7))
        f = {"entidade": "camara", "nome": "Câmara", "rotulo": "x", "parcial": False, "ate": "2026-10-07", "dias_com_registro": 2,
             "emissao": {"qtd": 1, "empenhado": 1, "anulado": 0, "liquidado": 0, "pago": 0},
             "comparacao": {"variacao_pct": None}, "orgaos": [], "elementos": [], "fornecedores": [], "pessoas_fisicas": None, "maiores": [],
             "modalidades": [], "licitacoes": {"qtd": 0, "valor": 0, "por_modalidade": []}, "contratos": {"qtd": 0, "valor": 0},
             "dia_pico": {"data": "2026-10-05", "empenhado": 1, "pct": None}, "camara": {"diarias": d, "verba": {}}}
        txt = json.dumps(rel.ficha(f), ensure_ascii=False) + json.dumps(rel.modelo_fixo(f), ensure_ascii=False)
        self.assertNotIn("VEREADOR UM", txt)
        self.assertIn("vereadores: R$ 1,8 mil", txt)


class Verificacao(Base):
    def setUp(self):
        super().setUp()
        self.f = rel.fatos(self.conn, "prefeitura", "semana", "2026-W41", date(2026, 10, 5), date(2026, 10, 11), date(2026, 10, 7))
        self.fich = rel.ficha(self.f)
        self.ok = {"titulo": "Semana", "resumo": f"O portal registra {self.fich['empenhado_liquido_no_periodo']} empenhados.",
                   "pontos": ["Um ponto."], "observacoes": ["Limites."]}

    def test_aprova_texto_com_numeros_da_ficha(self):
        self.assertEqual(rel.verificar(self.ok, self.fich), [])

    def test_reprova_numero_inventado_e_juizo_de_valor(self):
        self.assertTrue(rel.verificar({**self.ok, "resumo": "O gasto foi de R$ 987,6 milhões."}, self.fich))
        self.assertTrue(rel.verificar({**self.ok, "pontos": ["Um valor excessivo para o período."]}, self.fich))
        self.assertTrue(rel.verificar({"titulo": "x"}, self.fich))

    def test_modelo_fixo_passa_na_propria_verificacao_de_numeros(self):
        mf = rel.modelo_fixo(self.f)
        self.assertEqual(rel.verificar(mf, self.fich), [])


class Geracao(Base):
    BOM = {"titulo": "T", "resumo": "O portal registra empenhos no período, sem comparar com outros.", "pontos": ["p"], "observacoes": ["o"]}

    def gera(self, cliente, **kw):
        return rel.gerar(self.conn, ["prefeitura"], hoje=HOJE, cliente=cliente, **kw)

    def origens(self):
        return {r["origem"] for r in self.conn.execute("SELECT origem FROM relatorio")}

    def test_sem_ia_usa_modelo_fixo_rotulado(self):
        c = self.gera(None, usar_ia=False)
        self.assertGreater(c["modelo_fixo"], 0); self.assertEqual(c["ia"], 0)
        self.assertEqual(self.origens(), {"modelo"})

    def test_com_ia_aprovada(self):
        ia = FakeIA(*[self.BOM] * 20)
        self.gera(ia)
        r = self.conn.execute("SELECT origem, modelo FROM relatorio WHERE chave='2026-W41'").fetchone()
        self.assertEqual((r["origem"], r["modelo"]), ("ia", rel.MODELO_PADRAO))

    def test_ia_reprovada_duas_vezes_cai_no_modelo_fixo(self):
        ruim = {**self.BOM, "resumo": "Gasto absurdo de R$ 999,9 milhões."}
        self.gera(FakeIA(*[ruim] * 40))
        self.assertEqual(self.origens(), {"modelo"})

    def test_falha_da_ia_nunca_derruba(self):
        self.gera(FakeIA(*[RuntimeError("rede")] * 20))
        self.assertEqual(self.origens(), {"modelo"})

    def test_resposta_que_nao_e_json_cai_no_modelo_fixo(self):
        self.gera(FakeIA(*["isto não é json"] * 40))
        self.assertEqual(self.origens(), {"modelo"})

    def test_nao_chama_ia_de_novo_se_nada_mudou(self):
        ia = FakeIA(*[self.BOM] * 40)
        self.gera(ia)
        antes = ia.chamadas
        self.gera(ia)
        self.assertEqual(ia.chamadas, antes)

    def test_numeros_novos_geram_novo_texto(self):
        self.gera(None, usar_ia=False)
        self.emp(700, "1", data="2026-10-07")
        c = self.gera(None, usar_ia=False)
        self.assertGreaterEqual(c["gerados"], 1)

    def test_texto_do_modelo_fixo_e_trocado_quando_a_ia_aparece(self):
        self.gera(None, usar_ia=False)
        self.gera(FakeIA(*[self.BOM] * 40))
        self.assertIn("ia", self.origens())


class Publicacao(Base):
    def test_publica_indice_e_arquivos(self):
        rel.gerar(self.conn, ["prefeitura"], hoje=HOJE, usar_ia=False)
        saida = Path(self.tmp.name) / "web_data"
        idx = pubrel.publicar_relatorios(self.conn, saida)
        self.assertIn("2026-W41", [i["chave"] for i in idx["itens"]["prefeitura"]["semana"]])
        self.assertEqual(idx["padrao"]["prefeitura"]["semana"], "2026-W41")      # 3 dias com registro: a corrente já é a principal
        corpo = json.loads((saida / "relatorios" / "prefeitura_semana_2026-W41.json").read_text(encoding="utf-8"))
        self.assertEqual(corpo["origem"], "modelo")
        self.assertIn("resumo", corpo["texto"])
        self.assertFalse(idx["ia_em_uso"])


if __name__ == "__main__":
    unittest.main()
