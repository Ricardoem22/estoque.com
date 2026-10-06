from datetime import timedelta

from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

import config
from contagem import bp as contagem_bp, init_db as init_db_contagem
from desperdicio import bp as desperdicio_bp, init_db as init_db_desperdicio
from compras import bp as compras_bp, init_db as init_db_compras
from relatorio import bp as relatorio_bp
from mural import bp as mural_bp, init_db as init_db_mural
from funcionarios import autenticar, bp as funcionarios_bp, conferir_sessao, init_db as init_db_funcionarios
from insumo_cadastro import bp as insumo_bp
from movimentos import bp as movimentos_bp, init_db as init_db_movimentos

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
app.register_blueprint(insumo_bp)
app.register_blueprint(movimentos_bp)


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
    # A tela inicial é o painel do estoque
    return url_for("relatorio.estoque")


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

@app.route("/")
def index():
    # A antiga aba Produtos virou o painel do Estoque (um estoque só, o dos insumos)
    return redirect(url_for("relatorio.estoque"))


# Cria as tabelas também quando rodando via gunicorn
init_db_contagem()
init_db_desperdicio()
init_db_compras()
init_db_funcionarios()
init_db_mural()
init_db_movimentos()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

