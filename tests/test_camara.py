import json
import tempfile
import unittest
from pathlib import Path

from contas import db, publicar_camara as pc
from contas.coleta import camara as cam, vinculos


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.conn = db.conectar(Path(self.tmp.name) / "t.sqlite"); self.addCleanup(self.conn.close)
        self.csv = Path(self.tmp.name) / "v.csv"
        self.csv.write_text("codif;vereador;decisao;nota\n")

    def vereador(self, nome, cpf):
        return vinculos.registrar_vereador(self.conn, nome, cpf)

    def forn(self, codif, nome, doc):
        self.conn.execute("INSERT INTO fornecedor VALUES ('camara',?,?,?,?)", (codif, nome, doc, "cnpj" if "/" in doc else "cpf_mascarado"))

    def emp(self, pk, codif, hist, pago, elemento="93", data="2026-02-10", ano=2026):
        self.conn.execute("INSERT INTO empenho VALUES ('camara',?,?,?, 'OR',NULL,?,?, '0101','010101','Legislativa','','','',?, 'Indenizações', '', '', ?,?,?,?)",
                          (ano, pk, pk, codif, data, elemento, hist, pago, pago, pago))


class Texto(unittest.TestCase):
    def test_competencia(self):
        self.assertEqual(cam.competencia("VERBA INDENIZATÓRIA REF: 01/2026."), "2026-01")
        self.assertEqual(cam.competencia("DESPESAS REALIZADAS NO MES DE MAIO 2026"), "2026-05")
        self.assertEqual(cam.competencia("DESPESAS NO MÊS DE MARÇO DE 2026"), "2026-03")
        self.assertIsNone(cam.competencia("REEMBOLSO DE ABASTECIMENTO"))

    def test_categoria_93(self):
        self.assertEqual(cam.categoria_93("Verba indenizatoria destinada a cobrir gastos"), "verba")
        self.assertEqual(cam.categoria_93("REEMBOLSO DE PASSAGEM AEREA"), "reembolso")

    def test_so_cargo_vereador(self):
        self.assertTrue(cam.eh_vereador("VEREADOR")); self.assertTrue(cam.eh_vereador("Vereadora"))
        self.assertFalse(cam.eh_vereador("ASSESSOR DE VEREADOR")); self.assertFalse(cam.eh_vereador("ASSESSOR PARLAMENTAR"))

    def test_passageiros(self):
        d = "FORNECIMENTO DE PASSÁGENS AÉREAS.\n\nPassageira: Mariana Leandro Dallabrida Carvalho Trecho:  Cuiabá/MT (CGB) x Brasília"
        self.assertEqual(pc.passageiros(d), ["Mariana Leandro Dallabrida Carvalho"])
        self.assertEqual(pc.passageiros("LOCAÇÃO DE VEÍCULOS"), [])


class Vinculos(Base):
    def test_mesma_pessoa_com_grafia_diferente(self):
        a = self.vereador("ROGERIO HENRIQUEDE ARAUJO", "111.XXX.XXX-11")
        self.assertEqual(self.vereador("ROGERIO HENRIQUE DE ARAUJO", "111.XXX.XXX-11"), a)
        self.assertNotEqual(self.vereador("ROGERIO HENRIQUE DE ARAUJO", "222.XXX.XXX-22"), a)   # outro CPF mascarado = outra pessoa

    def test_regra_confirma_so_com_cpf_e_nome(self):
        v = self.vereador("SERGIO RODRIGUES GONCALVES", "695.XXX.XXX-72")
        self.forn("1728", "SERGIO RODRIGUES GONCALVES", "695.XXX.XXX-72")        # igual -> confirmado
        self.forn("775", "SERGIO RODRIGUES GONÇALVES", "14.780.772/0001-06")      # nome igual, CNPJ -> só sugerido
        self.forn("9", "FULANO DE TAL", "999.XXX.XXX-99")                         # nada
        vinculos.vincular(self.conn, "camara", self.csv)
        st = {r["codif"]: (r["status"], r["origem"]) for r in self.conn.execute("SELECT * FROM vereador_vinculo")}
        self.assertEqual(st, {"1728": ("confirmado", "regra"), "775": ("sugerido", "regra")})
        self.assertEqual(self.conn.execute("SELECT vereador_id FROM vereador_vinculo WHERE codif='1728'").fetchone()[0], v)

    def test_decisao_manual_prevalece(self):
        self.vereador("SERGIO RODRIGUES GONCALVES", "695.XXX.XXX-72")
        self.forn("775", "SERGIO RODRIGUES GONÇALVES", "14.780.772/0001-06")
        self.csv.write_text("codif;vereador;decisao;nota\n775;Sérgio Rodrigues Gonçalves;confirmar;confirmado pelo cliente\n")
        vinculos.vincular(self.conn, "camara", self.csv)
        self.assertEqual(self.conn.execute("SELECT status, origem FROM vereador_vinculo WHERE codif='775'").fetchone()[:], ("confirmado", "manual"))

    def test_csv_com_vereador_inexistente_falha_alto(self):
        self.csv.write_text("codif;vereador;decisao;nota\n1;Ninguém;confirmar;\n")
        with self.assertRaises(ValueError):
            vinculos.vincular(self.conn, "camara", self.csv)


