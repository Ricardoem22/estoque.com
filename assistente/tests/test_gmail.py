import base64
import email
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gmail  # noqa: E402


def b64(texto):
    return base64.urlsafe_b64encode(texto.encode()).decode().rstrip("=")


class FakeExec:
    def __init__(self, valor):
        self.valor = valor

    def execute(self):
        return self.valor


class FakeMensagens:
    def __init__(self):
        self.enviado = None

    def list(self, **kw):
        return FakeExec({"messages": [{"id": "a1"}]})

    def get(self, userId, id, format, **kw):
        return FakeExec({"id": id, "labelIds": ["UNREAD"], "snippet": "Seu boleto &amp; nota",
                         "payload": {"headers": [{"name": "From", "value": "Loja <l@x.com>"},
                                                 {"name": "Subject", "value": "Boleto"},
                                                 {"name": "Date", "value": "Thu, 8 Oct 2026"}],
                                     "mimeType": "text/plain", "body": {"data": b64("Vence dia 10.")}}})

    def send(self, userId, body):
        self.enviado = body
        return FakeExec({"id": "s1"})


class FakeServico:
    def __init__(self):
        self.msgs = FakeMensagens()

    def users(self):
        return self

    def messages(self):
        return self.msgs


class TestGmail(unittest.TestCase):
    def test_corpo_prefere_texto_simples(self):
        parte = {"mimeType": "multipart/alternative", "parts": [
            {"mimeType": "text/html", "body": {"data": b64("<p>Olá <b>mundo</b></p>")}},
            {"mimeType": "text/plain", "body": {"data": b64("Olá mundo")}},
        ]}
        self.assertEqual(gmail.extrair_corpo(parte), "Olá mundo")

    def test_corpo_so_html(self):
        parte = {"mimeType": "text/html",
                 "body": {"data": b64("<style>x{}</style><p>Linha 1</p><p>Linha &amp; 2</p>")}}
        self.assertEqual(gmail.extrair_corpo(parte), "Linha 1\nLinha & 2")

    def test_mensagem_montada(self):
        raw = gmail.montar_mensagem("a@b.com", "Oi", "Olá, tudo bem?")["raw"]
        msg = email.message_from_bytes(base64.urlsafe_b64decode(raw))
        self.assertEqual(msg["To"], "a@b.com")
        self.assertEqual(msg.get_payload(decode=True).decode("utf-8"), "Olá, tudo bem?")

    def test_buscar_ler_enviar(self):
        fake = FakeServico()
        with mock.patch.object(gmail, "servico", return_value=fake):
            r = gmail.buscar("is:unread")
            self.assertIn("id=a1 [NÃO LIDO]", r)
            self.assertIn("Seu boleto & nota", r)
            self.assertIn("Vence dia 10.", gmail.ler("a1"))
            self.assertIn("s1", gmail.enviar("a@b.com", "Oi", "corpo"))
            self.assertIn("raw", fake.msgs.enviado)

    def test_sem_credenciais_nao_registra(self):
        with mock.patch.object(gmail, "CREDENCIAIS", Path("/nao/existe.json")):
            self.assertIn("credentials.json", gmail.registrar())


if __name__ == "__main__":
    unittest.main()
