import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ferramentas import Executor  # noqa: E402
from modelos import ModeloAPI, ModeloLocal  # noqa: E402


class TestExecutor(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())
        self.pedidos = []

    def executor(self, resposta):
        return Executor(lambda acao: self.pedidos.append(acao) or resposta)

    def test_acao_simples_nao_pede_confirmacao(self):
        r, erro = self.executor(False)("criar_pasta", {"caminho": str(self.pasta / "nova")})
        self.assertFalse(erro)
        self.assertTrue((self.pasta / "nova").is_dir())
        self.assertEqual(self.pedidos, [])

    def test_acao_sensivel_recusada_nao_executa(self):
        alvo = self.pasta / "a.txt"
        alvo.write_text("oi")
        r, _ = self.executor(False)("apagar", {"caminho": str(alvo)})
        self.assertTrue(alvo.exists())
        self.assertIn("não autorizou", r)
        self.assertEqual(len(self.pedidos), 1)

    def test_acao_sensivel_autorizada(self):
        ex = self.executor(True)
        ex("escrever_arquivo", {"caminho": str(self.pasta / "b.txt"), "conteudo": "olá"})
        ex("mover", {"origem": str(self.pasta / "b.txt"), "destino": str(self.pasta / "c.txt")})
        self.assertEqual((self.pasta / "c.txt").read_text(encoding="utf-8"), "olá")
        ex("apagar", {"caminho": str(self.pasta / "c.txt")})
        self.assertFalse((self.pasta / "c.txt").exists())

    def test_sem_confirmacao_configurada(self):
        ex = Executor(lambda a: self.fail("não devia perguntar"), pedir_confirmacao=False)
        r, erro = ex("executar_comando", {"comando": "echo oi"})
        self.assertFalse(erro)
        self.assertIn("oi", r)

    def test_erros_voltam_como_texto(self):
        ex = self.executor(True)
        self.assertTrue(ex("ler_arquivo", {"caminho": str(self.pasta / "nao_existe")})[1])
        self.assertTrue(ex("apagar", {})[1])
        self.assertTrue(ex("formatar_disco", {})[1])


class TestLacoDeFerramentas(unittest.TestCase):
    def test_local(self):
        m = ModeloLocal()
        respostas = iter([
            {"role": "assistant", "content": "",
             "tool_calls": [{"function": {"name": "listar_arquivos", "arguments": {"pasta": "."}}}]},
            {"role": "assistant", "content": "Pronto."},
        ])
        m._chat = lambda sistema, hist: next(respostas)
        chamadas = []
        hist = []
        r = m.conversar("s", hist, "liste", lambda n, a: chamadas.append((n, a)) or ("ok", False))
        self.assertEqual(r, "Pronto.")
        self.assertEqual(chamadas, [("listar_arquivos", {"pasta": "."})])
        self.assertEqual(hist[2]["role"], "tool")

    def test_api(self):
        m = ModeloAPI()
        respostas = iter([
            NS(stop_reason="tool_use",
               content=[NS(type="tool_use", id="t1", name="abrir", input={"alvo": "notepad"})]),
            NS(stop_reason="end_turn", content=[NS(type="text", text="Abri o Bloco de Notas.")]),
        ])
        m._chat = lambda sistema, hist: next(respostas)
        hist = []
        r = m.conversar("s", hist, "abre o bloco de notas", lambda n, a: ("Abri", False))
        self.assertEqual(r, "Abri o Bloco de Notas.")
        self.assertEqual(hist[2]["content"][0]["tool_use_id"], "t1")
        self.assertEqual([h["role"] for h in hist], ["user", "assistant", "user", "assistant"])


if __name__ == "__main__":
    unittest.main()
