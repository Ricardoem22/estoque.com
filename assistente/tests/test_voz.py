import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voz import Voz, limpar  # noqa: E402


class TestVoz(unittest.TestCase):
    def test_limpar_markdown(self):
        self.assertEqual(limpar("**Pronto!** Veja o [site](https://x.com)\n# Título"), "Pronto! Veja o site Título")

    def test_escolha_da_voz(self):
        v = Voz(ativa=False)
        nomes = ["Microsoft Zira Desktop - English (United States)",
                 "Microsoft Maria Desktop - Portuguese(Brazil)"]
        self.assertEqual(v._escolher(nomes), 1)  # sem Daniel, pega a em português
        self.assertEqual(v._escolher(nomes + ["Microsoft Daniel - Portuguese (Brazil)"]), 2)

    def test_desligada_nao_fala(self):
        Voz(ativa=False).falar("oi")  # não deve dar erro


if __name__ == "__main__":
    unittest.main()
