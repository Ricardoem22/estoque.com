"""Modelos de IA: local (Ollama) e externo (API da Anthropic).

Cada modelo guarda o histórico no seu próprio formato e executa as
ferramentas pedidas pela IA até ter uma resposta final em texto.
"""
import json
import os
import urllib.error
import urllib.request

from ferramentas import FERRAMENTAS

MAX_RODADAS = 15  # limite de ferramentas seguidas numa mesma pergunta


class ModeloIndisponivel(Exception):
    pass


class ModeloLocal:
    """Conversa com o Ollama rodando no próprio computador."""

    nome = "local"

    def __init__(self):
        self.url = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        self.modelo = os.environ.get("OLLAMA_MODELO", "qwen2.5:7b")
        self.ferramentas = [
            {"type": "function",
             "function": {"name": f.nome, "description": f.descricao, "parameters": f.esquema()}}
            for f in FERRAMENTAS
        ]

    def disponivel(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=2):
                return True
        except (urllib.error.URLError, OSError):
            return False

    def _chat(self, sistema: str, historico: list[dict]) -> dict:
        corpo = json.dumps({
            "model": self.modelo,
            "stream": False,
            "messages": [{"role": "system", "content": sistema}, *historico],
            "tools": self.ferramentas,
        }).encode("utf-8")
        req = urllib.request.Request(f"{self.url}/api/chat", data=corpo,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8"))["message"]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ModeloIndisponivel(
                    f"O modelo '{self.modelo}' não está baixado. Rode: ollama pull {self.modelo}") from e
            raise ModeloIndisponivel(f"O Ollama respondeu com erro {e.code}.") from e
        except (urllib.error.URLError, OSError) as e:
            raise ModeloIndisponivel("Não consegui falar com o Ollama. Ele está aberto?") from e

    def conversar(self, sistema: str, historico: list[dict], texto: str, executar) -> str:
        historico.append({"role": "user", "content": texto})
        for _ in range(MAX_RODADAS):
            msg = self._chat(sistema, historico)
            historico.append(msg)
            chamadas = msg.get("tool_calls") or []
            if not chamadas:
                return (msg.get("content") or "").strip()
            for c in chamadas:
                nome = c["function"]["name"]
                args = c["function"].get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = None
                resultado, _ = executar(nome, args)
                historico.append({"role": "tool", "tool_name": nome, "content": resultado})
        return "Parei depois de muitas ações seguidas. Quer que eu continue?"


class ModeloAPI:
    """Usa a API da Anthropic (precisa de internet e de ANTHROPIC_API_KEY)."""

    nome = "api"

    def __init__(self):
        self.modelo = os.environ.get("ANTHROPIC_MODELO", "claude-opus-5-5")
        self._cliente = None
        self.ferramentas = [
            {"name": f.nome, "description": f.descricao, "input_schema": f.esquema(), "strict": True}
            for f in FERRAMENTAS
        ]

    def disponivel(self) -> bool:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

    def _chat(self, sistema: str, historico: list):
        import anthropic

        if self._cliente is None:
            self._cliente = anthropic.Anthropic()
        try:
            return self._cliente.beta.messages.create(
                model=self.modelo,
                max_tokens=16000,
                system=sistema,
                messages=historico,
                tools=self.ferramentas,
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

    def conversar(self, sistema: str, historico: list, texto: str, executar) -> str:
        historico.append({"role": "user", "content": texto})
        for _ in range(MAX_RODADAS):
            resposta = self._chat(sistema, historico)
            # Guarda o conteúdo completo (inclui raciocínio e chamadas de ferramenta).
            historico.append({"role": "assistant", "content": resposta.content})
            if resposta.stop_reason == "refusal":
                return "Desculpe, não posso ajudar com isso."
            if resposta.stop_reason != "tool_use":
                return "".join(b.text for b in resposta.content if b.type == "text").strip()
            resultados = []
            for b in resposta.content:
                if b.type == "tool_use":
                    resultado, erro = executar(b.name, b.input)
                    resultados.append({"type": "tool_result", "tool_use_id": b.id,
                                       "content": resultado, "is_error": erro})
            historico.append({"role": "user", "content": resultados})
        return "Parei depois de muitas ações seguidas. Quer que eu continue?"


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
