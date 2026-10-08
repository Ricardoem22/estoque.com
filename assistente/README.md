# Assistente pessoal (protótipo — Etapas 2, 3 e 5)

Chat por texto no Windows. Ao abrir, ele diz **"Bom dia"**, **"Boa tarde"** ou **"Boa noite"** conforme o horário, com o seu nome, e fala isso em voz alta.
Conversa em português ou em inglês. Usa uma IA **local** (Ollama) e, se ela não estiver disponível, uma **API externa** (Anthropic).

Ele também **age no computador**: basta pedir em linguagem normal ("abre o Chrome", "organiza minha pasta Downloads por tipo", "quanto espaço tem no disco C?").

| Ação | Pede confirmação? |
|---|---|
| abrir programa, arquivo, pasta ou site | não |
| listar pasta, ler arquivo, criar pasta | não |
| escrever, mover, copiar arquivo | sim |
| apagar (definitivo, não vai para a lixeira) | sim |
| rodar comando no PowerShell | sim |

Nada é proibido. A confirmação aparece como `Autorizar? (s/n)` e mostra exatamente o que será feito. Para executar sem perguntar, coloque `CONFIRMAR_ACOES=nao` no `.env`. Assim, um erro de interpretação da IA pode apagar ou alterar arquivos sem aviso.

Com o Gmail conectado (veja abaixo), ele busca, lê e resume e-mails, salva rascunhos e envia. **Enviar e salvar rascunho sempre pedem confirmação**, mostrando destinatário, assunto e texto.

Ainda não tem acesso à Alexa nem aos dispositivos da casa.

## Instalação no Windows

1. Instale o **Python 3.11 ou mais novo** em <https://www.python.org/downloads/> e marque "Add Python to PATH".
2. Instale o **Ollama** em <https://ollama.com/download>. Depois, no Prompt de Comando:
   ```
   ollama pull qwen2.5:7b
   ```
   (cerca de 4,7 GB; se o computador tiver menos de 16 GB de RAM, use `qwen2.5:3b` e ajuste o `.env`)
3. Nesta pasta:
   ```
   pip install -r requirements.txt
   copy .env.exemplo .env
   ```
4. (Opcional) Para usar a API externa, coloque a chave em `ANTHROPIC_API_KEY` no `.env`. Ela é cobrada por uso.
5. Voz masculina em português: em *Configurações › Hora e idioma › Fala*, adicione a voz **Microsoft Daniel (Português - Brasil)**, caso ela não apareça.

## Uso

```
python assistente.py
```

**Para falar em vez de digitar:** no `Você:`, aperte **Enter sem escrever nada**, fale e faça uma pausa. O reconhecimento de voz roda no seu computador, sem internet; na primeira vez, ele baixa o modelo (cerca de 500 MB). Se ficar lento, use `OUVIR_MODELO=base` no `.env`.

**Modo mãos-livres:** digite `/maoslivres` (ou coloque `MAOS_LIVRES=sim` no `.env` para já abrir assim). Ele fica ouvindo e só responde quando você diz **"Jarvis, ..."**; se disser só "Jarvis", ele pergunta "Sim?" e espera o pedido. Para voltar ao teclado: `Ctrl+C` ou "Jarvis, pare de ouvir".

Ou dê dois cliques em **`Iniciar Jarvis.bat`** (pode copiá-lo para a Área de Trabalho). Ele espera que esta pasta esteja em `C:\Users\<você>\assistente-pessoal`.

Na primeira vez, ele pergunta como deve te chamar. O nome fica guardado em `%APPDATA%\Assistente\memoria.json`, somente no seu computador.

| Comando | O que faz |
|---|---|
| `/nome Fulano` | muda como ele te chama |
| `/lembrar ...` | guarda uma preferência |
| `/memoria` | mostra o que está guardado |
| `/esquecer` | apaga tudo (pede confirmação) |
| `/voz` | liga ou desliga a fala das respostas |
| `/sair` | encerra |

## Gmail

O Google exige que cada pessoa crie a própria "chave" de acesso. É gratuito e leva uns 10 minutos, uma vez só.

1. Abra <https://console.cloud.google.com/> com a sua conta do Gmail e crie um projeto chamado **Jarvis**.
2. Em **APIs e serviços › Biblioteca**, procure **Gmail API** e clique em **Ativar**.
3. Em **Google Auth Platform** (ou **Tela de consentimento OAuth**), clique em **Começar**: nome do app **Jarvis**, o seu e-mail como suporte e contato, público **Externo**. Conclua.
4. Em **Público › Usuários de teste**, adicione o seu próprio endereço do Gmail.
5. Em **Clientes › Criar cliente**, escolha o tipo **App para computador**, dê o nome **Jarvis**, crie e clique em **Baixar JSON**.
6. No PowerShell, mova o arquivo baixado para a pasta do assistente com o nome certo:
   ```
   Move-Item "$HOME\Downloads\client_secret_*.json" "$HOME\assistente-pessoal\credentials.json"
   ```
7. Abra o Jarvis e digite `/gmail`. O navegador abre: escolha a sua conta. No aviso "O Google não verificou este app", clique em **Continuar** (o app é seu) e depois em **Permitir**.

Pronto. Peça, por exemplo, "resuma meus e-mails não lidos de hoje".

Enquanto o app estiver em modo de teste, o Google pede para autorizar de novo a cada 7 dias: é só digitar `/gmail` outra vez. A autorização fica em `%APPDATA%\Assistente\gmail_token.json`; `/gmail sair` apaga.

## TVs

Funciona com **LG (webOS)**, **Samsung (Tizen, 2016 em diante)** e TVs com **Roku** (como as Philips Roku TV), pela rede de casa, sem internet.

1. Deixe as TVs ligadas e no mesmo Wi-Fi do computador.
2. No Jarvis, digite `/tv procurar`. Se o Windows perguntar sobre o Firewall, clique em **Permitir**.
3. Dê nomes: `/tv nome 1 sala`, `/tv nome 2 quarto`.
4. Peça: "Jarvis, abre o YouTube na TV da sala", "abaixa o volume da TV do quarto", "desliga a TV".

Na primeira vez, LG e Samsung mostram na tela um pedido para permitir o Jarvis: aceite com o controle remoto.
Para **ligar** uma TV desligada, ative nela a opção de ligar pela rede (LG: "Ligar via Wi-Fi"; Samsung: "Ligar com dispositivo móvel"). Na Roku, deixe "Controle por apps móveis" ativado.

## Atualizar

Dê dois cliques em **`Atualizar Jarvis.bat`**. Ele baixa a versão mais nova do GitHub e instala o que faltar. O seu `.env` e a sua memória são mantidos.

## Testes

```
python -m unittest discover -s tests
```

## Próximas etapas

- Casa (Positivo/Tuya, Intelbras, Ekaza): lâmpadas e TVs.
