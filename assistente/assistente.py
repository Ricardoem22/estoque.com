"""Assistente pessoal — chat por texto ou voz.

Rode com:  python assistente.py
"""
import os
import re
import threading
import time
from pathlib import Path

from datetime import datetime

import gmail
import tv
from ferramentas import Executor
from memoria import Memoria
from modelos import ModeloIndisponivel, escolher_modelo
from ouvido import Ouvido, extrair_chamado
from saudacao import saudar
from voz import Voz

VERSAO = "9"  # aumenta a cada atualização; aparece na abertura

AJUDA = """Para falar em vez de digitar, aperte Enter sem escrever nada.
No modo mãos-livres, é só dizer "Jarvis, ..." (Ctrl+C ou "Jarvis, pare de ouvir" volta ao teclado).
Comandos:
  /nome <seu nome>   muda como eu te chamo
  /lembrar <algo>    guarda uma preferência (fica só neste computador)
  /memoria           mostra o que eu guardei
  /esquecer          apaga toda a memória
  /voz               liga ou desliga a minha voz
  /tv                mostra as TVs cadastradas
  /tv procurar       procura as TVs na rede (deixe-as ligadas)
  /tv nome <nº> <nome>   dá um nome, ex.: /tv nome 1 sala
  /tv adicionar <lg|samsung|roku> <ip>   cadastra uma TV à mão
  /voz teste         testa a voz e mostra as vozes instaladas
  /maoslivres        fico ouvindo e respondo quando você disser o meu nome
  /microfone         lista os microfones e testa o volume
  /microfone <nº>    passa a usar o microfone desse número (e testa)
  /gmail             conecta ao Gmail (ou mostra o que falta)
  /gmail sair        desconecta o Gmail deste computador
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


def montar_sistema(nome_assistente: str, memoria: Memoria, com_gmail: bool) -> str:
    lista_tvs = memoria.get("tvs", [])
    sobre_tvs = (
        "Você controla as TVs da casa com tv_controlar (TVs: "
        + ", ".join(t["nome"] for t in lista_tvs) + "). "
        if lista_tvs else
        "Ainda não há TVs cadastradas; se pedirem para controlar a TV, diga para usar /tv procurar. "
    )
    integracoes = sobre_tvs + (
        "Você tem acesso ao Gmail do usuário pelas ferramentas gmail_*: para resumir e-mails, "
        "busque primeiro e leia os que importam. Você ainda não tem acesso a agenda, Alexa ou às lâmpadas; "
        if com_gmail else
        "Você ainda não tem acesso a e-mail, agenda, Alexa ou às lâmpadas; "
    )
    texto = (
        f"Você é {nome_assistente}, um assistente pessoal educado e direto. "
        f"Você está conversando com {memoria.get('nome', 'o usuário')}. "
        "Responda em português do Brasil, a não ser que o usuário escreva em inglês; nesse caso responda em inglês. "
        "Seja breve: suas respostas podem ser lidas em voz alta. "
        "Você pode agir no computador do usuário (Windows) com as ferramentas disponíveis: "
        "abrir programas e sites, mexer em arquivos e pastas e rodar comandos no PowerShell. "
        "Use-as quando o usuário pedir algo que dependa delas, e conte o resultado real; "
        "se uma ação falhar ou não for autorizada, diga isso. "
        + integracoes +
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
    falta_gmail = gmail.registrar()  # precisa vir antes de escolher o modelo
    tv.registrar(memoria)
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
    print(f"{nome_assistente}: {ola} (versão {VERSAO}; modelo: {modelo.nome}; digite /ajuda para ver os comandos)")
    if not voz.ativa and os.environ.get("VOZ_ATIVA", "sim").lower() == "sim":
        print(f"[aviso] A voz não funcionou{f' ({voz.erro})' if voz.erro else ''}. Digite /voz teste.")
    elif not falar_respostas:
        print("(as respostas não serão faladas: FALAR_RESPOSTAS=nao no .env; /voz liga)")
    voz.falar(ola)

    ouvido = Ouvido(os.environ.get("OUVIR_MODELO", "small"), os.environ.get("OUVIR_IDIOMA", "pt"),
                    os.environ.get("OUVIR_DISPOSITIVO") or str(memoria.get("microfone", "")))
    # Carrega a IA e o reconhecimento de voz em segundo plano enquanto você lê a saudação
    ouvido.aquecer()
    if modelo.nome == "local":
        threading.Thread(target=modelo.aquecer, daemon=True).start()
    mostrar_tempo = os.environ.get("MOSTRAR_TEMPO", "sim").lower() == "sim"
    ouvido.dica = f"{nome_assistente}."
    maos_livres = ouvido.disponivel and os.environ.get("MAOS_LIVRES", "nao").lower() == "sim"
    if maos_livres:
        print(f"{nome_assistente}: Modo mãos-livres ligado: diga \"{nome_assistente}\" e o seu pedido.")

    def esperar_chamado() -> str | None:
        """Ouve sem parar até alguém dizer o nome do assistente; devolve o pedido."""
        frase = ouvido.ouvir(espera_max=None, avisar=False)
        if not frase:
            return None
        chamou, pedido = extrair_chamado(frase, nome_assistente)
        if not chamou:
            return None
        if not pedido:
            print(f"{nome_assistente}: Sim?")
            voz.falar("Sim?")
            pedido = ouvido.ouvir(espera_max=8.0)
            if not pedido:
                return None
        print(f"Você (voz): {pedido}")
        return pedido

    historico: list = []
    avisou_ouvindo = False
    while True:
        if maos_livres:
            if not avisou_ouvindo:
                print(f"(ouvindo... diga \"{nome_assistente}\"; Ctrl+C volta ao teclado)")
                avisou_ouvindo = True
            try:
                texto = esperar_chamado()
            except KeyboardInterrupt:
                maos_livres = False
                print(f"\n{nome_assistente}: Modo mãos-livres desligado. Pode digitar.")
                continue
            if not texto:
                continue
            avisou_ouvindo = False
            if re.search(r"(?i)\b(pare|parar|para) de (ouvir|escutar)\b|modo texto", texto):
                maos_livres = False
                print(f"{nome_assistente}: Certo, parei de ouvir. Pode digitar.")
                voz.falar("Certo, parei de ouvir.")
                continue
        else:
            try:
                texto = input("Você: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
        if not texto:
            if not ouvido.disponivel:
                print(f"[aviso] {ouvido.erro}")
                continue
            t0 = time.monotonic()
            texto = ouvido.ouvir()
            t_ouvir = time.monotonic() - t0
            if not texto:
                print(f"{nome_assistente}: {ouvido.motivo or 'Não ouvi nada.'} Aperte Enter para tentar de novo.")
                continue
            print(f"Você (voz): {texto}" + (f"   (entendi em {t_ouvir:.1f} s, contando a sua fala)" if mostrar_tempo else ""))

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
            elif cmd == "/gmail" and arg == "sair":
                gmail.desconectar()
                print(f"{nome_assistente}: Gmail desconectado deste computador.")
            elif cmd == "/gmail":
                if falta_gmail:
                    print(f"{nome_assistente}: Ainda não dá para usar o Gmail: {falta_gmail}.")
                else:
                    try:
                        gmail.servico()
                        print(f"{nome_assistente}: Gmail conectado.")
                    except Exception as e:
                        print(f"[aviso] Não consegui conectar ao Gmail: {e}")
            elif cmd == "/microfone":
                if not ouvido.disponivel:
                    print(f"[aviso] {ouvido.erro}")
                    continue
                if arg.isdigit():
                    ouvido.dispositivo = int(arg)
                    memoria.set("microfone", int(arg))
                    print(f"{nome_assistente}: Vou usar o microfone {arg}. Fale algo nos próximos 4 segundos:")
                    try:
                        ouvido.medir()
                        print("Se a barra encheu quando você falou, está pronto: aperte Enter vazio para falar comigo.")
                    except Exception as e:
                        print(f"[aviso] Esse microfone não funcionou ({e}). Tente outro número.")
                    continue
                try:
                    print("Microfones (* = o padrão do Windows):")
                    print(ouvido.microfones())
                    print(f"Usando: {ouvido.dispositivo if ouvido.dispositivo is not None else 'o padrão'}. "
                          "Fale algo nos próximos 4 segundos:")
                    ouvido.medir()
                    print("Se a barra quase não se mexeu, teste outro microfone com /microfone <número>, "
                          "por exemplo /microfone 2.")
                except Exception as e:
                    print(f"[aviso] Não consegui usar o microfone: {e}")
            elif cmd == "/maoslivres":
                if not ouvido.disponivel:
                    print(f"[aviso] {ouvido.erro}")
                else:
                    maos_livres = True
                    print(f"{nome_assistente}: Modo mãos-livres ligado. Diga \"{nome_assistente}\" e o seu pedido, "
                          f"por exemplo \"{nome_assistente}, que horas são?\".")
            elif cmd == "/tv":
                partes = arg.split()
                if not partes:
                    print(tv.descrever())
                elif partes[0] == "procurar":
                    print(f"{nome_assistente}: Procurando TVs na rede (uns 5 segundos)...")
                    achadas = tv.procurar()
                    novas = tv.adicionar(achadas)
                    ignoradas = [a for a in achadas if a["marca"] not in tv.DRIVERS]
                    print(tv.descrever())
                    if novas:
                        print(f"{nome_assistente}: Achei {len(novas)} TV(s) nova(s). Dê nomes com /tv nome <nº> <nome>.")
                    if ignoradas:
                        print(f"(também vi {len(ignoradas)} aparelho(s) Android/Google TV, que ainda não sei controlar)")
                    if not achadas:
                        print("Não achei nenhuma. As TVs estão ligadas e no mesmo Wi-Fi do computador?")
                elif partes[0] == "nome" and len(partes) >= 3 and partes[1].isdigit():
                    lista = tv.tvs()
                    i = int(partes[1]) - 1
                    if 0 <= i < len(lista):
                        lista[i]["nome"] = " ".join(partes[2:])
                        tv.salvar()
                        print(tv.descrever())
                    else:
                        print("Número de TV inválido. Veja a lista com /tv.")
                elif partes[0] == "adicionar" and len(partes) == 3 and partes[1] in tv.DRIVERS:
                    tv.adicionar([{"ip": partes[2], "marca": partes[1]}])
                    print(tv.descrever())
                else:
                    print(AJUDA)
            elif cmd == "/voz" and arg == "teste":
                if not voz.ativa:
                    print(f"{nome_assistente}: A voz está desligada"
                          + (f" ({voz.erro})." if voz.erro else ". Confira VOZ_ATIVA=sim no .env."))
                else:
                    print(f"{nome_assistente}: Usando: {voz.nome_voz}")
                    for v in voz.vozes():
                        print(f"   - {v}")
                    falar_respostas = True
                    voz.falar("Teste de voz. Se você está me ouvindo, está tudo certo.")
                    print(f"{nome_assistente}: Se não ouviu nada, confira o volume e a saída de som do Windows.")
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
        t0 = time.monotonic()
        try:
            resposta = modelo.conversar(montar_sistema(nome_assistente, memoria, falta_gmail is None), historico, texto, executar)
        except ModeloIndisponivel as e:
            del historico[tamanho:]  # descarta a pergunta que não teve resposta
            print(f"[aviso] {e}")
            continue
        print(f"{nome_assistente}: {resposta}")
        if mostrar_tempo:
            print(f"   (pensei em {time.monotonic() - t0:.1f} s)")
        if falar_respostas:
            voz.falar(resposta)

    despedida = "Até logo!" if idioma == "pt" else "See you!"
    print(f"{nome_assistente}: {despedida}")
    voz.falar(despedida)


if __name__ == "__main__":
    main()
