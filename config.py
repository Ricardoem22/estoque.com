# config.py
# Configurações do app, lidas de variáveis de ambiente.
import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Caminho fixo do banco, independente da pasta de onde o app é iniciado
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "estoque.db"))

# Pasta das fotos de desperdício (fora do repositório)
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(BASE_DIR, "fotos"))

# Senha de acesso da equipe. Sem ela definida, ninguém consegue entrar.
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

# Chave para assinar o cookie de login. Se não for definida, é gerada a cada
# reinício (todos precisam entrar de novo depois de um Reload).
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
