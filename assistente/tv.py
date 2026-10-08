"""Controle das TVs pela rede de casa: LG (webOS), Samsung (Tizen) e TVs com Roku (ex.: Philips Roku TV).

As TVs são encontradas automaticamente (/tv procurar) e ficam guardadas na memória local.
Na primeira vez, LG e Samsung mostram um aviso na tela da TV pedindo para permitir o Jarvis.
"""
import asyncio
import difflib
import platform
import re
import socket
import subprocess
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from ferramentas import FERRAMENTAS, POR_NOME, Ferramenta
from memoria import Memoria, pasta_padrao

ACOES = ["ligar", "desligar", "volume_mais", "volume_menos", "volume", "mudo", "canal_mais", "canal_menos",
         "abrir", "pausar", "continuar", "inicio", "voltar"]

_memoria: Memoria | None = None


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").strip()


# ---------------------------------------------------------------- descoberta

def classificar(resposta: str, descricao: str = "") -> str | None:
    """Descobre a marca pela resposta SSDP e pela descrição do aparelho."""
    tudo = _norm(resposta + " " + descricao)
    if "roku" in tudo:
        return "roku"
    if "webos" in tudo or "lge" in tudo or "lg electronics" in tudo:
        return "lg"
    if "samsung" in tudo and ("tv" in tudo or "remotecontrolreceiver" in tudo):
        return "samsung"
    if "android" in tudo or "google tv" in tudo:
        return "android"
    return None


def _cabecalho(resposta: str, nome: str) -> str:
    m = re.search(rf"(?im)^{nome}:\s*(.+)$", resposta)
    return m.group(1).strip() if m else ""


def _descricao(local: str) -> tuple[str, str]:
    """Lê o XML de descrição do aparelho: (texto para classificar, nome amigável)."""
    try:
        with urllib.request.urlopen(local, timeout=2) as r:
            xml = r.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError):
        return "", ""
    nome = re.search(r"<friendlyName>(.*?)</friendlyName>", xml, re.S)
    partes = re.findall(r"<(?:manufacturer|modelName|modelDescription)>(.*?)</", xml, re.S)
    return " ".join(partes), (nome.group(1).strip() if nome else "")


def mac_de(ip: str) -> str:
    """Pega o endereço físico (MAC) da TV pela tabela ARP, para poder ligá-la pela rede."""
    try:
        saida = subprocess.run(["arp", "-a", ip] if platform.system() == "Windows" else ["arp", "-n", ip],
                               capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = re.search(r"([0-9a-fA-F]{2}[-:]){5}[0-9a-fA-F]{2}", saida)
    return m.group(0).replace("-", ":").lower() if m else ""


def procurar(segundos: float = 4.0) -> list[dict]:
    """Procura TVs na rede local via SSDP (o mesmo jeito que os apps de controle remoto usam)."""
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\n"
           "MX: 2\r\nST: ssdp:all\r\n\r\n").encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.settimeout(0.5)
    respostas: dict[str, list[str]] = {}
    try:
        for _ in range(2):
            s.sendto(msg, ("239.255.255.250", 1900))
        fim = time.monotonic() + segundos
        while time.monotonic() < fim:
            try:
                dados, (ip, _) = s.recvfrom(4096)
            except socket.timeout:
                continue
            respostas.setdefault(ip, []).append(dados.decode("utf-8", errors="replace"))
    finally:
        s.close()

    achadas = []
    for ip, lista in respostas.items():
        texto = "\n".join(lista)
        marca = classificar(texto)
        nome = ""
        if marca is None or marca == "android":
            for local in {_cabecalho(r, "LOCATION") for r in lista} - {""}:
                desc, nome = _descricao(local)
                marca = classificar(texto, desc) or marca
                if marca and marca != "android":
                    break
        if marca:
            achadas.append({"ip": ip, "marca": marca, "modelo": nome})
    return achadas


# ---------------------------------------------------------------- ligar pela rede

def wake_on_lan(mac: str) -> None:
    bruto = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    pacote = b"\xff" * 6 + bruto * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for porta in (9, 7):
            s.sendto(pacote, ("255.255.255.255", porta))


def _ligar(tv: dict) -> str:
    if not tv.get("mac"):
        return ("Não sei o endereço físico (MAC) dessa TV para ligá-la pela rede. "
                "Com a TV ligada, rode /tv procurar de novo.")
    wake_on_lan(tv["mac"])
    return ("Mandei o sinal para ligar. Se não ligar, ative na TV a opção de ligar pela rede "
            "(LG: 'Ligar via Wi-Fi'; Samsung: 'Ligar com dispositivo móvel').")


# ---------------------------------------------------------------- Roku (Philips Roku TV, TCL etc.)

ROKU_TECLAS = {"ligar": "PowerOn", "desligar": "PowerOff", "volume_mais": "VolumeUp",
               "volume_menos": "VolumeDown", "mudo": "VolumeMute", "canal_mais": "ChannelUp",
               "canal_menos": "ChannelDown", "pausar": "Play", "continuar": "Play",
               "inicio": "Home", "voltar": "Back"}


