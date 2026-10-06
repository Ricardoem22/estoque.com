# config.py
# Configurações do app, lidas de variáveis de ambiente.
import os
import secrets
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Caminho fixo do banco, independente da pasta de onde o app é iniciado
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "estoque.db"))

# Pasta das fotos de desperdício (fora do repositório)
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(BASE_DIR, "fotos"))

# Senha de acesso da equipe. Sem ela definida, ninguém consegue entrar.
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

# Senha da gerência, para aprovar desperdícios. Sem ela ninguém aprova.
GERENCIA_PASSWORD = os.environ.get("GERENCIA_PASSWORD", "")

# Chave para assinar o cookie de login. Se não for definida, é gerada a cada
# reinício (todos precisam entrar de novo depois de um Reload).
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)


# O servidor (PythonAnywhere) roda em UTC. Datas e horas do app usam o
# horário de Brasília, para a contagem não sair com o dia seguinte à noite.
FUSO_BRASIL = timezone(timedelta(hours=-3))


def agora():
    return datetime.now(FUSO_BRASIL).replace(tzinfo=None)


def hoje():
    return agora().date()
