import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from contas import db, publicar, validar
from contas.coleta import despesas, ibge, mensal, pessoal, receitas
from contas.parsers import centavos

AMOSTRA = Path(__file__).resolve().parent.parent / "fase1" / "amostras" / "prefeitura_despesas_gerais.json"


def empenho(pk, tipo="OR", e="100,00", l="60,00", p="40,00", codif="1", codlo="020601", num=None, origem="", data="05/01/2026 00:00:00"):
    return {"PKEMP": pk, "CODIGO": num or pk, "TPEM": tipo, "PKEMPA": origem, "CODIF": codif, "NOMEFOR": f"FORN {codif}",
            "DATAE": data, "CODLO": codlo, "ELEMENTO": "39", "NATUREZA": "Serviços", "FUNCAONOME": "Educação",
            "PRODU": "teste", "CPFFORMATADO": "11.111.111/0001-11", "EMPENHADO": e, "LIQUIDADO": l, "PAGO": p,
            "ANULADO": "0", "REFORCO": "0", "DOTAC": "999", "ALTDO": "0", "DOTACATUALIZADA": "999"}


def base_dados():
    return [empenho("1"), empenho("2", e="50,50", l="0", p="0", codif="2"),
            empenho("3", tipo="AN", e="-20,00", l="0", p="0", origem="1", num="1", data="10/02/2026 00:00:00")]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.conectar(Path(self.tmp.name) / "t.sqlite")
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.conn.close)

    def carrega(self, dados, ano=2026):
        with mock.patch.object(despesas, "_baixar_com_cache", return_value=(dados, "http://x", 123)):
            return despesas.coletar_empenhos(self.conn, "prefeitura", ano)


class Empenhos(Base):
    def test_anulacao_entra_com_sinal_da_fonte(self):
        self.carrega(base_dados())
        t = self.conn.execute("SELECT SUM(empenhado) e, SUM(liquidado) l, SUM(pago) p, COUNT(*) n FROM empenho").fetchone()
        self.assertEqual((t["e"], t["l"], t["p"], t["n"]), (13050, 6000, 4000, 3))   # 100 + 50,50 - 20

    def test_idempotente(self):
        self.carrega(base_dados()); self.carrega(base_dados())
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM empenho").fetchone()[0], 3)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM fornecedor").fetchone()[0], 2)

    def test_registro_removido_na_fonte_some(self):
        self.carrega(base_dados()); self.carrega(base_dados()[:2])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM empenho").fetchone()[0], 2)

    def test_pkemp_duplicado_aborta_e_nao_apaga_o_que_havia(self):
        self.carrega(base_dados())
        with self.assertRaises(despesas.FormatoMudou):
            self.carrega(base_dados() + [empenho("1")])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM empenho").fetchone()[0], 3)
        self.assertEqual(self.conn.execute("SELECT status FROM execucao_coleta ORDER BY id DESC LIMIT 1").fetchone()[0], "erro")

    def test_campo_ausente_levanta_formato_mudou(self):
        ruim = base_dados(); del ruim[0]["CODLO"]
        with self.assertRaises(despesas.FormatoMudou):
            self.carrega(ruim)

    def test_orgao_vem_do_codigo_da_unidade(self):
        self.carrega(base_dados())
        self.assertEqual(self.conn.execute("SELECT DISTINCT orgao FROM empenho").fetchone()[0], "0206")

    @unittest.skipUnless(AMOSTRA.exists(), "amostra real da Fase 1 ausente")
    def test_amostra_real_converte(self):
        for r in json.loads(AMOSTRA.read_text()):
            t = despesas.converte_empenho("prefeitura", 2026, r)
            self.assertEqual(len(t), 22)
            self.assertRegex(t[7], r"^\d{4}-\d{2}-\d{2}$")
            self.assertIsInstance(t[19], int)


class Validacao(Base):
    def totais(self, e, l, p, dot=1000):
        agora = db.agora()
        for origem in ("por_orgao", "por_fornecedor"):
            self.conn.execute("INSERT INTO total_portal VALUES ('prefeitura',2026,?,?,?,?,?,?)", (origem, e, l, p, dot, agora))
        self.conn.execute("INSERT INTO orgao_total_portal VALUES ('prefeitura',2026,'0206',?,?,?,?)", (e, l, p, dot))
        self.conn.commit()

    def test_confere(self):
        self.carrega(base_dados()); self.totais(13050, 6000, 4000)
        res = validar.validar(self.conn, "prefeitura", 2026)
        self.assertEqual(validar.resumo(res)[1], 0, [r for r in res if r["status"] != "ok"])

    def test_divergencia_de_um_centavo_e_detectada(self):
        self.carrega(base_dados()); self.totais(13051, 6000, 4000)
        res = {r["checagem"]: r for r in validar.validar(self.conn, "prefeitura", 2026)}
        self.assertEqual(res["empenhado_vs_portal_por_orgao"]["status"], "divergente")
        self.assertEqual(res["empenhado_vs_portal_por_orgao"]["diferenca"], -1)
        self.assertEqual(res["por_orgao_confere"]["status"], "divergente")

    def test_subtrair_anulado_de_novo_nao_bate(self):
        """Documenta a regra descoberta na Fase 1: EMPENHADO já é líquido; não subtrair ANULADO outra vez."""
        d = base_dados(); d[2]["ANULADO"] = "20,00"
        self.carrega(d)
        soma = self.conn.execute("SELECT SUM(empenhado) FROM empenho").fetchone()[0]
        self.assertEqual(soma, sum(centavos(r["EMPENHADO"]) for r in d))


