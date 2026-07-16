from flask import Flask, render_template, request, redirect, url_for
import sqlite3

app = Flask(__name__)
DB_NAME = "estoque.db"

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

if __name__ == "__main__":
    init_db()
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

