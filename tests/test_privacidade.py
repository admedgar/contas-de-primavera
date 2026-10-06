import json
import tempfile
import unittest
from pathlib import Path

from contas import config, db, publicar


def montar(tmp):
    conn = db.conectar(Path(tmp) / "t.sqlite")
    forn = [("1", "MARIA PRESTADORA", "111.XXX.XXX-11", "cpf_mascarado"), ("2", "JOAO BENEFICIARIO", "222.XXX.XXX-22", "cpf_mascarado"),
            ("3", "JOAO ME", "11.111.111/0001-11", "cnpj"), ("4", "EMPRESA LTDA", "22.222.222/0001-22", "cnpj"),
            ("5", "VEREADOR TESTE", "333.XXX.XXX-33", "cpf_mascarado")]
    conn.executemany("INSERT INTO fornecedor VALUES ('camara',?,?,?,?)", forn)
    linhas = [("p1", "1", "39", "SERVICO CONTRATADO"), ("p2", "2", "48", "AUXILIO A FAMILIA DE FULANO"), ("p3", "3", "14", "VIAGEM DE JOAO"),
              ("p4", "4", "39", "EMPRESA"), ("p5", "5", "14", "VIAGEM DO VEREADOR"), ("p6", "4", "14", "EMPRESA COM DIARIA")]
    for pk, cod, el, h in linhas:
        conn.execute("INSERT INTO empenho VALUES ('camara',2026,?,?, 'OR',NULL,?, '2026-02-01','0101','010101','Legislativa','','','',?,'x','','',?,100,100,100)", (pk, pk, cod, el, h))
    conn.execute("INSERT INTO vereador (id, nome, nome_norm, cpf_mascarado) VALUES (1,'VEREADOR TESTE','VEREADOR TESTE','333.XXX.XXX-33')")
    conn.execute("INSERT INTO vereador_vinculo VALUES ('5',1,'confirmado','regra',NULL)")
    conn.commit()
    return conn


class Privacidade(unittest.TestCase):
    def roda(self, politica):
        antes = config.PF_POLITICA; config.PF_POLITICA = politica
        self.addCleanup(setattr, config, "PF_POLITICA", antes)
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        conn = montar(tmp.name); self.addCleanup(conn.close)
        publicar.publicar(conn, "camara", Path(tmp.name) / "out")
        d = Path(tmp.name) / "out" / "camara"
        E = json.loads((d / "empenhos_2026.json").read_text())["linhas"]
        F = json.loads((d / "fornecedores_2026.json").read_text())
        return {l[0]: l for l in E}, F, "".join(p.read_text() for p in d.glob("*.json"))

    def test_beneficiarios_omite_so_o_que_deve(self):
        E, F, texto = self.roda("beneficiarios")
        self.assertEqual(E["p1"][3], "MARIA PRESTADORA")           # pessoa física prestando serviço (el. 39): visível
        self.assertEqual(E["p4"][3], "EMPRESA LTDA")                # empresa: visível
        self.assertEqual(E["p5"][3], "VEREADOR TESTE")              # vereador confirmado: nominal
        for pk in ("p2", "p3", "p6"):                               # auxílio (48) e diárias (14), com CPF ou CNPJ
            self.assertEqual(E[pk][3], publicar.ROTULO_PF); self.assertEqual(E[pk][4], ""); self.assertEqual(E[pk][11], "")
        self.assertNotIn("FAMILIA DE FULANO", texto); self.assertNotIn("JOAO BENEFICIARIO", texto); self.assertNotIn("JOAO ME", texto)
        self.assertNotIn("EMPRESA COM DIARIA", texto)

    def test_totais_nao_mudam(self):
        E, F, _ = self.roda("beneficiarios")
        self.assertEqual(sum(l[8] for l in E.values()), 600)
        self.assertEqual(sum(l[3] for l in F["linhas"]), 600)       # inclui a linha agregada de pessoas omitidas
        omitida = [l for l in F["linhas"] if "omitido" in l[0]][0]
        self.assertEqual(omitida[3], 300)                           # p2, p3 (14) e a parte de diária da empresa (p6)? -> p2+p3+p6 = 300

    def test_empresa_mantem_sua_parte_nao_diaria(self):
        _, F, _ = self.roda("beneficiarios")
        emp = [l for l in F["linhas"] if l[0] == "EMPRESA LTDA"][0]
        self.assertEqual(emp[3], 100)                               # só o empenho do elemento 39 fica na linha da empresa

    def test_politica_portal_publica_tudo(self):
        E, _, texto = self.roda("portal")
        self.assertEqual(E["p2"][3], "JOAO BENEFICIARIO"); self.assertIn("FAMILIA DE FULANO", texto)


if __name__ == "__main__":
    unittest.main()