class Verba(Base):
    def test_deriva_e_separa(self):
        v = self.vereador("ANA SOUZA", "123.XXX.XXX-45"); self.forn("1", "ANA SOUZA", "123.XXX.XXX-45"); self.forn("2", "OUTRO NOME", "333.XXX.XXX-33")
        self.emp("a", "1", "VERBA INDENIZATÓRIA REF: 02/2026", 834000)
        self.emp("b", "1", "REEMBOLSO DE PASSAGEM AEREA", 404116)
        self.emp("c", "2", "VERBA INDENIZATORIA DESTINADA A COBRIR GASTOS", 834000)    # favorecido não vinculado
        vinculos.vincular(self.conn, "camara", self.csv)
        cam.derivar_verba(self.conn, "camara", 2026)
        r = {x["pkemp"]: (x["categoria"], x["vereador_id"], x["competencia"]) for x in self.conn.execute("SELECT * FROM verba_indenizatoria")}
        self.assertEqual(r, {"a": ("verba", v, "2026-02"), "b": ("reembolso", v, None), "c": ("verba", None, None)})
        self.assertEqual(self.conn.execute("SELECT SUM(pago) FROM verba_indenizatoria").fetchone()[0], self.conn.execute("SELECT SUM(pago) FROM empenho").fetchone()[0])

    def test_tabela_de_detalhamento_existe_e_esta_vazia(self):
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM verba_indenizatoria_item").fetchone()[0], 0)


class Publicacao(Base):
    def test_criterio_unico_e_privacidade(self):
        a = self.vereador("ANA SOUZA", "123.XXX.XXX-45"); b = self.vereador("BRUNO LIMA", "456.XXX.XXX-78")
        for vid, meses in ((a, (1, 2, 3, 4)), (b, (3, 4))):
            for m in meses:
                self.conn.execute("INSERT INTO vereador_folha VALUES (?,?,?,?,?,?,?,?,?)", (vid, 2026, m, "VEREADOR", "Eletivo", "2025-01-01", 1450242, 800000, 1))
        self.forn("1", "ANA SOUZA", "123.XXX.XXX-45"); self.forn("2", "BRUNO LIMA", "456.XXX.XXX-78")
        for pk, cod, pago in (("a1", "1", 834000), ("a2", "1", 834000), ("b1", "2", 834000)):
            self.emp(pk, cod, "VERBA INDENIZATÓRIA REF: 01/2026", pago)
        for i, nome in enumerate(("SERVIDORA SECRETA 1", "SERVIDORA SECRETA 2", "SERVIDORA SECRETA 3", "SOLITARIA CHEFE")):
            cargo = "ASSISTENTE" if i < 3 else "DIRETORA GERAL"
            self.conn.execute("INSERT INTO diaria (entidade, exercicio, pkemp, data, valor, valor_anulado, quantidade, elemento, descricao, codif, favorecido, cargo, cpf_mascarado) "
                              "VALUES ('camara',2026,'x','2026-03-01',100000,0,'2','DIÁRIAS - CIVIL','viagem',?,?,?,?)", (f"s{i}", nome, cargo, f"90{i}.XXX.XXX-00"))
        self.conn.execute("INSERT INTO diaria (entidade, exercicio, pkemp, data, valor, valor_anulado, quantidade, elemento, descricao, codif, favorecido, cargo, cpf_mascarado) "
                          "VALUES ('camara',2026,'y','2026-03-02',50000,0,'1','DIÁRIAS - CIVIL','viagem a Cuiabá','1','ANA SOUZA','VEREADOR','123.XXX.XXX-45')")
        vinculos.vincular(self.conn, "camara", self.csv); cam.derivar_verba(self.conn, "camara", 2026); self.conn.commit()
        with tempfile.TemporaryDirectory() as out:
            pc.publicar_camara(self.conn, Path(out))
            comp = {c["nome"]: c for c in json.loads((Path(out) / "camara" / "comparativo.json").read_text())["2026"]}
            self.assertEqual((comp["ANA SOUZA"]["meses"], comp["BRUNO LIMA"]["meses"]), (4, 2))
            self.assertEqual(comp["ANA SOUZA"]["verba"], 1668000); self.assertEqual(comp["ANA SOUZA"]["verba_mes"], 417000)   # mesma fórmula: total ÷ meses de folha
            self.assertEqual(comp["BRUNO LIMA"]["verba_mes"], 417000)
            self.assertEqual(comp["ANA SOUZA"]["diarias"], 50000)
            d = json.loads((Path(out) / "camara" / "diarias.json").read_text())["2026"]
            texto = json.dumps(d, ensure_ascii=False)
            self.assertNotIn("SECRETA", texto); self.assertNotIn("SOLITARIA", texto)       # nomes de não vereadores nunca saem
            cargos = {g["cargo"]: g["pessoas"] for g in d["servidores"]["por_cargo"]}
            self.assertEqual(cargos, {"ASSISTENTE": 3})                                     # cargo com 1 pessoa não aparece sozinho
            self.assertEqual(d["vereadores"]["valor"], 50000)
            v = json.loads((Path(out) / "camara" / "verba.json").read_text())
            self.assertFalse(v["detalhamento"]["disponivel"])
            self.assertEqual(v["anos"]["2026"]["total_verba"], 2502000)


