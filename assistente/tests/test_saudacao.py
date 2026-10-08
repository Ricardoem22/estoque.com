import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memoria import Memoria  # noqa: E402
from saudacao import saudar  # noqa: E402


class TestSaudacao(unittest.TestCase):
    def h(self, hora):
        return datetime(2026, 1, 1, hora, 0)

    def test_periodos(self):
        self.assertEqual(saudar("Ana", agora=self.h(5)), "Bom dia, Ana!")
        self.assertEqual(saudar("Ana", agora=self.h(11)), "Bom dia, Ana!")
        self.assertEqual(saudar("Ana", agora=self.h(12)), "Boa tarde, Ana!")
        self.assertEqual(saudar("Ana", agora=self.h(17)), "Boa tarde, Ana!")
        self.assertEqual(saudar("Ana", agora=self.h(18)), "Boa noite, Ana!")
        self.assertEqual(saudar("Ana", agora=self.h(2)), "Boa noite, Ana!")

    def test_ingles_e_sem_nome(self):
        self.assertEqual(saudar("Ana", "en", self.h(9)), "Good morning, Ana!")
        self.assertEqual(saudar("", agora=self.h(20)), "Boa noite!")


class TestMemoria(unittest.TestCase):
    def test_salva_le_e_apaga(self):
        with tempfile.TemporaryDirectory() as pasta:
            m = Memoria(Path(pasta))
            m.set("nome", "Ana")
            m.lembrar("gosta de respostas curtas")
            de_novo = Memoria(Path(pasta))
            self.assertEqual(de_novo.get("nome"), "Ana")
            self.assertEqual(de_novo.get("fatos"), ["gosta de respostas curtas"])
            de_novo.apagar_tudo()
            self.assertEqual(Memoria(Path(pasta)).dados, {})


if __name__ == "__main__":
    unittest.main()
