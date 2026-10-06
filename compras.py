# compras.py
# Registro das compras (entradas de mercadoria), usado no cálculo do consumo.
from datetime import datetime
import re

from flask import Blueprint, redirect, render_template, request, url_for

from contagem import agrupar_por_categoria, get_connection, parse_quantidade
import config
from insumos_iniciais import UNIDADES

bp = Blueprint("compras", __name__)


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            insumo_id INTEGER NOT NULL REFERENCES insumos(id) ON DELETE CASCADE,
            quantidade REAL NOT NULL,
            unidade TEXT NOT NULL,
            fornecedor TEXT NOT NULL DEFAULT '',
            criado_em TEXT NOT NULL
        )
    """)
    # Valor pago na linha da nota (opcional), usado no valor do estoque
    colunas = {c["name"] for c in conn.execute("PRAGMA table_info(compras)")}
    if "valor_total" not in colunas:
        conn.execute("ALTER TABLE compras ADD COLUMN valor_total REAL")
    conn.commit()
    conn.close()


@bp.app_template_filter("brl")
def brl_filter(valor):
    if valor is None:
        return ""
    texto = f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


def parse_valor(texto):
    """Aceita '45,90', 'R$ 1.234,56', '1234.56'. Retorna None se vazio."""
    texto = (texto or "").replace("R$", "").replace(" ", "").strip()
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", texto):
        texto = texto.replace(".", "")  # 1.234 = mil duzentos e trinta e quatro
    valor = float(texto)
    if valor < 0:
        raise ValueError
    return valor


def mes_selecionado():
    mes = request.args.get("mes", "")
    try:
        datetime.strptime(mes, "%Y-%m")
        return mes
    except ValueError:
        return config.hoje().strftime("%Y-%m")


@bp.route("/compras", methods=["GET", "POST"])
def compras():
    conn = get_connection()
    erro = None
    form = request.form

    if request.method == "POST":
        insumo = conn.execute("SELECT * FROM insumos WHERE id = ?", (form.get("insumo_id", type=int),)).fetchone()
        data = form.get("data", "")
        try:
            quantidade = parse_quantidade(form.get("quantidade"))
        except ValueError:
            quantidade = None
        try:
            valor_total = parse_valor(form.get("valor_total"))
        except ValueError:
            valor_total = -1
        try:
            datetime.strptime(data, "%Y-%m-%d")
        except ValueError:
            erro = "Informe uma data válida."
        if insumo is None:
            erro = "Escolha o insumo."
        elif not quantidade:
            erro = "Informe uma quantidade maior que zero."
        elif valor_total == -1:
            erro = "Valor pago inválido. Use só números, ex.: 45,90."

        if not erro:
            conn.execute("""
                INSERT INTO compras (data, insumo_id, quantidade, unidade, fornecedor, criado_em, valor_total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                data, insumo["id"], quantidade, form.get("unidade", "").strip() or insumo["unidade"],
                form.get("fornecedor", "").strip(), config.agora().strftime("%Y-%m-%d %H:%M:%S"), valor_total,
            ))
            conn.commit()
            conn.close()
            # Mantém a data e o fornecedor para lançar a nota inteira em sequência
            return redirect(url_for("compras.compras", mes=data[:7], salvo=1, data=data,
                                    fornecedor=form.get("fornecedor", "").strip()))

    mes = mes_selecionado()
    registros = conn.execute("""
        SELECT c.*, i.nome AS insumo_nome FROM compras c
        JOIN insumos i ON i.id = c.insumo_id
        WHERE substr(c.data, 1, 7) = ?
        ORDER BY c.data DESC, c.id DESC
    """, (mes,)).fetchall()
    grupos = agrupar_por_categoria(conn.execute("SELECT * FROM insumos").fetchall())
    conn.close()
    return render_template(
        "compras.html", grupos=grupos, unidades=UNIDADES, registros=registros, mes=mes, erro=erro, form=form,
        total_mes=sum(r["valor_total"] or 0 for r in registros),
        data_padrao=form.get("data") or request.args.get("data") or config.hoje().isoformat(),
        fornecedor=form.get("fornecedor") or request.args.get("fornecedor", ""),
        salvo=request.args.get("salvo"),
    )


@bp.route("/compras/<int:id>/excluir", methods=["POST"])
def excluir_compra(id):
    conn = get_connection()
    conn.execute("DELETE FROM compras WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("compras.compras", mes=request.form.get("mes", "")))
