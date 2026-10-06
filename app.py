from datetime import timedelta
import sqlite3

from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

import config
from insumos_iniciais import UNIDADES
from contagem import bp as contagem_bp, init_db as init_db_contagem, parse_quantidade
from desperdicio import bp as desperdicio_bp, init_db as init_db_desperdicio
from compras import bp as compras_bp, init_db as init_db_compras, parse_valor
from produtos_nota import bp as produtos_nota_bp, init_db as init_db_produtos_nota
from relatorio import bp as relatorio_bp
from mural import bp as mural_bp, init_db as init_db_mural
from funcionarios import autenticar, bp as funcionarios_bp, conferir_sessao, init_db as init_db_funcionarios

app = Flask(__name__)
# O PythonAnywhere atende por HTTPS na frente do app; assim os links por e-mail saem com https
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
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
app.register_blueprint(produtos_nota_bp)
DB_NAME = config.DB_PATH


@app.before_request
def exigir_login():
    if request.endpoint in ("login", "static", "funcionarios.esqueci_senha", "funcionarios.redefinir_senha"):
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
    # Características que vêm da nota fiscal
    colunas = {c["name"] for c in conn.execute("PRAGMA table_info(produtos)")}
    for coluna in ("ncm", "codigo", "ean", "unidade", "fornecedor"):
        if coluna not in colunas:
            conn.execute(f"ALTER TABLE produtos ADD COLUMN {coluna} TEXT NOT NULL DEFAULT ''")
    conn.commit()
    conn.close()


CAMPOS_TEXTO = ("ncm", "codigo", "ean", "unidade", "fornecedor")


def ler_form_produto(form):
    """Valida o formulário de produto. Retorna (dados, erro)."""
    dados = {"nome": form.get("nome", "").strip()}
    for campo in CAMPOS_TEXTO:
        dados[campo] = form.get(campo, "").strip()
    dados["ncm"] = "".join(c for c in dados["ncm"] if c.isdigit())
    if not dados["nome"]:
        return dados, "O nome do produto é obrigatório."
    if dados["ncm"] and len(dados["ncm"]) != 8:
        return dados, "O NCM tem 8 números (ex.: 0402.10.10)."
    try:
        dados["quantidade"] = parse_quantidade(form.get("quantidade", ""))
    except ValueError:
        dados["quantidade"] = None
    if dados["quantidade"] is None:
        return dados, "A quantidade deve ser um número maior ou igual a zero (ex.: 2,5)."
    try:
        dados["preco"] = parse_valor(form.get("preco", ""))
    except ValueError:
        dados["preco"] = None
    if dados["preco"] is None:
        return dados, "O preço deve ser um número válido, maior ou igual a zero (ex.: 12,90)."
    return dados, None

@app.route("/")
def index():
    busca = request.args.get("busca", "")
    conn = get_connection()
    if busca:
        produtos = conn.execute(
            "SELECT * FROM produtos WHERE nome LIKE ? OR ncm LIKE ? OR codigo LIKE ? OR ean LIKE ? ORDER BY nome",
            (f"%{busca}%",) * 4
        ).fetchall()
    else:
        produtos = conn.execute("SELECT * FROM produtos ORDER BY nome").fetchall()
    conn.close()
    return render_template("index.html", produtos=produtos, busca=busca)

@app.route("/adicionar", methods=["GET", "POST"])
def adicionar():
    erro = None
    dados = {}
    if request.method == "POST":
        dados, erro = ler_form_produto(request.form)
        if not erro:
            conn = get_connection()
            conn.execute(
                "INSERT INTO produtos (nome, quantidade, preco, ncm, codigo, ean, unidade, fornecedor)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (dados["nome"], dados["quantidade"], dados["preco"], *(dados[c] for c in CAMPOS_TEXTO))
            )
            conn.commit()
            conn.close()
            return redirect(url_for("index"))

    return render_template("adicionar.html", erro=erro, produto=dados, unidades=UNIDADES)

@app.route("/editar/<int:id>", methods=["GET", "POST"])
def editar(id):
    conn = get_connection()
    produto = conn.execute("SELECT * FROM produtos WHERE id = ?", (id,)).fetchone()

    if produto is None:
        conn.close()
        return "Produto não encontrado", 404

    produto = dict(produto)
    erro = None
    if request.method == "POST":
        dados, erro = ler_form_produto(request.form)
        if not erro:
            conn.execute(
                "UPDATE produtos SET nome = ?, quantidade = ?, preco = ?, ncm = ?, codigo = ?, ean = ?,"
                " unidade = ?, fornecedor = ? WHERE id = ?",
                (dados["nome"], dados["quantidade"], dados["preco"], *(dados[c] for c in CAMPOS_TEXTO), id)
            )
            conn.commit()
            conn.close()
            return redirect(url_for("index"))
        produto.update(dados)

    conn.close()
    return render_template("editar.html", produto=produto, erro=erro, unidades=UNIDADES)

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
init_db_produtos_nota()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

