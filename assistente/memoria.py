"""Memória local: um arquivo JSON só no seu computador.

Guarda apenas o que você mandar (nome e preferências). Nunca guarde senhas aqui.
"""
import json
import os
from pathlib import Path


def pasta_padrao() -> Path:
    base = os.environ.get("APPDATA")  # Windows: C:\Users\<você>\AppData\Roaming
    return Path(base) / "Assistente" if base else Path.home() / ".assistente"


class Memoria:
    def __init__(self, pasta: Path | None = None):
        self.arquivo = (pasta or pasta_padrao()) / "memoria.json"
        self.dados = self._carregar()

    def _carregar(self) -> dict:
        try:
            return json.loads(self.arquivo.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def salvar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text(json.dumps(self.dados, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, chave, padrao=None):
        return self.dados.get(chave, padrao)

    def set(self, chave, valor) -> None:
        self.dados[chave] = valor
        self.salvar()

    def lembrar(self, fato: str) -> None:
        self.dados.setdefault("fatos", []).append(fato)
        self.salvar()

    def apagar_tudo(self) -> None:
        self.dados = {}
        if self.arquivo.exists():
            self.arquivo.unlink()
