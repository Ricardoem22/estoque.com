import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ouvido import DetectorDeFala  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