def _roku_post(tv: dict, caminho: str) -> None:
    req = urllib.request.Request(f"http://{tv['ip']}:8060/{caminho}", data=b"", method="POST")
    urllib.request.urlopen(req, timeout=5).close()


def roku(tv: dict, acao: str, valor: str) -> str:
    if acao == "abrir":
        with urllib.request.urlopen(f"http://{tv['ip']}:8060/query/apps", timeout=5) as r:
            apps = {a.text or "": a.get("id") for a in ET.fromstring(r.read()).iter("app")}
        nome = melhor(valor, list(apps))
        if not nome:
            return f"Não achei o app '{valor}' nessa TV. Apps instalados: {', '.join(apps)}"
        _roku_post(tv, f"launch/{apps[nome]}")
        return f"Abri o {nome}."
    if acao == "volume":
        return "Na Roku não dá para escolher um número de volume; use volume_mais ou volume_menos."
    if acao in ("volume_mais", "volume_menos") and valor.isdigit():
        for _ in range(min(int(valor), 30)):
            _roku_post(tv, f"keypress/{ROKU_TECLAS[acao]}")
            time.sleep(0.15)
        return "Pronto."
    if acao == "ligar" and tv.get("mac"):
        wake_on_lan(tv["mac"])  # algumas Roku dormem o Wi-Fi; o pacote ajuda a acordar
    _roku_post(tv, f"keypress/{ROKU_TECLAS[acao]}")
    return "Pronto."


# ---------------------------------------------------------------- LG webOS

async def _lg_async(tv: dict, acao: str, valor: str) -> str:
    from aiowebostv import WebOsClient

    cliente = WebOsClient(tv["ip"], tv.get("chave"), connect_timeout=8)
    if not tv.get("chave"):
        print("(olhe a TV: aceite o pedido de conexão do Jarvis)")
    await cliente.connect()
    try:
        if cliente.client_key and cliente.client_key != tv.get("chave"):
            tv["chave"] = cliente.client_key
            salvar()
        if acao == "desligar":
            await cliente.power_off()
        elif acao in ("volume_mais", "volume_menos"):
            for _ in range(min(int(valor), 30) if valor.isdigit() else 1):
                await (cliente.volume_up() if acao == "volume_mais" else cliente.volume_down())
        elif acao == "volume":
            await cliente.set_volume(int(valor))
        elif acao == "mudo":
            await cliente.set_mute(not await cliente.get_muted())
        elif acao == "canal_mais":
            await cliente.channel_up()
        elif acao == "canal_menos":
            await cliente.channel_down()
        elif acao == "pausar":
            await cliente.pause()
        elif acao == "continuar":
            await cliente.play()
        elif acao == "inicio":
            await cliente.button("HOME")
        elif acao == "voltar":
            await cliente.button("BACK")
        elif acao == "abrir":
            apps = await cliente.get_apps() or []
            lista = apps.values() if isinstance(apps, dict) else apps
            por_nome = {a.get("title", ""): a.get("id") for a in lista}
            nome = melhor(valor, list(por_nome))
            if not nome:
                return f"Não achei o app '{valor}' nessa TV. Apps: {', '.join(por_nome)}"
            await cliente.launch_app(por_nome[nome])
            return f"Abri o {nome}."
        return "Pronto."
    finally:
        await cliente.disconnect()


def lg(tv: dict, acao: str, valor: str) -> str:
    if acao == "ligar":
        return _ligar(tv)
    return asyncio.run(_lg_async(tv, acao, valor))


# ---------------------------------------------------------------- Samsung Tizen

SAMSUNG_TECLAS = {"desligar": "KEY_POWER", "volume_mais": "KEY_VOLUP", "volume_menos": "KEY_VOLDOWN",
                  "mudo": "KEY_MUTE", "canal_mais": "KEY_CHUP", "canal_menos": "KEY_CHDOWN",
                  "pausar": "KEY_PAUSE", "continuar": "KEY_PLAY", "inicio": "KEY_HOME", "voltar": "KEY_RETURN"}
SAMSUNG_APPS = {"YouTube": "111299001912", "Netflix": "3201907018807", "Prime Video": "3201910019365"}


def samsung(tv: dict, acao: str, valor: str) -> str:
    if acao == "ligar":
        return _ligar(tv)
    if acao == "volume":
        return "Na Samsung não dá para escolher um número de volume; use volume_mais ou volume_menos."
    from samsungtvws import SamsungTVWS

    token = pasta_padrao() / f"samsung_{tv['ip'].replace('.', '_')}.txt"
    token.parent.mkdir(parents=True, exist_ok=True)
    if not token.exists():
        print("(olhe a TV: permita a conexão do Jarvis)")
    remoto = SamsungTVWS(host=tv["ip"], port=8002, token_file=str(token), name="Jarvis", timeout=15)
    try:
        if acao == "abrir":
            apps = {}
            try:
                apps = {a.get("name", ""): a.get("appId") for a in (remoto.app_list() or [])}
            except Exception:
                pass  # alguns modelos não informam a lista
            apps = apps or SAMSUNG_APPS
            nome = melhor(valor, list(apps))
            if not nome:
                return f"Não achei o app '{valor}'. Conheço: {', '.join(apps)}"
            remoto.run_app(apps[nome])
            return f"Abri o {nome}."
        vezes = min(int(valor), 30) if acao.startswith("volume_") and valor.isdigit() else 1
        for _ in range(vezes):
            remoto.send_key(SAMSUNG_TECLAS[acao])
        return "Pronto."
    finally:
        remoto.close()