class Funcoes(unittest.TestCase):
    def test_diferenca_de_acumulados(self):
        acum = {1: {"A": (100, 50)}, 2: {"A": (250, 80), "B": (10, 10)}, 3: {"A": (250, 90)}}
        m = mensal.diferenca_acumulados(acum)
        self.assertEqual(m[1]["A"], (100, 50)); self.assertEqual(m[2]["A"], (150, 30))
        self.assertEqual(m[2]["B"], (10, 10)); self.assertEqual(m[3]["A"], (0, 10))

    def test_receita_topo_so_ordem_1(self):
        L = [{"ORDEM": "1"}, {"ORDEM": "10"}, {"ORDEM": " 1 "}, {"ORDEM": "3"}]
        self.assertEqual(len(receitas.topo(L)), 2)

    def test_ibge_serie(self):
        resp = [{"resultados": [{"series": [{"serie": {"2025": "96006", "2026": "99053", "2022": "-"}}]}]}]
        self.assertEqual(ibge.extrai_serie(resp), {2025: 96006, 2026: 99053})
        with self.assertRaises(RuntimeError):
            ibge.extrai_serie([])

    def test_k_anonimato_grupos_pequenos(self):
        regs = [{"cargo": "A", "proventos": 100, "descontos": 10}] * 5 + \
               [{"cargo": "B", "proventos": 999999, "descontos": 1}] + [{"cargo": "C", "proventos": 7, "descontos": 1}]
        r = {c: q for c, q, *_ in pessoal.agrega(regs, lambda s: s["cargo"], k=3)}
        self.assertEqual(r, {"A": 5})   # B e C (1 pessoa cada) somam 2 < 3: nem "Outros" aparece

    def test_k_anonimato_outros_so_se_nao_identifica(self):
        regs = [{"cargo": c, "proventos": 10, "descontos": 1} for c in "BCD"]
        r = {c: q for c, q, *_ in pessoal.agrega(regs, lambda s: s["cargo"], k=3)}
        self.assertEqual(r, {pessoal.OUTROS: 3})

    def test_nenhum_nome_e_gravado_na_folha(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        conn = db.conectar(Path(tmp.name) / "t.sqlite"); self.addCleanup(conn.close)
        folha = [{"NOME": f"PESSOA SECRETA {i}", "CARGO": "PROFESSOR", "DIVISAO": "EDUCACAO", "VINCULO": "Estatutário",
                  "PROVENTOS": "1000,00", "DESCONTOS": "100,00", "CPF": "-", "CPFFORMATADO": "111.XXX.XXX-11"} for i in range(5)]
        with mock.patch.object(pessoal, "_mes_disponivel", return_value=(folha, "http://x", 1)):
            pessoal.coletar_folha(conn, "prefeitura", 2026)
        despejo = "\n".join(str(tuple(r)) for t in ("servidor_agregado", "fornecedor", "execucao_coleta") for r in conn.execute(f"SELECT * FROM {t}"))
        self.assertNotIn("SECRETA", despejo)
        self.assertEqual(conn.execute("SELECT qtd FROM servidor_agregado WHERE dimensao='total'").fetchone()[0], 5)


class Publicacao(Base):
    def test_gera_json_sem_campos_sensiveis(self):
        self.carrega(base_dados())
        with tempfile.TemporaryDirectory() as out:
            publicar.publicar(self.conn, "prefeitura", Path(out))
            r = json.loads((Path(out) / "prefeitura" / "resumo.json").read_text())
            self.assertEqual(r["anos"]["2026"]["empenhado"], 13050)
            emp = json.loads((Path(out) / "prefeitura" / "empenhos_2026.json").read_text())
            self.assertEqual(len(emp["linhas"]), 3)
            todos = "".join(p.read_text() for p in Path(out).rglob("*.json"))
            for proibido in ("FORNECEDOR_CONTA", "AGENCIA", "LOGIN"):
                self.assertNotIn(proibido, todos)


if __name__ == "__main__":
    unittest.main()
