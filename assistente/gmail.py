"""Integração com o Gmail: buscar, ler e enviar e-mails da sua conta.

Precisa do arquivo credentials.json (veja o README). Na primeira vez, abre o
navegador para você autorizar; a autorização fica salva só no seu computador.
"""
import base64
import html
import re
from email.mime.text import MIMEText
from pathlib import Path

from ferramentas import FERRAMENTAS, POR_NOME, Ferramenta, _cortar
from memoria import pasta_padrao

ESCOPOS = ["https://www.googleapis.com/auth/gmail.modify"]  # ler, enviar, rascunhos (sem apagar de vez)
CREDENCIAIS = Path(__file__).with_name("credentials.json")


def _token() -> Path:
    return pasta_padrao() / "gmail_token.json"


def bibliotecas_instaladas() -> bool:
    try:
        import google.oauth2.credentials  # noqa: F401
        import google_auth_oauthlib.flow  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
        return True
    except ImportError:
        return False


_servico = None


def servico():
    """Conecta ao Gmail (abre o navegador para autorizar, se preciso)."""
    global _servico
    if _servico is not None:
        return _servico
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    cred = None
    if _token().exists():
        cred = Credentials.from_authorized_user_file(str(_token()), ESCOPOS)
    if not cred or not cred.valid:
        if cred and cred.expired and cred.refresh_token:
            cred.refresh(Request())
        else:
            print("(abrindo o navegador para você autorizar o acesso ao Gmail...)")
            cred = InstalledAppFlow.from_client_secrets_file(str(CREDENCIAIS), ESCOPOS).run_local_server(port=0)
        _token().parent.mkdir(parents=True, exist_ok=True)
        _token().write_text(cred.to_json(), encoding="utf-8")
    _servico = build("gmail", "v1", credentials=cred, cache_discovery=False)
    return _servico


def desconectar() -> None:
    global _servico
    _servico = None
    if _token().exists():
        _token().unlink()


# ---------- leitura das mensagens ----------

def _decodificar(dados: str) -> str:
    return base64.urlsafe_b64decode(dados + "=" * (-len(dados) % 4)).decode("utf-8", errors="replace")


def _sem_html(texto: str) -> str:
    texto = re.sub(r"(?is)<(script|style).*?</\1>", "", texto)
    texto = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", texto)
    texto = html.unescape(re.sub(r"<[^>]+>", "", texto))
    return re.sub(r"\n\s*\n+", "\n\n", texto).strip()


def extrair_corpo(parte: dict) -> str:
    """Pega o texto do e-mail, preferindo text/plain; se só houver HTML, tira as tags."""
    simples, rico = [], []

    def visitar(p):
        tipo = p.get("mimeType", "")
        dados = p.get("body", {}).get("data")
        if dados and tipo == "text/plain":
            simples.append(_decodificar(dados))
        elif dados and tipo == "text/html":
            rico.append(_sem_html(_decodificar(dados)))
        for filho in p.get("parts", []) or []:
            visitar(filho)

    visitar(parte)
    return "\n".join(simples or rico).strip()


def _cabecalhos(msg: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


def buscar(consulta: str) -> str:
    s = servico()
    r = s.users().messages().list(userId="me", q=consulta, maxResults=10).execute()
    ids = [m["id"] for m in r.get("messages", [])]
    if not ids:
        return "Nenhum e-mail encontrado."
    linhas = []
    for i in ids:
        m = s.users().messages().get(userId="me", id=i, format="metadata",
                                     metadataHeaders=["From", "Subject", "Date"]).execute()
        h = _cabecalhos(m)
        nao_lido = " [NÃO LIDO]" if "UNREAD" in m.get("labelIds", []) else ""
        linhas.append(f"id={i}{nao_lido}\n  De: {h.get('from', '')}\n  Assunto: {h.get('subject', '')}\n"
                      f"  Data: {h.get('date', '')}\n  Trecho: {html.unescape(m.get('snippet', ''))}")
    return _cortar("\n".join(linhas))


def ler(id_email: str) -> str:
    m = servico().users().messages().get(userId="me", id=id_email, format="full").execute()
    h = _cabecalhos(m)
    corpo = extrair_corpo(m.get("payload", {})) or "(sem texto)"
    return _cortar(f"De: {h.get('from', '')}\nPara: {h.get('to', '')}\nAssunto: {h.get('subject', '')}\n"
                   f"Data: {h.get('date', '')}\n\n{corpo}")


def montar_mensagem(para: str, assunto: str, corpo: str) -> dict:
    msg = MIMEText(corpo, "plain", "utf-8")
    msg["To"], msg["Subject"] = para, assunto
    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")}


def enviar(para: str, assunto: str, corpo: str) -> str:
    r = servico().users().messages().send(userId="me", body=montar_mensagem(para, assunto, corpo)).execute()
    return f"E-mail enviado (id={r.get('id')})."


def rascunho(para: str, assunto: str, corpo: str) -> str:
    r = servico().users().drafts().create(
        userId="me", body={"message": montar_mensagem(para, assunto, corpo)}).execute()
    return f"Rascunho salvo no Gmail (id={r.get('id')})."


def marcar_lido(id_email: str) -> str:
    servico().users().messages().modify(userId="me", id=id_email, body={"removeLabelIds": ["UNREAD"]}).execute()
    return "Marcado como lido."


NOVAS = [
    Ferramenta("gmail_buscar",
               "Busca e-mails no Gmail do usuário (até 10). Use a sintaxe de busca do Gmail, "
               "ex.: 'is:unread', 'from:fulano@x.com', 'newer_than:2d', 'subject:boleto'.",
               {"consulta": "termos de busca do Gmail"}, buscar),
    Ferramenta("gmail_ler", "Lê o conteúdo completo de um e-mail pelo id (que vem do gmail_buscar).",
               {"id_email": "id do e-mail"}, ler),
    Ferramenta("gmail_rascunho", "Salva um rascunho no Gmail, sem enviar.",
               {"para": "e-mail do destinatário", "assunto": "assunto", "corpo": "texto do e-mail"},
               rascunho, sensivel=True),
    Ferramenta("gmail_enviar", "Envia um e-mail pelo Gmail do usuário.",
               {"para": "e-mail do destinatário", "assunto": "assunto", "corpo": "texto do e-mail"},
               enviar, sensivel=True),
    Ferramenta("gmail_marcar_lido", "Marca um e-mail como lido.", {"id_email": "id do e-mail"}, marcar_lido),
]


def registrar() -> str | None:
    """Liga as ferramentas do Gmail se estiver tudo pronto. Devolve o motivo se não estiver."""
    if not CREDENCIAIS.exists():
        return "falta o arquivo credentials.json (veja a seção Gmail do README)"
    if not bibliotecas_instaladas():
        return "faltam bibliotecas: pip install -r requirements.txt"
    for f in NOVAS:
        if f.nome not in POR_NOME:
            FERRAMENTAS.append(f)
            POR_NOME[f.nome] = f
    return None
