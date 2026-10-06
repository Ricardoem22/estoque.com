# desperdicio.py
# Registro de desperdício de insumos (vencido, estragado, erro de preparo...).
import csv
import io
import os
import uuid
from datetime import datetime

from flask import Blueprint, Response, abort, redirect, render_template, request, send_from_directory, session, url_for

import config

from contagem import agrupar_por_categoria, data_br_filter, formatar_quantidade, get_connection, parse_quantidade
from insumos_iniciais import UNIDADES

bp = Blueprint("desperdicio", __name__)

EXTENSOES_FOTO = {"jpg", "jpeg", "png", "webp", "heic", "heif"}

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
            foto TEXT NOT NULL DEFAULT '',
            criado_em TEXT NOT NULL
        )
    """)
    # Colunas adicionadas depois da primeira versão
    colunas = [c["name"] for c in conn.execute("PRAGMA table_info(desperdicios)")]
    for coluna, tipo in [("foto", "TEXT NOT NULL DEFAULT ''"),
                         ("status", "TEXT NOT NULL DEFAULT 'pendente'"),
                         ("aprovado_por", "TEXT NOT NULL DEFAULT ''"),
                         ("aprovado_em", "TEXT NOT NULL DEFAULT ''")]:
        if coluna not in colunas:
            conn.execute(f"ALTER TABLE desperdicios ADD COLUMN {coluna} {tipo}")
    conn.commit()
    conn.close()


def extensao_foto(arquivo):
    """Retorna a extensão se o arquivo for uma foto aceita, senão None."""
    if not arquivo or not arquivo.filename:
        return None
    ext = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
    if ext not in EXTENSOES_FOTO and (arquivo.mimetype or "").startswith("image/"):
        ext = arquivo.mimetype.split("/", 1)[1].lower()
    return ext if ext in EXTENSOES_FOTO else None


def apagar_foto(nome):
    if nome:
        try:
            os.remove(os.path.join(config.UPLOAD_DIR, nome))
        except OSError:
            pass


def mes_selecionado():
    mes = request.args.get("mes", "")
    try:
        datetime.strptime(mes, "%Y-%m")
        return mes
    except ValueError:
        return config.hoje().strftime("%Y-%m")


def registros_do_mes(conn, mes):
    return conn.execute("""
        SELECT * FROM desperdicios
        WHERE substr(data, 1, 7) = ?
        ORDER BY data DESC, id DESC
    """, (mes,)).fetchall()


def resumo(registros):
    """Total aprovado por insumo e unidade, do mais frequente para o menos."""
    totais = {}
    for r in registros:
        if r["status"] != "aprovado":
            continue
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
        foto = request.files.get("foto")
        ext = extensao_foto(foto)
        if not erro and ext is None:
            erro = "Tire ou anexe uma foto do que foi desperdiçado."

        if not erro:
            os.makedirs(config.UPLOAD_DIR, exist_ok=True)
            nome_foto = f"{uuid.uuid4().hex}.{ext}"
            foto.save(os.path.join(config.UPLOAD_DIR, nome_foto))
            conn.execute("""
                INSERT INTO desperdicios
                    (data, insumo_id, insumo_nome, categoria, quantidade, unidade, motivo, responsavel, observacao,
                     foto, criado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data, insumo["id"], insumo["nome"], insumo["categoria"], quantidade,
                form.get("unidade", "").strip() or insumo["unidade"], motivo,
                form.get("responsavel", "").strip(), form.get("observacao", "").strip(),
                nome_foto, config.agora().strftime("%Y-%m-%d %H:%M:%S"),
            ))
            conn.commit()
            conn.close()
            return redirect(url_for("desperdicio.desperdicio", mes=data[:7], salvo=1))

    mes = mes_selecionado()
    registros = registros_do_mes(conn, mes)
    grupos = agrupar_por_categoria(conn.execute("SELECT * FROM insumos").fetchall())
    conn.close()
    return render_template(
        "desperdicio.html", gerente=session.get("gerente"),
        pendentes=sum(1 for r in registros if r["status"] == "pendente"), grupos=grupos, unidades=UNIDADES, motivos=MOTIVOS,
        registros=registros, resumo=resumo(registros), mes=mes, erro=erro, form=form,
        hoje=config.hoje().isoformat(), salvo=request.args.get("salvo"),
    )


def exigir_gerente():
    if not session.get("gerente"):
        return redirect(url_for("gerencia", proximo=url_for("desperdicio.desperdicio", mes=request.form.get("mes", ""))))
    return None


@bp.route("/desperdicio/<int:id>/<any(aprovar, recusar):acao>", methods=["POST"])
def decidir_desperdicio(id, acao):
    bloqueio = exigir_gerente()
    if bloqueio:
        return bloqueio
    conn = get_connection()
    conn.execute(
        "UPDATE desperdicios SET status = ?, aprovado_por = ?, aprovado_em = ? WHERE id = ?",
        ("aprovado" if acao == "aprovar" else "recusado", session["gerente"],
         config.agora().strftime("%Y-%m-%d %H:%M:%S"), id),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("desperdicio.desperdicio", mes=request.form.get("mes", "")))


@bp.route("/desperdicio/<int:id>/excluir", methods=["POST"])
def excluir_desperdicio(id):
    conn = get_connection()
    registro = conn.execute("SELECT foto, status FROM desperdicios WHERE id = ?", (id,)).fetchone()
    # Depois de aprovado ou recusado, só a gerência pode excluir
    if registro and registro["status"] != "pendente" and not session.get("gerente"):
        conn.close()
        return exigir_gerente()
    if registro:
        apagar_foto(registro["foto"])
    conn.execute("DELETE FROM desperdicios WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("desperdicio.desperdicio", mes=request.form.get("mes", "")))


@bp.route("/desperdicio/foto/<nome>")
def foto(nome):
    if not nome:
        abort(404)
    return send_from_directory(config.UPLOAD_DIR, nome)


@bp.route("/desperdicio/csv")
def exportar_csv():
    mes = mes_selecionado()
    conn = get_connection()
    registros = registros_do_mes(conn, mes)
    conn.close()

    saida = io.StringIO()
    writer = csv.writer(saida, delimiter=";")
    writer.writerow(["Data", "Categoria", "Insumo", "Quantidade", "Unidade", "Motivo", "Responsável", "Observação", "Status", "Aprovado por", "Foto"])
    for r in registros:
        writer.writerow([
            data_br_filter(r["data"]), r["categoria"], r["insumo_nome"], formatar_quantidade(r["quantidade"]),
            r["unidade"], r["motivo"], r["responsavel"], r["observacao"], r["status"].capitalize(), r["aprovado_por"],
            url_for("desperdicio.foto", nome=r["foto"], _external=True) if r["foto"] else "",
        ])

    # BOM para o Excel reconhecer os acentos
    return Response(
        "﻿" + saida.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=desperdicio_{mes}.csv"},
    )
