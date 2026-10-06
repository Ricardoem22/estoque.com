# funcionarios.py
# Contas individuais dos funcionários: login, cadastro pela gerência,
# senha temporária ("esqueci a senha") e troca de senha.
import hmac
import re
import secrets
import sqlite3
import time

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

import config
from email_envio import email_configurado, enviar_email

bp = Blueprint("funcionarios", __name__)

PAPEIS = {"equipe": "Equipe", "gerente": "Gerência"}
SENHA_MINIMA = 6
# Usuários reservados para o acesso de emergência pelas senhas do servidor
USUARIO_MESTRE = "gerencia"
USUARIO_EQUIPE = "equipe"
# Sem letras e números parecidos (l/1, o/0), para ditar a senha sem confusão
LETRAS_SENHA = "abcdefghjkmnpqrstuvwxyz23456789"
VALIDADE_LINK = 60 * 60  # o link de nova senha vale 1 hora
INTERVALO_EMAIL = 120  # no máximo um e-mail a cada 2 minutos por pessoa
ultimo_envio = {}
EMAIL_VALIDO = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def get_connection():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS funcionarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            usuario TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            papel TEXT NOT NULL DEFAULT 'equipe',
            ativo INTEGER NOT NULL DEFAULT 1,
            trocar_senha INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT NOT NULL
        )
    """)
    colunas = {c["name"] for c in conn.execute("PRAGMA table_info(funcionarios)")}
    if "email" not in colunas:
        conn.execute("ALTER TABLE funcionarios ADD COLUMN email TEXT NOT NULL DEFAULT ''")
    conn.commit()
    conn.close()


def normalizar_email(texto):
    return (texto or "").strip().lower()


def email_invalido(email):
    return bool(email) and not EMAIL_VALIDO.fullmatch(email)


# ---------- Link de nova senha por e-mail ----------

def assinador():
    return URLSafeTimedSerializer(current_app.secret_key, salt="redefinir-senha")


def gerar_token(funcionario):
    # O final do hash da senha entra no token: depois de trocar a senha, o link deixa de valer
    return assinador().dumps({"id": funcionario["id"], "h": funcionario["senha_hash"][-12:]})


def ler_token(token):
    try:
        dados = assinador().loads(token, max_age=VALIDADE_LINK)
    except (SignatureExpired, BadSignature):
        return None
    conn = get_connection()
    funcionario = conn.execute("SELECT * FROM funcionarios WHERE id = ?", (dados.get("id"),)).fetchone()
    conn.close()
    if not funcionario or not funcionario["ativo"] or funcionario["senha_hash"][-12:] != dados.get("h"):
        return None
    return funcionario


def normalizar_usuario(texto):
    return (texto or "").strip().lower()


def senha_temporaria():
    return "".join(secrets.choice(LETRAS_SENHA) for _ in range(8))


def senha_confere(digitada, correta):
    return bool(correta) and hmac.compare_digest(digitada.encode(), correta.encode())


def entrar(nome, papel, funcionario_id=None, trocar_senha=False):
    session.clear()
    session.permanent = True
    session["logado"] = True
    session["nome"] = nome
    session["funcionario_id"] = funcionario_id
    if papel == "gerente":
        session["gerente"] = nome
    if trocar_senha:
        session["trocar_senha"] = True


def autenticar(usuario, senha):
    """Confere usuário e senha. Devolve uma mensagem de erro ou None se entrou."""
    usuario = normalizar_usuario(usuario)
    conn = get_connection()
    funcionario = conn.execute("SELECT * FROM funcionarios WHERE usuario = ?", (usuario,)).fetchone()
    total = conn.execute("SELECT COUNT(*) FROM funcionarios").fetchone()[0]
    conn.close()

    if funcionario:
        if not check_password_hash(funcionario["senha_hash"], senha):
            return "Usuário ou senha incorretos."
        if not funcionario["ativo"]:
            return "Este usuário está desativado. Fale com a gerência."
        entrar(funcionario["nome"], funcionario["papel"], funcionario["id"], bool(funcionario["trocar_senha"]))
        return None

    # Acesso da gerência pela senha do servidor: primeiro acesso e recuperação
    if usuario == USUARIO_MESTRE and senha_confere(senha, config.GERENCIA_PASSWORD):
        entrar("Gerência", "gerente")
        return None
    # Senha antiga da equipe: vale só até o primeiro funcionário ser cadastrado
    if usuario == USUARIO_EQUIPE and total == 0 and senha_confere(senha, config.APP_PASSWORD):
        entrar("Equipe", "equipe")
        return None
    return "Usuário ou senha incorretos."


def conferir_sessao():
    """Chamado a cada página: derruba quem foi desativado e força a troca de senha."""
    funcionario_id = session.get("funcionario_id")
    if funcionario_id:
        conn = get_connection()
        funcionario = conn.execute("SELECT * FROM funcionarios WHERE id = ?", (funcionario_id,)).fetchone()
        conn.close()
        if not funcionario or not funcionario["ativo"]:
            session.clear()
            return redirect(url_for("login"))
        # Mantém nome e perfil em dia se a gerência mudou o cadastro
        session["nome"] = funcionario["nome"]
        if funcionario["papel"] == "gerente":
            session["gerente"] = funcionario["nome"]
        else:
            session.pop("gerente", None)
    if session.get("trocar_senha") and request.endpoint not in ("funcionarios.trocar_senha", "sair", "static"):
        return redirect(url_for("funcionarios.trocar_senha"))
    return None


@bp.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():
    enviado = False
    erro = None
    if request.method == "POST":
        busca = request.form.get("usuario", "").strip().lower()
        if not busca:
            erro = "Digite seu usuário ou e-mail."
        else:
            conn = get_connection()
            funcionario = conn.execute(
                "SELECT * FROM funcionarios WHERE ativo = 1 AND email != '' AND (usuario = ? OR email = ?)",
                (busca, busca),
            ).fetchone()
            conn.close()
            agora = time.time()
            if funcionario and agora - ultimo_envio.get(funcionario["id"], 0) > INTERVALO_EMAIL:
                link = url_for("funcionarios.redefinir_senha", token=gerar_token(funcionario), _external=True)
                try:
                    enviar_email(
                        funcionario["email"], "Nova senha - Gestor Full de Restaurante",
                        f"Olá, {funcionario['nome']}.\n\n"
                        f"Para criar uma nova senha, abra o link abaixo (vale por 1 hora):\n{link}\n\n"
                        f"Seu usuário é: {funcionario['usuario']}\n\n"
                        "Se você não pediu isso, ignore este e-mail. Sua senha continua a mesma.",
                    )
                    ultimo_envio[funcionario["id"]] = agora
                except Exception:
                    current_app.logger.exception("Falha ao enviar e-mail de nova senha")
                    erro = "Não consegui enviar o e-mail agora. Tente de novo em alguns minutos ou fale com a gerência."
            # A mesma resposta com ou sem cadastro, para não revelar quem tem conta
            enviado = not erro
    return render_template("esqueci_senha.html", email_ativo=email_configurado(), enviado=enviado, erro=erro)


@bp.route("/redefinir-senha/<token>", methods=["GET", "POST"])
def redefinir_senha(token):
    funcionario = ler_token(token)
    if not funcionario:
        return render_template("redefinir_senha.html", invalido=True)
    erro = None
    if request.method == "POST":
        nova = request.form.get("nova", "")
        if len(nova) < SENHA_MINIMA:
            erro = f"A nova senha precisa ter pelo menos {SENHA_MINIMA} caracteres."
        elif nova != request.form.get("confirmar", ""):
            erro = "A confirmação não é igual à nova senha."
        else:
            conn = get_connection()
            conn.execute("UPDATE funcionarios SET senha_hash = ?, trocar_senha = 0 WHERE id = ?",
                         (generate_password_hash(nova), funcionario["id"]))
            conn.commit()
            conn.close()
            entrar(funcionario["nome"], funcionario["papel"], funcionario["id"])
            return redirect(url_for("contagem.contagens"))
    return render_template("redefinir_senha.html", funcionario=funcionario, erro=erro)


@bp.route("/meu-email", methods=["POST"])
def meu_email():
    funcionario_id = session.get("funcionario_id")
    email = normalizar_email(request.form.get("email"))
    if not funcionario_id or email_invalido(email):
        return redirect(url_for("funcionarios.trocar_senha", email_erro=1))
    conn = get_connection()
    conn.execute("UPDATE funcionarios SET email = ? WHERE id = ?", (email, funcionario_id))
    conn.commit()
    conn.close()
    return redirect(url_for("funcionarios.trocar_senha", email_salvo=1))


@bp.route("/trocar-senha", methods=["GET", "POST"])
def trocar_senha():
    erro = None
    funcionario_id = session.get("funcionario_id")
    if not funcionario_id:
        # Acessos pelas senhas do servidor não têm senha própria para trocar
        return render_template("trocar_senha.html", sem_conta=True)

    if request.method == "POST":
        atual = request.form.get("atual", "")
        nova = request.form.get("nova", "")
        conn = get_connection()
        funcionario = conn.execute("SELECT * FROM funcionarios WHERE id = ?", (funcionario_id,)).fetchone()
        if not check_password_hash(funcionario["senha_hash"], atual):
            erro = "A senha atual está incorreta."
        elif len(nova) < SENHA_MINIMA:
            erro = f"A nova senha precisa ter pelo menos {SENHA_MINIMA} caracteres."
        elif nova != request.form.get("confirmar", ""):
            erro = "A confirmação não é igual à nova senha."
        elif nova == atual:
            erro = "Escolha uma senha diferente da atual."
        if not erro:
            conn.execute(
                "UPDATE funcionarios SET senha_hash = ?, trocar_senha = 0 WHERE id = ?",
                (generate_password_hash(nova), funcionario_id),
            )
            conn.commit()
            session.pop("trocar_senha", None)
        conn.close()
        if not erro:
            return redirect(url_for("contagem.contagens"))

    conn = get_connection()
    meu = conn.execute("SELECT email FROM funcionarios WHERE id = ?", (funcionario_id,)).fetchone()
    conn.close()
    return render_template(
        "trocar_senha.html", erro=erro, obrigatoria=session.get("trocar_senha"), email=meu["email"] if meu else "",
        email_salvo=request.args.get("email_salvo"), email_erro=request.args.get("email_erro"),
    )


# ---------- Cadastro (só gerência) ----------

@bp.before_request
def exigir_gerencia_no_cadastro():
    if request.endpoint and request.endpoint.startswith("funcionarios.cadastro") and not session.get("gerente"):
        return render_template("gerencia.html"), 403
    return None


def listar(conn):
    return conn.execute(
        "SELECT * FROM funcionarios ORDER BY ativo DESC, papel DESC, nome COLLATE NOCASE"
    ).fetchall()


@bp.route("/funcionarios", methods=["GET", "POST"], endpoint="cadastro")
def cadastro():
    erro = None
    nova_senha = None
    form = request.form
    conn = get_connection()
    if request.method == "POST":
        nome = form.get("nome", "").strip()
        usuario = normalizar_usuario(form.get("usuario"))
        papel = form.get("papel", "equipe")
        email = normalizar_email(form.get("email"))
        if not nome:
            erro = "Informe o nome do funcionário."
        elif not re.fullmatch(r"[a-z0-9._-]{3,30}", usuario):
            erro = "O usuário deve ter de 3 a 30 letras ou números, sem espaços nem acentos (ex.: joao.silva)."
        elif usuario in (USUARIO_MESTRE, USUARIO_EQUIPE):
            erro = f"O usuário \"{usuario}\" é reservado. Escolha outro."
        elif papel not in PAPEIS:
            erro = "Escolha o perfil."
        elif email_invalido(email):
            erro = "O e-mail parece errado. Confira (ex.: joao@gmail.com) ou deixe em branco."
        elif conn.execute("SELECT 1 FROM funcionarios WHERE usuario = ?", (usuario,)).fetchone():
            erro = f"Já existe um funcionário com o usuário \"{usuario}\"."
        if not erro:
            senha = senha_temporaria()
            conn.execute(
                "INSERT INTO funcionarios (nome, usuario, senha_hash, papel, criado_em, email) VALUES (?, ?, ?, ?, ?, ?)",
                (nome, usuario, generate_password_hash(senha), papel, config.agora().strftime("%Y-%m-%d %H:%M:%S"),
                 email),
            )
            conn.commit()
            nova_senha = {"nome": nome, "usuario": usuario, "senha": senha}
            form = {}
    funcionarios = listar(conn)
    conn.close()
    return render_template(
        "funcionarios.html", funcionarios=funcionarios, papeis=PAPEIS, erro=erro,
        form=form, nova_senha=nova_senha, eu=session.get("funcionario_id"), email_ativo=email_configurado(),
    )


@bp.route("/funcionarios/<int:id>/<any(senha, ativar, desativar, perfil, email):acao>", methods=["POST"],
          endpoint="cadastro_acao")
def cadastro_acao(id, acao):
    conn = get_connection()
    funcionario = conn.execute("SELECT * FROM funcionarios WHERE id = ?", (id,)).fetchone()
    if not funcionario:
        conn.close()
        return redirect(url_for("funcionarios.cadastro"))
    erro = None
    nova_senha = None
    proprio = id == session.get("funcionario_id")

    if acao == "email":
        email = normalizar_email(request.form.get("email"))
        if email_invalido(email):
            erro = "O e-mail parece errado. Confira (ex.: joao@gmail.com) ou deixe em branco."
        else:
            conn.execute("UPDATE funcionarios SET email = ? WHERE id = ?", (email, id))
    elif acao == "senha":
        senha = senha_temporaria()
        conn.execute(
            "UPDATE funcionarios SET senha_hash = ?, trocar_senha = 1 WHERE id = ?",
            (generate_password_hash(senha), id),
        )
        nova_senha = {"nome": funcionario["nome"], "usuario": funcionario["usuario"], "senha": senha}
    elif proprio:
        erro = "Você não pode desativar nem mudar o perfil da sua própria conta."
    elif acao in ("ativar", "desativar"):
        conn.execute("UPDATE funcionarios SET ativo = ? WHERE id = ?", (1 if acao == "ativar" else 0, id))
    elif acao == "perfil" and request.form.get("papel") in PAPEIS:
        conn.execute("UPDATE funcionarios SET papel = ? WHERE id = ?", (request.form["papel"], id))
    conn.commit()
    funcionarios = listar(conn)
    conn.close()
    if erro or nova_senha:
        return render_template(
            "funcionarios.html", funcionarios=funcionarios, papeis=PAPEIS, erro=erro,
            form={}, nova_senha=nova_senha, eu=session.get("funcionario_id"),
        )
    return redirect(url_for("funcionarios.cadastro"))
