"""Assistente pessoal — protótipo de chat por texto (Etapa 2).

Rode com:  python assistente.py
"""
import os
from pathlib import Path

from memoria import Memoria
from datetime import datetime

from ferramentas import Executor
from modelos import ModeloIndisponivel, escolher_modelo
from ouvido import Ouvido
from saudacao import saudar
from voz import Voz

AJUDA = """Para falar em vez de digitar, aperte Enter sem escrever nada.
Comandos:
  /nome <seu nome>   muda como eu te chamo
  /lembrar <algo>    guarda uma preferência (fica só neste computador)
  /memoria           mostra o que eu guardei
  /esquecer          apaga toda a memória
  /voz               liga ou desliga a minha voz
  /sair              encerra"""


# Comandos de terminal que às vezes são digitados no chat por engano
COMANDOS_TERMINAL = {"ollama", "pip", "python", "notepad", "cd", "dir", "copy", "expand-archive", "git"}


def carregar_env(arquivo: Path) -> None:
    """Lê o arquivo .env (CHAVE=valor) sem sobrescrever variáveis já definidas."""
    if not arquivo.exists():
        return
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))


def montar_sistema(nome_assistente: str, memoria: Memoria) -> str:
    texto = (
        f"Você é {nome_assistente}, um assistente pessoal educado e direto. "
        f"Você está conversando com {memoria.get('nome', 'o usuário')}. "
        "Responda em português do Brasil, a não ser que o usuário escreva em inglês; nesse caso responda em inglês. "
        "Seja breve: suas respostas podem ser lidas em voz alta. "
        "Você pode agir no computador do usuário (Windows) com as ferramentas disponíveis: "
        "abrir programas e sites, mexer em arquivos e pastas e rodar comandos no PowerShell. "
        "Use-as quando o usuário pedir algo que dependa delas, e conte o resultado real; "
        "se uma ação falhar ou não for autorizada, diga isso. "
        "Você ainda não tem acesso a e-mail, agenda, Alexa ou dispositivos da casa; "
        "se pedirem algo assim, diga que essa integração ainda não foi conectada e não finja ter feito.\n"
        f"Agora são {datetime.now():%d/%m/%Y %H:%M}."
    )
    fatos = memoria.get("fatos", [])
    if fatos:
        texto += "\nPreferências que o usuário pediu para lembrar:\n" + "\n".join(f"- {f}" for f in fatos)
    return texto


def main() -> None:
    carregar_env(Path(__file__).with_name(".env"))
    nome_assistente = os.environ.get("ASSISTENTE_NOME", "Jarvis")
    idioma = os.environ.get("IDIOMA", "pt")
    memoria = Memoria()
    voz = Voz(os.environ.get("VOZ", "Daniel"), os.environ.get("VOZ_ATIVA", "sim").lower() == "sim")
    falar_respostas = os.environ.get("FALAR_RESPOSTAS", "sim").lower() == "sim"
    modelo = escolher_modelo(os.environ.get("MODO", "auto").lower())

    def confirmar(acao: str) -> bool:
        return input(f"{nome_assistente} quer fazer -> {acao}\nAutorizar? (s/n) ").strip().lower() == "s"

    executar = Executor(confirmar, os.environ.get("CONFIRMAR_ACOES", "sim").lower() != "nao")

    if modelo.nome == "local" and modelo.disponivel() and not modelo.tem_modelo():
        outros = modelo.instalados()
        print(f"{nome_assistente}: O modelo de IA '{modelo.modelo}' ainda não está baixado.")
        if input("Quer que eu baixe agora? (s/n) ").strip().lower() == "s":
            if not modelo.baixar():
                print("[aviso] Não consegui baixar. Verifique a internet e abra o assistente de novo.")
        elif outros:
            modelo.modelo = outros[0]
            print(f"{nome_assistente}: Certo, vou usar o '{modelo.modelo}', que já está baixado.")

    if not memoria.get("nome"):
        nome = input(f"{nome_assistente}: Olá! Como você quer que eu te chame? ").strip()
        if nome:
            memoria.set("nome", nome)

    ola = saudar(memoria.get("nome", ""), idioma)
    print(f"{nome_assistente}: {ola} (modelo: {modelo.nome}; digite /ajuda para ver os comandos)")
    voz.falar(ola)

    ouvido = Ouvido(os.environ.get("OUVIR_MODELO", "small"), os.environ.get("OUVIR_IDIOMA", "pt"))

    historico: list = []
    while True:
        try:
            texto = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not texto:
            if not ouvido.disponivel:
                print(f"[aviso] {ouvido.erro}")
                continue
            texto = ouvido.ouvir()
            if not texto:
                print(f"{nome_assistente}: Não ouvi nada. Aperte Enter e fale de novo.")
                continue
            print(f"Você (voz): {texto}")

        if texto.startswith("/"):
            cmd, _, arg = texto.partition(" ")
            arg = arg.strip()
            if cmd == "/sair":
                break
            elif cmd == "/ajuda":
                print(AJUDA)
            elif cmd == "/nome" and arg:
                memoria.set("nome", arg)
                print(f"{nome_assistente}: Certo, vou te chamar de {arg}.")
            elif cmd == "/lembrar" and arg:
                memoria.lembrar(arg)
                print(f"{nome_assistente}: Anotado.")
            elif cmd == "/memoria":
                print(memoria.dados or "Nada guardado.")
                print(f"(arquivo: {memoria.arquivo})")
            elif cmd == "/esquecer":
                if input("Apagar toda a memória? (s/n) ").strip().lower() == "s":
                    memoria.apagar_tudo()
                    print(f"{nome_assistente}: Memória apagada.")
            elif cmd == "/voz":
                falar_respostas = not falar_respostas
                print(f"{nome_assistente}: Voz {'ligada' if falar_respostas else 'desligada'}.")
            else:
                print(AJUDA)
            continue

        if texto.split()[0].lower() in COMANDOS_TERMINAL:
            print(f"{nome_assistente}: Isso parece um comando do PowerShell. Aqui é o nosso chat; "
                  "digite /sair para voltar ao PowerShell e rodar o comando lá.")
            continue

        tamanho = len(historico)
        try:
            resposta = modelo.conversar(montar_sistema(nome_assistente, memoria), historico, texto, executar)
        except ModeloIndisponivel as e:
            del historico[tamanho:]  # descarta a pergunta que não teve resposta
            print(f"[aviso] {e}")
            continue
        print(f"{nome_assistente}: {resposta}")
        if falar_respostas:
            voz.falar(resposta)

    despedida = "Até logo!" if idioma == "pt" else "See you!"
    print(f"{nome_assistente}: {despedida}")
    voz.falar(despedida)


if __name__ == "__main__":
    main()
