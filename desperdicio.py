# desperdicio.py
# Registro de desperdício de insumos (vencido, estragado, erro de preparo...).
import csv
import io
from datetime import date, datetime

from flask import Blueprint, Response, redirect, render_template, request, url_for

from contagem import agrupar_por_categoria, data_br_filter, formatar_quantidade, get_connection, parse_quantidade
from insumos_iniciais import UNIDADES

bp = Blueprint("desperdicio", __name__)

MOTIVOS = ["Vencido", "Estragado", "Erro de preparo", "Queimado", "Caiu / quebrou", "Sobra descartada", "Outro"]


def init_db():
    conn = get_connection()
    # Nome e categoria ficam gravados no registro para o histórico não sumir
    # se o insumo for excluído depois.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS desperdicios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            insumo_id INTEGER REFERENCES insumos(id) ON DELETE SET NULL,
            insumo_nome TEXT NOT NULL,
            categoria TEXT NOT NULL,
            quantidade REAL NOT NULL,
            unidade TEXT NOT NULL,
            motivo TEXT NOT NULL,
            responsavel TEXT NOT NULL DEFAULT '',
            observacao TEXT NOT NULL DEFAULT '',
            criado_em TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def mes_selecionado():
    mes = request.args.get("mes", "")
    try:
        datetime.strptime(mes, "%Y-%m")
        return mes
    except ValueError:
        return date.today().strftime("%Y-%m")


def registros_do_mes(conn, mes):
    return conn.execute("""
        SELECT * FROM desperdicios
        WHERE substr(data, 1, 7) = ?
        ORDER BY data DESC, id DESC
    """, (mes,)).fetchall()


def resumo(registros):
    """Total por insumo e unidade, do maior para o menor."""
    totais = {}
    for r in registros:
        chave = (r["insumo_nome"], r["unidade"])
        total = totais.setdefault(chave, {"nome": r["insumo_nome"], "unidade": r["unidade"], "quantidade": 0, "vezes": 0})
        total["quantidade"] += r["quantidade"]
        total["vezes"] += 1
    return sorted(totais.values(), key=lambda t: (-t["vezes"], t["nome"]))


@bp.route("/desperdicio", methods=["GET", "POST"])
def desperdicio():
    conn = get_connection()
    erro = None
    form = request.form

    if request.method == "POST":
        insumo = conn.execute("SELECT * FROM insumos WHERE id = ?", (form.get("insumo_id", type=int),)).fetchone()
        data = form.get("data", "")
        motivo = form.get("motivo", "")
        try:
            quantidade = parse_quantidade(form.get("quantidade"))
        except ValueError:
            quantidade = None
        try:
            datetime.strptime(data, "%Y-%m-%d")
        except ValueError:
            erro = "Informe uma data válida."
        if insumo is None:
            erro = "Escolha o insumo."
        elif not quantidade:
            erro = "Informe uma quantidade maior que zero."
        elif motivo not in MOTIVOS:
            erro = "Escolha o motivo."

        if not erro:
            conn.execute("""
                INSERT INTO desperdicios
                    (data, insumo_id, insumo_nome, categoria, quantidade, unidade, motivo, responsavel, observacao, criado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data, insumo["id"], insumo["nome"], insumo["categoria"], quantidade,
                form.get("unidade", "").strip() or insumo["unidade"], motivo,
                form.get("responsavel", "").strip(), form.get("observacao", "").strip(),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ))
            conn.commit()
            conn.close()
            return redirect(url_for("desperdicio.desperdicio", mes=data[:7], salvo=1))

    mes = mes_selecionado()
    registros = registros_do_mes(conn, mes)
    grupos = agrupar_por_categoria(conn.execute("SELECT * FROM insumos").fetchall())
    conn.close()
    return render_template(
        "desperdicio.html", grupos=grupos, unidades=UNIDADES, motivos=MOTIVOS,
        registros=registros, resumo=resumo(registros), mes=mes, erro=erro, form=form,
        hoje=date.today().isoformat(), salvo=request.args.get("salvo"),
    )


@bp.route("/desperdicio/<int:id>/excluir", methods=["POST"])
def excluir_desperdicio(id):
    conn = get_connection()
    conn.execute("DELETE FROM desperdicios WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("desperdicio.desperdicio", mes=request.form.get("mes", "")))


@bp.route("/desperdicio/csv")
def exportar_csv():
    mes = mes_selecionado()
    conn = get_connection()
    registros = registros_do_mes(conn, mes)
    conn.close()

    saida = io.StringIO()
    writer = csv.writer(saida, delimiter=";")
    writer.writerow(["Data", "Categoria", "Insumo", "Quantidade", "Unidade", "Motivo", "Responsável", "Observação"])
    for r in registros:
        writer.writerow([
            data_br_filter(r["data"]), r["categoria"], r["insumo_nome"], formatar_quantidade(r["quantidade"]),
            r["unidade"], r["motivo"], r["responsavel"], r["observacao"],
        ])

    # BOM para o Excel reconhecer os acentos
    return Response(
        "﻿" + saida.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=desperdicio_{mes}.csv"},
    )
