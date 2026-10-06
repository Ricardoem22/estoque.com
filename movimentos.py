# movimentos.py
# Movimentações manuais de estoque: saída/consumo, devolução ao fornecedor, ajustes com justificativa
# e transferência entre locais. Perdas continuam na aba Desperdício (com foto e aprovação da gerência).
#
# Só as movimentações com data igual ou depois da última contagem mexem no estoque atual: a contagem
# seguinte já mostra o que realmente sobrou.
from datetime import datetime

from flask import Blueprint, redirect, render_template, request, session, url_for

import config
from contagem import get_connection, parse_quantidade
from insumo_cadastro import carregar_conversoes, insumos_para_formulario
from unidades import UNIDADES_COMUNS, converter

bp = Blueprint("movimentos", __name__)

# sinal: + soma no estoque, − desconta, ⇄ não muda o total
TIPOS = {
    "saida": {"nome": "Saída / consumo", "sinal": "−", "fator": -1},
    "devolucao": {"nome": "Devolução ao fornecedor", "sinal": "−", "fator": -1},
    "ajuste_menos": {"nome": "Ajuste: faltou", "sinal": "−", "fator": -1, "justificar": True},
    "ajuste_mais": {"nome": "Ajuste: sobrou", "sinal": "+", "fator": 1, "justificar": True},
    "transferencia": {"nome": "Transferência entre locais", "sinal": "⇄", "fator": 0},
}


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS movimentacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            insumo_id INTEGER NOT NULL REFERENCES insumos(id) ON DELETE CASCADE,
            tipo TEXT NOT NULL,
            quantidade REAL NOT NULL,
            unidade TEXT NOT NULL,
            motivo TEXT NOT NULL DEFAULT '',
            local_origem TEXT NOT NULL DEFAULT '',
            local_destino TEXT NOT NULL DEFAULT '',
            responsavel TEXT NOT NULL DEFAULT '',
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
        return config.hoje().strftime("%Y-%m")


@bp.route("/movimentacoes", methods=["GET", "POST"])
def movimentacoes():
    conn = get_connection()
    erro = None
    form = request.form
    if request.method == "POST":
        tipo = form.get("tipo", "")
        insumo = conn.execute("SELECT * FROM insumos WHERE id = ?", (form.get("insumo_id", type=int),)).fetchone()
        data = form.get("data", "")
        unidade = form.get("unidade", "").strip()
        motivo = form.get("motivo", "").strip()
        try:
            quantidade = parse_quantidade(form.get("quantidade"))
        except ValueError:
            quantidade = None
        try:
            datetime.strptime(data, "%Y-%m-%d")
        except ValueError:
            erro = "Informe uma data válida."
        if tipo not in TIPOS:
            erro = "Escolha o tipo de movimentação."
        elif insumo is None:
            erro = "Escolha o insumo."
        elif not quantidade:
            erro = "Informe uma quantidade maior que zero."
        elif TIPOS[tipo].get("justificar") and not motivo:
            erro = "Ajuste precisa de justificativa: escreva o motivo."
        elif tipo == "transferencia" and not form.get("local_destino", "").strip():
            erro = "Informe para onde o insumo foi transferido."
        elif unidade and converter(1, unidade, insumo["unidade"],
                                   carregar_conversoes(conn).get(insumo["id"], [])) is None:
            erro = (f"{unidade} não converte para {insumo['unidade']}. Cadastre a medida na ficha do insumo "
                    f"ou use {insumo['unidade']}.")
        if not erro:
            conn.execute("""
                INSERT INTO movimentacoes (data, insumo_id, tipo, quantidade, unidade, motivo, local_origem,
                                           local_destino, responsavel, criado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data, insumo["id"], tipo, quantidade, unidade or insumo["unidade"], motivo,
                form.get("local_origem", "").strip() or insumo["local"], form.get("local_destino", "").strip(),
                session.get("nome", ""), config.agora().strftime("%Y-%m-%d %H:%M:%S"),
            ))
            if tipo == "transferencia" and form.get("mudar_local"):
                conn.execute("UPDATE insumos SET local = ? WHERE id = ?",
                             (form.get("local_destino").strip(), insumo["id"]))
            conn.commit()
            conn.close()
            return redirect(url_for("movimentos.movimentacoes", mes=data[:7], salvo=1, tipo=tipo))

    mes = mes_selecionado()
    filtro_tipo = request.args.get("filtro", "")
    sql = """
        SELECT m.*, i.nome AS insumo_nome FROM movimentacoes m
        JOIN insumos i ON i.id = m.insumo_id
        WHERE substr(m.data, 1, 7) = ?
    """
    parametros = [mes]
    if filtro_tipo in TIPOS:
        sql += " AND m.tipo = ?"
        parametros.append(filtro_tipo)
    registros = conn.execute(sql + " ORDER BY m.data DESC, m.id DESC", parametros).fetchall()
    grupos = insumos_para_formulario(conn)
    locais = sorted({r["local"] for r in conn.execute("SELECT DISTINCT local FROM insumos WHERE local != ''")})
    conn.close()
    return render_template(
        "movimentacoes.html", tipos=TIPOS, grupos=grupos, registros=registros, mes=mes, erro=erro, form=form,
        tipo_padrao=form.get("tipo") or request.args.get("tipo", "saida"), filtro=filtro_tipo, locais=locais,
        unidades=UNIDADES_COMUNS, data_padrao=form.get("data") or config.hoje().isoformat(),
        salvo=request.args.get("salvo"),
    )


@bp.route("/movimentacoes/<int:id>/excluir", methods=["POST"])
def excluir(id):
    # Excluir mexe no saldo: só a gerência
    if not session.get("gerente"):
        return redirect(url_for("gerencia", proximo=url_for("movimentos.movimentacoes")))
    conn = get_connection()
    conn.execute("DELETE FROM movimentacoes WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("movimentos.movimentacoes", mes=request.form.get("mes", "")))
