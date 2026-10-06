# mural.py
# Mural de mensagens da equipe: conversas, dúvidas e recados.
# A gerência fixa recados no topo. A página busca mensagens novas de tempos
# em tempos (o PythonAnywhere grátis não aceita WebSocket).
import sqlite3

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

import config

bp = Blueprint("mural", __name__)

TAMANHO_MAXIMO = 1000
ULTIMAS = 200


def get_connection():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mensagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            autor_id INTEGER,
            autor_nome TEXT NOT NULL,
            texto TEXT NOT NULL,
            fixada INTEGER NOT NULL DEFAULT 0,
            criada_em TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def pode_apagar(mensagem):
    if session.get("gerente"):
        return True
    return bool(mensagem["autor_id"]) and mensagem["autor_id"] == session.get("funcionario_id")


def contexto():
    return {"pode_apagar": pode_apagar, "gerente": session.get("gerente"), "eu": session.get("funcionario_id"),
            "meu_nome": session.get("nome")}


@bp.route("/mural", methods=["GET", "POST"])
def mural():
    erro = None
    if request.method == "POST":
        texto = request.form.get("texto", "").strip()
        if not texto:
            erro = "Escreva a mensagem antes de enviar."
        elif len(texto) > TAMANHO_MAXIMO:
            erro = f"A mensagem pode ter até {TAMANHO_MAXIMO} caracteres."
        else:
            conn = get_connection()
            conn.execute(
                "INSERT INTO mensagens (autor_id, autor_nome, texto, fixada, criada_em) VALUES (?, ?, ?, ?, ?)",
                (session.get("funcionario_id"), session.get("nome") or "Equipe", texto,
                 1 if session.get("gerente") and request.form.get("fixar") else 0,
                 config.agora().strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
            conn.close()
            return redirect(url_for("mural.mural") + "#fim")

    conn = get_connection()
    fixadas = conn.execute("SELECT * FROM mensagens WHERE fixada = 1 ORDER BY id DESC").fetchall()
    mensagens = conn.execute(
        "SELECT * FROM (SELECT * FROM mensagens ORDER BY id DESC LIMIT ?) ORDER BY id", (ULTIMAS,)
    ).fetchall()
    conn.close()
    return render_template(
        "mural.html", fixadas=fixadas, mensagens=mensagens, erro=erro,
        texto=request.form.get("texto", "") if erro else "", maximo=TAMANHO_MAXIMO, **contexto(),
    )


@bp.route("/mural/novas")
def novas():
    """Mensagens depois da última que a página já mostra, em HTML pronto."""
    depois = request.args.get("depois", 0, type=int)
    conn = get_connection()
    mensagens = conn.execute(
        "SELECT * FROM mensagens WHERE id > ? ORDER BY id LIMIT ?", (depois, ULTIMAS)
    ).fetchall()
    conn.close()
    html = "".join(render_template("_mensagem.html", m=m, **contexto()) for m in mensagens)
    return jsonify(html=html, ultima=mensagens[-1]["id"] if mensagens else depois)


@bp.route("/mural/<int:id>/<any(fixar, desafixar, apagar):acao>", methods=["POST"])
def acao(id, acao):
    conn = get_connection()
    mensagem = conn.execute("SELECT * FROM mensagens WHERE id = ?", (id,)).fetchone()
    if mensagem:
        if acao == "apagar" and pode_apagar(mensagem):
            conn.execute("DELETE FROM mensagens WHERE id = ?", (id,))
        elif acao in ("fixar", "desafixar") and session.get("gerente"):
            conn.execute("UPDATE mensagens SET fixada = ? WHERE id = ?", (1 if acao == "fixar" else 0, id))
        conn.commit()
    conn.close()
    return redirect(url_for("mural.mural"))
