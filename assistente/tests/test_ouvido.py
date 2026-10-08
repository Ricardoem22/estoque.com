import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ouvido import DetectorDeFala, extrair_chamado  # noqa: E402


def rodar(volumes, **kw):
    d = DetectorDeFala(ruido=0.005, **kw)
    estados = [d.bloco(v) for v in volumes]
    return estados


class TestDetector(unittest.TestCase):
    def test_ninguem_fala(self):
        estados = rodar([0.001] * 100, espera_max=1.0)
        self.assertEqual(estados[9], "nada")

    def test_fala_e_para(self):
        estados = rodar([0.001] * 5 + [0.2] * 10 + [0.001] * 20, silencio_fim=0.5)
        self.assertEqual(estados[5], "gravando")
        self.assertEqual(estados.index("fim"), 5 + 10 + 4)

    def test_pausa_curta_nao_encerra(self):
        estados = rodar([0.2] * 5 + [0.001] * 3 + [0.2] * 5 + [0.001] * 20, silencio_fim=0.5)
        self.assertEqual(estados.index("fim"), 5 + 3 + 5 + 4)

    def test_limite_de_tempo(self):
        estados = rodar([0.2] * 300, fala_max=2.0)
        self.assertEqual(estados.index("fim"), 19)


    def test_espera_infinita(self):
        estados = rodar([0.001] * 500, espera_max=None)
        self.assertNotIn("nada", estados)


class TestChamado(unittest.TestCase):
    def test_variacoes_do_nome(self):
        casos = {
            "Jarvis, que horas são?": "que horas são",
            "Ei Jarves abra o bloco de notas": "abra o bloco de notas",
            "jar vis, liga a luz": "liga a luz",
            "Járvis": "",
            "Javis, tudo bem?": "tudo bem",
        }
        for frase, pedido in casos.items():
            self.assertEqual(extrair_chamado(frase), (True, pedido), frase)

    def test_conversa_sem_nome_e_ignorada(self):
        for frase in ["Vamos jantar mais tarde?", "O carro está na garagem", "Obrigado"]:
            self.assertFalse(extrair_chamado(frase)[0], frase)

    def test_outro_nome(self):
        self.assertEqual(extrair_chamado("Friday, liga a TV", "Friday"), (True, "liga a TV"))


if __name__ == "__main__":
    unittest.main()