if __name__ == "__main__":
    unittest.main()


class RegrasDescobertas(Base):
    def test_suplente_conta_como_vereador_e_assessor_nao(self):
        self.assertTrue(cam.eh_vereador("VEREADOR SUPLENTE"))
        self.assertFalse(cam.eh_vereador("ASSESSOR DE VEREADOR")); self.assertFalse(cam.eh_vereador("VEREADORIA"))

    def _folha(self, vid, meses_proventos, ano=2026, cargo="VEREADOR"):
        for m, p in meses_proventos:
            self.conn.execute("INSERT INTO vereador_folha VALUES (?,?,?,?,?,?,?,?,?)", (vid, ano, m, cargo, "Eletivo", "2025-01-01", p, 0, 1))

    def test_mes_sem_proventos_nao_conta_como_mes_de_exercicio(self):
        a = self.vereador("ANA SOUZA", "123.XXX.XXX-45")
        self._folha(a, [(1, 1000), (2, 0), (3, 1000)])
        self.forn("1", "ANA SOUZA", "123.XXX.XXX-45"); self.emp("p", "1", "x", 1, elemento="39")
        vinculos.vincular(self.conn, "camara", self.csv)
        with tempfile.TemporaryDirectory() as out:
            pc.publicar_camara(self.conn, Path(out))
            c = json.loads((Path(out) / "camara" / "comparativo.json").read_text())["2026"][0]
            f = json.loads((Path(out) / "camara" / "vereadores.json").read_text())["anos"]["2026"][0]
        self.assertEqual(c["meses"], 2); self.assertEqual(f["meses_sem_proventos"], [2]); self.assertEqual(c["proventos_mes"], 1000)

    def test_vinculo_so_vale_no_ano_em_que_foi_vereador(self):
        a = self.vereador("ANA SOUZA", "123.XXX.XXX-45"); self.forn("1", "ANA SOUZA", "123.XXX.XXX-45")
        self._folha(a, [(1, 1000)], ano=2026)                      # vereadora só em 2026
        self.emp("x", "1", "VERBA INDENIZATÓRIA REF: 01/2024", 834000, data="2024-02-01", ano=2024)
        self.conn.execute("INSERT INTO diaria (entidade, exercicio, pkemp, data, valor, valor_anulado, quantidade, elemento, descricao, codif, favorecido, cargo, cpf_mascarado) "
                          "VALUES ('camara',2024,'d','2024-03-01',400000,0,'1','DIÁRIAS - CIVIL','viagem','1','ANA SOUZA','','123.XXX.XXX-45')")
        vinculos.vincular(self.conn, "camara", self.csv); cam.derivar_verba(self.conn, "camara", 2024)
        self.emp("w", "1", "x", 1, ano=2026, elemento="39"); self.conn.commit()
        with tempfile.TemporaryDirectory() as out:
            pc.publicar_camara(self.conn, Path(out))
            fichas = json.loads((Path(out) / "camara" / "vereadores.json").read_text())["anos"]
            verba = json.loads((Path(out) / "camara" / "verba.json").read_text())["anos"]["2024"]
            dia = json.loads((Path(out) / "camara" / "diarias.json").read_text())["2024"]
        self.assertEqual(fichas["2024"], [])                         # sem folha em 2024 = sem ficha em 2024
        self.assertEqual(verba["nao_vinculado"]["verba_pago"], 834000)
        self.assertEqual(dia["vereadores"]["valor"], 0)
