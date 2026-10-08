"""Modelos de IA: local (Ollama) e externo (API da Anthropic)."""
import json
import os
import urllib.error
import urllib.request


class ModeloIndisponivel(Exception):
    pass


class ModeloLocal:
    """Conversa com o Ollama rodando no próprio computador."""

    nome = "local"

    def __init__(self):
        self.url = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        self.modelo = os.environ.get("OLLAMA_MODELO", "qwen2.5:7b")

    def disponivel(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=2):
                return True
        except (urllib.error.URLError, OSError):
            return False

    def responder(self, sistema: str, historico: list[dict]) -> str:
        corpo = json.dumps({
            "model": self.modelo,
            "stream": False,
            "messages": [{"role": "system", "content": sistema}, *historico],
        }).encode("utf-8")
        req = urllib.request.Request(f"{self.url}/api/chat", data=corpo,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                dados = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ModeloIndisponivel(
                    f"O modelo '{self.modelo}' não está baixado. Rode: ollama pull {self.modelo}") from e
            raise ModeloIndisponivel(f"O Ollama respondeu com erro {e.code}.") from e
        except (urllib.error.URLError, OSError) as e:
            raise ModeloIndisponivel("Não consegui falar com o Ollama. Ele está aberto?") from e
        return dados["message"]["content"].strip()


class ModeloAPI:
    """Usa a API da Anthropic (precisa de internet e de ANTHROPIC_API_KEY)."""

    nome = "api"

    def __init__(self):
        self.modelo = os.environ.get("ANTHROPIC_MODELO", "claude-opus-5-5")
        self._cliente = None

    def disponivel(self) -> bool:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

    def responder(self, sistema: str, historico: list[dict]) -> str:
        import anthropic

        if self._cliente is None:
            self._cliente = anthropic.Anthropic()
        try:
            resposta = self._cliente.beta.messages.create(
                model=self.modelo,
                max_tokens=16000,
                system=sistema,
                messages=historico,
                output_config={"effort": "low"},
                # Se o modelo recusar, a própria API tenta de novo com outro modelo.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as e:
            raise ModeloIndisponivel("A chave da API é inválida. Confira o ANTHROPIC_API_KEY no .env.") from e
        except anthropic.RateLimitError as e:
            raise ModeloIndisponivel("Muitas mensagens seguidas na API. Espere um pouco e tente de novo.") from e
        except anthropic.APIStatusError as e:
            raise ModeloIndisponivel(f"A API respondeu com erro {e.status_code}.") from e
        except anthropic.APIConnectionError as e:
            raise ModeloIndisponivel("Sem conexão com a API. Verifique a internet.") from e

        if resposta.stop_reason == "refusal":
            return "Desculpe, não posso ajudar com isso."
        return "".join(b.text for b in resposta.content if b.type == "text").strip()


def escolher_modelo(modo: str):
    """modo: 'local', 'api' ou 'auto' (tenta o local e, se não houver, usa a API)."""
    local, api = ModeloLocal(), ModeloAPI()
    if modo == "local":
        return local
    if modo == "api":
        return api
    if local.disponivel():
        return local
    if api.disponivel():
        return api
    return local  # vai mostrar a mensagem explicando como abrir o Ollama
