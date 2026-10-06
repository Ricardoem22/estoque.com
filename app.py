from datetime import timedelta
import sqlite3

from flask import Flask, render_template, request, redirect, session, url_for

import config
from contagem import bp as contagem_bp, init_db as init_db_contagem
from desperdicio import bp as desperdicio_bp, init_db as init_db_desperdicio
from compras import bp as compras_bp, init_db as init_db_compras
from relatorio import bp as relatorio_bp
from mural import bp as mural_bp, init_db as init_db_mural
from funcionarios import autenticar, bp as funcionarios_bp, conferir_sessao, init_db as init_db_funcionarios

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    MAX_CONTENT_LENGTH=20 * 1024 * 1024,  # fotos de celular
)
app.register_blueprint(contagem_bp)
app.register_blueprint(desperdicio_bp)
app.register_blueprint(compras_bp)
app.register_blueprint(relatorio_bp)
app.register_blueprint(funcionarios_bp)
app.register_blueprint(mural_bp)
DB_NAME = config.DB_PATH


@app.before_request
def exigir_login():
    if request.endpoint in ("login", "static", "funcionarios.esqueci_senha"):
        return None
    if not session.get("logado"):
        return redirect(url_for("login", proximo=request.full_path.rstrip("?")))
    return conferir_sessao()


def destino_seguro(proximo):
    # Só redireciona para caminhos internos do próprio site
    if proximo.startswith("/") and not proximo.startswith(("//", "/\\")):
        return proximo
    return url_for("index")


@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    proximo = request.values.get("proximo", "")
    usuario = request.form.get("usuario", "")
    if request.method == "POST":
        erro = autenticar(usuario, request.form.get("senha", ""))
        if not erro:
            if session.get("trocar_senha"):
                return redirect(url_for("funcionarios.trocar_senha"))
            return redirect(destino_seguro(proximo))
    return render_template("login.html", erro=erro, proximo=proximo, usuario=usuario)


@app.route("/gerencia")
def gerencia():
    # Aprovar desperdício e cadastrar funcionários exige uma conta com perfil Gerência
    if session.get("gerente"):
        return redirect(destino_seguro(request.args.get("proximo", "") or url_for("desperdicio.desperdicio")))
    return render_template("gerencia.html")


@app.route("/sair")
def sair():
    session.clear()
    return redirect(url_for("login"))

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            quantidade INTEGER NOT NULL,
            preco REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()

@app.route("/")
def index():
    busca = request.args.get("busca", "")
    conn = get_connection()
    if busca:
        produtos = conn.execute(
            "SELECT * FROM produtos WHERE nome LIKE ? ORDER BY nome",
            (f"%{busca}%",)
        ).fetchall()
    else:
        produtos = conn.execute("SELECT * FROM produtos ORDER BY nome").fetchall()
    conn.close()
    return render_template("index.html", produtos=produtos, busca=busca)

@app.route("/adicionar", methods=["GET", "POST"])
def adicionar():
    erro = None
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        quantidade = request.form.get("quantidade", "")
        preco = request.form.get("preco", "")

        # Validações
        if not nome:
            erro = "O nome do produto é obrigatório."
        elif not quantidade.isdigit() or int(quantidade) < 0:
            erro = "A quantidade deve ser um número inteiro maior ou igual a zero."
        else:
            try:
                preco_float = float(preco)
                if preco_float < 0:
                    erro = "O preço não pode ser negativo."
            except ValueError:
                erro = "O preço deve ser um número válido."

        if not erro:
            conn = get_connection()
            conn.execute(
                "INSERT INTO produtos (nome, quantidade, preco) VALUES (?, ?, ?)",
                (nome, int(quantidade), preco_float)
            )
            conn.commit()
            conn.close()
            return redirect(url_for("index"))

    return render_template("adicionar.html", erro=erro)

@app.route("/editar/<int:id>", methods=["GET", "POST"])
def editar(id):
    conn = get_connection()
    produto = conn.execute("SELECT * FROM produtos WHERE id = ?", (id,)).fetchone()

    if produto is None:
        conn.close()
        return "Produto não encontrado", 404

    erro = None
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        quantidade = request.form.get("quantidade", "")
        preco = request.form.get("preco", "")

        if not nome:
            erro = "O nome do produto é obrigatório."
        elif not quantidade.isdigit() or int(quantidade) < 0:
            erro = "A quantidade deve ser um número inteiro maior ou igual a zero."
        else:
            try:
                preco_float = float(preco)
                if preco_float < 0:
                    erro = "O preço não pode ser negativo."
            except ValueError:
                erro = "O preço deve ser um número válido."

        if not erro:
            conn.execute(
                "UPDATE produtos SET nome = ?, quantidade = ?, preco = ? WHERE id = ?",
                (nome, int(quantidade), preco_float, id)
            )
            conn.commit()
            conn.close()
            return redirect(url_for("index"))

    conn.close()
    return render_template("editar.html", produto=produto, erro=erro)

@app.route("/excluir/<int:id>")
def excluir(id):
    conn = get_connection()
    conn.execute("DELETE FROM produtos WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

# Cria as tabelas também quando rodando via gunicorn
init_db()
init_db_contagem()
init_db_desperdicio()
init_db_compras()
init_db_funcionarios()
init_db_mural()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

