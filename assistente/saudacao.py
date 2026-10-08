"""Saudação de acordo com o horário."""
from datetime import datetime

TEXTOS = {
    "pt": ("Bom dia", "Boa tarde", "Boa noite"),
    "en": ("Good morning", "Good afternoon", "Good evening"),
}


def periodo(hora: int) -> int:
    """0 = manhã (5h–11h), 1 = tarde (12h–17h), 2 = noite (18h–4h)."""
    if 5 <= hora < 12:
        return 0
    if 12 <= hora < 18:
        return 1
    return 2


def saudar(nome: str, idioma: str = "pt", agora: datetime | None = None) -> str:
    agora = agora or datetime.now()
    textos = TEXTOS.get(idioma, TEXTOS["pt"])
    cumprimento = textos[periodo(agora.hour)]
    return f"{cumprimento}, {nome}!" if nome else f"{cumprimento}!"
