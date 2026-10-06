# Como colocar o app no ar (PythonAnywhere)

O app guarda os dados em SQLite (`estoque.db`, na pasta do projeto).
No PythonAnywhere esse arquivo fica salvo; em hospedagens sem disco
persistente (Render/Heroku no plano grátis) os dados seriam apagados.

## 1. Criar a conta e baixar o código

1. Crie uma conta grátis em https://www.pythonanywhere.com (plano "Beginner").
2. Abra **Consoles → Bash** e rode:

   ```bash
   git clone https://github.com/Ricardoem22/estoque.com.git
   cd estoque.com
   pip install --user -r requirements.txt
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```

   Guarde o código que o último comando imprime: ele é a `SECRET_KEY`.

## 2. Criar o site

1. Aba **Web → Add a new web app → Manual configuration → Python 3.10** (ou mais novo).
2. Em **Source code** e **Working directory** coloque `/home/SEU_USUARIO/estoque.com`.
3. Clique no link do **WSGI configuration file**, apague tudo e cole:

   ```python
   import os
   import sys

   os.environ["APP_PASSWORD"] = "troque-por-uma-senha-forte"
   os.environ["SECRET_KEY"] = "cole-aqui-o-codigo-gerado-no-passo-1"
   os.environ["GERENCIA_PASSWORD"] = "senha-da-gerencia-diferente-da-equipe"

   sys.path.insert(0, "/home/SEU_USUARIO/estoque.com")
   from app import app as application
   ```

4. Salve e clique em **Reload** na aba Web.
5. Acesse `https://SEU_USUARIO.pythonanywhere.com` e entre com o usuário `gerencia`
   e a `GERENCIA_PASSWORD`. Depois siga "Funcionários e senhas" abaixo.

## Funcionários e senhas

Cada pessoa entra com o próprio usuário e senha.

1. Entre com o usuário `gerencia` e a `GERENCIA_PASSWORD` do WSGI.
2. Abra **Funcionários**, cadastre você mesmo com o perfil **Gerência** e anote a senha
   temporária que aparece. Depois cadastre a equipe.
3. Saia e entre com o seu usuário. No primeiro acesso o sistema pede uma senha nova.

- **Esqueci a senha:** a gerência toca em **Nova senha** no nome da pessoa e passa a senha
  temporária para ela.
- **Funcionário saiu:** toque em **Desativar**. Ele é desconectado na hora.
- **A gerência esqueceu a senha:** entre com o usuário `gerencia` e a `GERENCIA_PASSWORD`,
  que sempre funcionam, e gere uma nova senha para a sua conta.
- A senha antiga da equipe (`APP_PASSWORD`, com o usuário `equipe`) só funciona enquanto
  nenhum funcionário estiver cadastrado.

## Atualizar depois de mudanças no GitHub

```bash
cd ~/estoque.com && git pull
pip install --user -r requirements.txt
```

Depois clique em **Reload** na aba Web.

## Configurações (variáveis de ambiente)

| Variável | Para que serve |
| --- | --- |
| `GERENCIA_PASSWORD` | Acesso de emergência da gerência (usuário `gerencia`): primeiro acesso e recuperação. |
| `APP_PASSWORD` | Opcional. Senha antiga da equipe (usuário `equipe`); vale só enquanto não houver funcionários cadastrados. |
| `SECRET_KEY` | Chave do cookie de login. Sem ela, todos precisam entrar de novo a cada Reload. |
| `DATABASE_PATH` | Opcional. Caminho do banco; o padrão é `estoque.db` na pasta do projeto. |
| `UPLOAD_DIR` | Opcional. Pasta das fotos de desperdício; o padrão é `fotos/` na pasta do projeto. |

## Rodar no seu computador

```bash
pip install -r requirements.txt
GERENCIA_PASSWORD=minhasenha python app.py
```

No Windows (PowerShell): `$env:GERENCIA_PASSWORD="minhasenha"; python app.py`

Abra http://localhost:5000 e entre com o usuário `gerencia` e a senha `minhasenha`.

## Observações

- No plano grátis, entre na aba **Web** a cada 3 meses e clique em
  "Run until 3 months from today" para o site não ser desligado.
- Faça cópias do `estoque.db` de vez em quando (aba **Files**, botão de download).
- As fotos de desperdício ficam na pasta `fotos/` (fora do GitHub). Cada foto é reduzida no
  celular antes do envio; o plano grátis tem 512 MB de disco, então acompanhe o uso na aba **Files**.
