"""Ações no computador que o assistente pode usar.

Nada é proibido. As ações que alteram ou apagam algo ("sensíveis") pedem
confirmação antes, a não ser que CONFIRMAR_ACOES=nao no .env.
"""
import os
import platform
import shutil
import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

WINDOWS = platform.system() == "Windows"
LIMITE_SAIDA = 8000  # caracteres devolvidos à IA


def _caminho(c: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(c))).resolve()


def _cortar(texto: str) -> str:
    return texto if len(texto) <= LIMITE_SAIDA else texto[:LIMITE_SAIDA] + "\n[...cortado]"


def abrir(alvo: str) -> str:
    if alvo.startswith(("http://", "https://")):
        webbrowser.open(alvo)
    elif WINDOWS:
        # "start" abre programas (notepad, calc, spotify:), arquivos, pastas e sites
        subprocess.Popen(["cmd", "/c", "start", "", alvo], shell=False)
    else:
        subprocess.Popen(["xdg-open", alvo])
    return f"Abri: {alvo}"


def listar_arquivos(pasta: str) -> str:
    p = _caminho(pasta)
    itens = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    linhas = [f"{'[pasta] ' if i.is_dir() else ''}{i.name}" for i in itens[:300]]
    return _cortar(f"{p}:\n" + ("\n".join(linhas) or "(vazia)"))


def ler_arquivo(caminho: str) -> str:
    return _cortar(_caminho(caminho).read_text(encoding="utf-8", errors="replace"))


def criar_pasta(caminho: str) -> str:
    p = _caminho(caminho)
    p.mkdir(parents=True, exist_ok=True)
    return f"Pasta pronta: {p}"


def escrever_arquivo(caminho: str, conteudo: str) -> str:
    p = _caminho(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(conteudo, encoding="utf-8")
    return f"Arquivo salvo: {p}"


def mover(origem: str, destino: str) -> str:
    novo = shutil.move(str(_caminho(origem)), str(_caminho(destino)))
    return f"Movido para: {novo}"


def copiar(origem: str, destino: str) -> str:
    o, d = _caminho(origem), _caminho(destino)
    novo = shutil.copytree(o, d / o.name if d.is_dir() else d) if o.is_dir() else shutil.copy2(o, d)
    return f"Copiado para: {novo}"


def apagar(caminho: str) -> str:
    p = _caminho(caminho)
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p)
    else:
        p.unlink()
    return f"Apagado: {p}"


def executar_comando(comando: str) -> str:
    args = (["powershell", "-NoProfile", "-Command", comando] if WINDOWS
            else ["bash", "-lc", comando])
    r = subprocess.run(args, capture_output=True, text=True, timeout=120,
                       encoding="utf-8", errors="replace")
    saida = (r.stdout or "") + (f"\n[erros]\n{r.stderr}" if r.stderr else "")
    return _cortar(f"(código de saída {r.returncode})\n{saida.strip() or '(sem saída)'}")


@dataclass
class Ferramenta:
    nome: str
    descricao: str
    parametros: dict[str, str]  # nome -> descrição (todos texto e obrigatórios)
    funcao: Callable[..., str]
    sensivel: bool = False

    def esquema(self) -> dict:
        return {
            "type": "object",
            "properties": {k: {"type": "string", "description": v} for k, v in self.parametros.items()},
            "required": list(self.parametros),
            "additionalProperties": False,
        }

    def resumo(self, args: dict) -> str:
        return f"{self.nome}: " + ", ".join(f"{k}={v!r}" for k, v in args.items())


FERRAMENTAS = [
    Ferramenta("abrir", "Abre um programa (ex.: notepad, calc, chrome), arquivo, pasta ou site.",
               {"alvo": "nome do programa, caminho ou URL"}, abrir),
    Ferramenta("listar_arquivos", "Lista o conteúdo de uma pasta.",
               {"pasta": "caminho da pasta; ~ é a pasta do usuário"}, listar_arquivos),
    Ferramenta("ler_arquivo", "Lê um arquivo de texto.", {"caminho": "caminho do arquivo"}, ler_arquivo),
    Ferramenta("criar_pasta", "Cria uma pasta (e as pastas acima, se faltarem).",
               {"caminho": "caminho da nova pasta"}, criar_pasta),
    Ferramenta("escrever_arquivo", "Cria ou substitui um arquivo de texto.",
               {"caminho": "caminho do arquivo", "conteudo": "texto completo do arquivo"},
               escrever_arquivo, sensivel=True),
    Ferramenta("mover", "Move ou renomeia um arquivo ou pasta.",
               {"origem": "caminho atual", "destino": "novo caminho ou pasta de destino"}, mover, sensivel=True),
    Ferramenta("copiar", "Copia um arquivo ou pasta.",
               {"origem": "caminho atual", "destino": "caminho ou pasta de destino"}, copiar, sensivel=True),
    Ferramenta("apagar", "Apaga definitivamente um arquivo ou pasta (não vai para a lixeira).",
               {"caminho": "caminho a apagar"}, apagar, sensivel=True),
    Ferramenta("executar_comando",
               "Executa um comando no PowerShell (no Windows) e devolve a saída. Use para o que as outras ferramentas não cobrem.",
               {"comando": "comando completo"}, executar_comando, sensivel=True),
]
POR_NOME = {f.nome: f for f in FERRAMENTAS}


class Executor:
    """Roda as ferramentas, pedindo confirmação nas sensíveis."""

    def __init__(self, confirmar: Callable[[str], bool], pedir_confirmacao: bool = True):
        self.confirmar = confirmar
        self.pedir_confirmacao = pedir_confirmacao

    def __call__(self, nome: str, args: dict) -> tuple[str, bool]:
        """Devolve (resultado, deu_erro)."""
        f = POR_NOME.get(nome)
        if f is None:
            return f"Ferramenta desconhecida: {nome}", True
        if not isinstance(args, dict) or set(args) != set(f.parametros) or \
                not all(isinstance(v, str) for v in args.values()):
            return f"Parâmetros inválidos. Esperado: {list(f.parametros)}", True
        if f.sensivel and self.pedir_confirmacao and not self.confirmar(f.resumo(args)):
            return "O usuário não autorizou esta ação.", False
        try:
            return f.funcao(**args), False
        except subprocess.TimeoutExpired:
            return "O comando passou de 2 minutos e foi interrompido.", True
        except Exception as e:  # erro de arquivo, permissão etc. volta para a IA explicar
            return f"Erro: {type(e).__name__}: {e}", True
