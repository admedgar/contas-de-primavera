import unittest

from contas.parsers import ano_2dig, centavos, data_iso, limpa, normaliza_nome, tipo_documento


class Centavos(unittest.TestCase):
    def test_formato_do_portal(self):
        self.assertEqual(centavos("31729665,47"), 3172966547)
        self.assertEqual(centavos("1867,73"), 186773)
        self.assertEqual(centavos("8340"), 834000)
        self.assertEqual(centavos("-0,12"), -12)
        self.assertEqual(centavos("-5740,81"), -574081)

    def test_vazio_e_traco(self):
        for v in (None, "", "  ", "-", "0"):
            self.assertEqual(centavos(v), 0)

    def test_casas_extras_arredondam(self):
        self.assertEqual(centavos("8690576,35999999"), 869057636)

    def test_milhar_e_ponto(self):
        self.assertEqual(centavos("1.234,56"), 123456)
        self.assertEqual(centavos("1.234"), 123400)       # ponto com 3 dígitos = milhar
        self.assertEqual(centavos("12.5"), 1250)           # ponto isolado = decimal

    def test_lixo_levanta_erro(self):
        with self.assertRaises(ValueError):
            centavos("abc")

    def test_soma_exata_sem_float(self):
        self.assertEqual(sum(centavos(x) for x in ["0,1"] * 10), 100)


class Datas(unittest.TestCase):
    def test_iso(self):
        self.assertEqual(data_iso("05/01/2026 00:00:00"), "2026-01-05")
        self.assertEqual(data_iso("31/12/2025"), "2025-12-31")
        self.assertIsNone(data_iso(""))
        self.assertIsNone(data_iso(None))

    def test_invalida(self):
        with self.assertRaises(ValueError):
            data_iso("2026-01-05")

    def test_ano_2_digitos(self):
        self.assertEqual(ano_2dig("26"), 2026)
        self.assertEqual(ano_2dig("2026"), 2026)


class Texto(unittest.TestCase):
    def test_normaliza_nome(self):
        self.assertEqual(normaliza_nome("  Sérgio  Rodrigues Gonçalves "), "SERGIO RODRIGUES GONCALVES")

    def test_tipo_documento(self):
        self.assertEqual(tipo_documento("29.979.036/0001-40"), "cnpj")
        self.assertEqual(tipo_documento("053.XXX.XXX-60"), "cpf_mascarado")
        self.assertEqual(tipo_documento("12345678901"), "outro")   # CPF puro NÃO é reconhecido nem tratado como mascarado

    def test_limpa(self):
        self.assertEqual(limpa("  a   b\n c "), "a b c")
        self.assertEqual(limpa("abcdef", 3), "abc")
        self.assertEqual(limpa(None), "")


if __name__ == "__main__":
    unittest.main()