DRIVERS = {"roku": roku, "lg": lg, "samsung": samsung}


# ---------------------------------------------------------------- lista de TVs

def melhor(pedido: str, opcoes: list[str]) -> str | None:
    """Escolhe a opção mais parecida com o pedido ('youtube' -> 'YouTube', 'sala' -> 'TV da sala')."""
    p = _norm(pedido)
    if not p or not opcoes:
        return None
    for o in opcoes:
        if p == _norm(o):
            return o
    contem = [o for o in opcoes if p in _norm(o) or (_norm(o) and _norm(o) in p)]
    if contem:
        return min(contem, key=len)
    perto = difflib.get_close_matches(p, [_norm(o) for o in opcoes], n=1, cutoff=0.6)
    return next(o for o in opcoes if _norm(o) == perto[0]) if perto else None


def tvs() -> list[dict]:
    return _memoria.get("tvs", []) if _memoria else []


def salvar() -> None:
    if _memoria:
        _memoria.set("tvs", tvs())


def escolher_tv(nome: str) -> dict | None:
    lista = tvs()
    if len(lista) == 1 and not nome:
        return lista[0]
    rotulos = {f"{t['nome']} {t['marca']}": t for t in lista}
    achou = melhor(nome, list(rotulos))
    return rotulos[achou] if achou else (lista[0] if len(lista) == 1 else None)


def adicionar(achadas: list[dict]) -> list[dict]:
    """Junta as TVs encontradas com as já salvas (pelo IP), dando nomes a novas."""
    lista = tvs()
    por_ip = {t["ip"]: t for t in lista}
    novas = []
    for a in achadas:
        if a["marca"] not in DRIVERS:
            continue
        if a["ip"] in por_ip:
            por_ip[a["ip"]]["mac"] = mac_de(a["ip"]) or por_ip[a["ip"]].get("mac", "")
            continue
        rotulo = {"lg": "LG", "samsung": "Samsung", "roku": "Philips"}[a["marca"]]
        nome = f"TV {rotulo}"
        n = 2
        while any(t["nome"] == nome for t in lista):
            nome, n = f"TV {rotulo} {n}", n + 1
        tv = {"nome": nome, "marca": a["marca"], "ip": a["ip"], "mac": mac_de(a["ip"]), "modelo": a.get("modelo", "")}
        lista.append(tv)
        novas.append(tv)
    if _memoria:
        _memoria.set("tvs", lista)
    return novas


def descrever() -> str:
    lista = tvs()
    if not lista:
        return "Nenhuma TV cadastrada. Use /tv procurar com as TVs ligadas."
    return "\n".join(f"{i + 1}. {t['nome']} ({t['marca']}, {t['ip']})" for i, t in enumerate(lista))


# ---------------------------------------------------------------- ferramentas para a IA

def tv_listar() -> str:
    return descrever()


def tv_controlar(tv: str, acao: str, valor: str) -> str:
    alvo = escolher_tv(tv)
    if alvo is None:
        return f"Não sei qual TV é '{tv}'. TVs cadastradas:\n{descrever()}"
    if acao not in ACOES:
        return f"Ação inválida. Use uma destas: {', '.join(ACOES)}"
    try:
        return f"{alvo['nome']}: " + DRIVERS[alvo["marca"]](alvo, acao, valor.strip())
    except ImportError:
        return "Falta instalar o suporte a TVs: clique em Atualizar Jarvis."
    except (OSError, urllib.error.URLError, TimeoutError, asyncio.TimeoutError) as e:
        return (f"Não consegui falar com a {alvo['nome']} ({alvo['ip']}): {e}. "
                "Ela está ligada e na mesma rede Wi-Fi? Se o IP mudou, rode /tv procurar.")


NOVAS = [
    Ferramenta("tv_listar", "Lista as TVs da casa que eu sei controlar.", {}, tv_listar),
    Ferramenta("tv_controlar",
               "Controla uma TV da casa. acao: " + ", ".join(ACOES) + ". "
               "valor: o app em 'abrir' (ex.: YouTube, Netflix, Globoplay), o número em 'volume' "
               "ou quantas vezes em volume_mais/volume_menos; senão, texto vazio.",
               {"tv": "nome ou marca da TV (ex.: 'sala', 'LG'); vazio se só houver uma",
                "acao": "uma das ações listadas", "valor": "complemento da ação ou vazio"},
               tv_controlar),
]


def registrar(memoria: Memoria) -> None:
    global _memoria
    _memoria = memoria
    for f in NOVAS:
        if f.nome not in POR_NOME:
            FERRAMENTAS.append(f)
            POR_NOME[f.nome] = f
