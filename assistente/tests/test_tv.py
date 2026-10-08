import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tv  # noqa: E402
from memoria import Memoria  # noqa: E402


class FakeRoku(BaseHTTPRequestHandler):
    pedidos = []

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'<apps><app id="837">YouTube</app><app id="12">Netflix</app>'
                         b'<app id="99">Globoplay</app></apps>')

    def do_POST(self):
        FakeRoku.pedidos.append(self.path)
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


class Base(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())
        tv.registrar(Memoria(self.pasta))
        mock.patch.object(tv, "mac_de", return_value="aa:bb:cc:dd:ee:ff").start()
        mock.patch.object(tv, "pasta_padrao", return_value=self.pasta).start()
        self.addCleanup(mock.patch.stopall)


class TestBasico(Base):
    def test_classificar(self):
        self.assertEqual(tv.classificar("SERVER: Roku/12.0 UPnP/1.0\nST: roku:ecp"), "roku")
        self.assertEqual(tv.classificar("SERVER: WebOS/4.1.0 UPnP/1.0"), "lg")
        self.assertEqual(tv.classificar("ST: urn:samsung.com:device:RemoteControlReceiver:1"), "samsung")
        self.assertEqual(tv.classificar("SERVER: Linux", "Philips Android TV"), "android")
        self.assertIsNone(tv.classificar("SERVER: Linux UPnP/1.0 roteador"))

    def test_melhor(self):
        self.assertEqual(tv.melhor("youtube", ["YouTube", "YouTube Kids", "Netflix"]), "YouTube")
        self.assertEqual(tv.melhor("netflics", ["YouTube", "Netflix"]), "Netflix")
        self.assertIsNone(tv.melhor("spotify", ["YouTube", "Netflix"]))

    def test_adicionar_nomeia_e_escolhe(self):
        tv.adicionar([{"ip": "10.0.0.2", "marca": "lg"}, {"ip": "10.0.0.3", "marca": "samsung"},
                      {"ip": "10.0.0.4", "marca": "lg"}, {"ip": "10.0.0.9", "marca": "android"}])
        self.assertEqual([t["nome"] for t in tv.tvs()], ["TV LG", "TV Samsung", "TV LG 2"])
        self.assertEqual(tv.escolher_tv("samsung")["ip"], "10.0.0.3")
        tv.tvs()[0]["nome"] = "TV da sala"
        self.assertEqual(tv.escolher_tv("sala")["ip"], "10.0.0.2")
        tv.adicionar([{"ip": "10.0.0.2", "marca": "lg"}])  # repetida não duplica
        self.assertEqual(len(tv.tvs()), 3)

    def test_wake_on_lan(self):
        enviados = []
        falso = mock.MagicMock()
        falso.__enter__.return_value.sendto = lambda dados, destino: enviados.append(dados)
        with mock.patch.object(tv.socket, "socket", return_value=falso):
            tv.wake_on_lan("aa:bb:cc:dd:ee:ff")
        self.assertEqual(enviados[0], b"\xff" * 6 + bytes.fromhex("aabbccddeeff") * 16)

    def test_tv_desconhecida(self):
        self.assertIn("Nenhuma TV", tv.tv_controlar("sala", "desligar", ""))


class TestRoku(Base):
    def setUp(self):
        super().setUp()
        self.srv = HTTPServer(("127.0.0.1", 0), FakeRoku)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.shutdown)
        porta = self.srv.server_address[1]
        tv.adicionar([{"ip": "127.0.0.1", "marca": "roku"}])
        FakeRoku.pedidos = []
        real = tv.urllib.request.urlopen
        mock.patch.object(tv.urllib.request, "urlopen",
                          side_effect=lambda u, **k: real(
                              u.replace(":8060", f":{porta}") if isinstance(u, str)
                              else tv.urllib.request.Request(u.full_url.replace(":8060", f":{porta}"),
                                                             data=u.data, method=u.get_method()), **k)).start()

    def test_teclas_e_apps(self):
        self.assertIn("Pronto", tv.tv_controlar("", "volume_mais", "3"))
        self.assertIn("Abri o Globoplay", tv.tv_controlar("philips", "abrir", "globo play"))
        tv.tv_controlar("", "desligar", "")
        self.assertEqual(FakeRoku.pedidos, ["/keypress/VolumeUp"] * 3 + ["/launch/99", "/keypress/PowerOff"])

    def test_tv_fora_do_ar(self):
        tv.tvs()[0]["ip"] = "127.0.0.1:1"
        self.assertIn("Não consegui falar", tv.tv_controlar("", "mudo", ""))


class TestLGeSamsung(Base):
    def test_lg(self):
        chamadas = []

        class Cliente:
            def __init__(self, host, key, connect_timeout=2):
                self.client_key = key or "CHAVE-NOVA"

            async def connect(self):
                chamadas.append("connect")

            async def disconnect(self):
                pass

            async def set_volume(self, n):
                chamadas.append(("volume", n))

            async def get_apps(self):
                return [{"id": "youtube.leanback.v4", "title": "YouTube"}]

            async def launch_app(self, app):
                chamadas.append(("app", app))

            async def power_off(self):
                chamadas.append("off")

        with mock.patch.dict(sys.modules, {"aiowebostv": types.SimpleNamespace(WebOsClient=Cliente)}):
            tv.adicionar([{"ip": "10.0.0.2", "marca": "lg"}])
            tv.tv_controlar("lg", "volume", "15")
            self.assertEqual(tv.tvs()[0]["chave"], "CHAVE-NOVA")  # guardou o pareamento
            self.assertIn("Abri o YouTube", tv.tv_controlar("lg", "abrir", "youtube"))
            tv.tv_controlar("lg", "desligar", "")
        self.assertIn(("volume", 15), chamadas)
        self.assertIn(("app", "youtube.leanback.v4"), chamadas)
        self.assertIn("off", chamadas)

    def test_samsung(self):
        teclas = []

        class Remoto:
            def __init__(self, **kw):
                pass

            def send_key(self, k):
                teclas.append(k)

            def app_list(self):
                raise RuntimeError("não suportado")

            def run_app(self, app):
                teclas.append(app)

            def close(self):
                pass

        with mock.patch.dict(sys.modules, {"samsungtvws": types.SimpleNamespace(SamsungTVWS=Remoto)}):
            tv.adicionar([{"ip": "10.0.0.3", "marca": "samsung"}])
            tv.tv_controlar("", "volume_menos", "2")
            self.assertIn("Netflix", tv.tv_controlar("", "abrir", "netflix"))
        self.assertEqual(teclas, ["KEY_VOLDOWN", "KEY_VOLDOWN", "3201907018807"])

    def test_ligar_usa_wake_on_lan(self):
        tv.adicionar([{"ip": "10.0.0.3", "marca": "samsung"}])
        with mock.patch.object(tv, "wake_on_lan") as wol:
            self.assertIn("ligar", tv.tv_controlar("", "ligar", ""))
        wol.assert_called_once_with("aa:bb:cc:dd:ee:ff")


if __name__ == "__main__":
    unittest.main()
