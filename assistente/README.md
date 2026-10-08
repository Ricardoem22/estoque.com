# Assistente pessoal (protótipo — Etapa 2)

Chat por texto no Windows. Ao abrir, ele diz **"Bom dia"**, **"Boa tarde"** ou **"Boa noite"** conforme o horário, com o seu nome, e fala isso em voz alta.
Conversa em português ou em inglês. Usa uma IA **local** (Ollama) e, se ela não estiver disponível, uma **API externa** (Anthropic).

Por enquanto ele **não executa nenhuma ação**: ainda não tem acesso ao Gmail, à Alexa nem aos dispositivos da casa.

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

Na primeira vez, ele pergunta como deve te chamar. O nome fica guardado em `%APPDATA%\Assistente\memoria.json`, somente no seu computador.

| Comando | O que faz |
|---|---|
| `/nome Fulano` | muda como ele te chama |
| `/lembrar ...` | guarda uma preferência |
| `/memoria` | mostra o que está guardado |
| `/esquecer` | apaga tudo (pede confirmação) |
| `/voz` | liga ou desliga a fala das respostas |
| `/sair` | encerra |

## Testes

```
python -m unittest discover -s tests
```

## Próximas etapas

- Entrada por microfone (falar em vez de digitar).
- Gmail: ler e resumir e-mails. Enviar exigirá confirmação.
- Casa (Alexa, Ekaza, Positivo, Intelbras): lâmpadas e TVs, sempre com permissões limitadas.
