# insumo_cadastro.py
# Ficha de cada insumo: código, marca, fornecedor, local, estoque mínimo e ideal, custo de referência,
# situação (ativo/inativo), medidas de compra ("1 saco = 5 kg") e histórico de movimentações.
import csv
import io
import json

from flask import Blueprint, Response, abort, redirect, render_template, request, url_for

from contagem import agrupar_por_categoria, formatar_quantidade, get_connection, lista_categorias, parse_quantidade
from compras import parse_valor
from unidades import UNIDADES_COMUNS, converter_fixo, unidades_do_insumo

bp = Blueprint("insumo", __name__)

LOCAIS_SUGERIDOS = ["Geladeira", "Freezer", "Câmara fria", "Despensa", "Estoque seco", "Bar", "Cozinha"]


def carregar_conversoes(conn):
    """{insumo_id: [(unidade, fator, unidade_base)]}"""
    por_insumo = {}
    for c in conn.execute("SELECT insumo_id, unidade, fator, unidade_base FROM insumo_conversoes ORDER BY unidade"):
        por_insumo.setdefault(c["insumo_id"], []).append((c["unidade"], c["fator"], c["unidade_base"]))
    return por_insumo


def insumos_para_formulario(conn, so_ativos=True):
    """Insumos agrupados por categoria, cada um com as medidas que aceita (para o select de unidade)."""
    conversoes = carregar_conversoes(conn)
    sql = "SELECT * FROM insumos" + (" WHERE ativo = 1" if so_ativos else "")
    linhas = []
    for insumo in conn.execute(sql).fetchall():
        item = dict(insumo)
        conv = conversoes.get(insumo["id"], [])
        item["unidades_json"] = json.dumps(unidades_do_insumo(insumo["unidade"], conv))
        item["conv_json"] = json.dumps({u: [f, b] for u, f, b in conv})
        linhas.append(item)
    return agrupar_por_categoria(linhas)


def numero_opcional(texto):
    texto = (texto or "").strip()
    if not texto:
        return None
    valor = parse_quantidade(texto)
    return valor


@bp.route("/insumos/<int:id>", methods=["GET", "POST"])
def editar(id):
    conn = get_connection()
    insumo = conn.execute("SELECT * FROM insumos WHERE id = ?", (id,)).fetchone()
    if insumo is None:
        conn.close()
        abort(404)
    erro = None
    form = request.form
    if request.method == "POST":
        nome = form.get("nome", "").strip()
        try:
            minimo = numero_opcional(form.get("minimo"))
            ideal = numero_opcional(form.get("ideal"))
        except ValueError:
            minimo = ideal = None
            erro = "Estoque mínimo e ideal precisam ser números, ex.: 2,5."
        try:
            custo = parse_valor(form.get("custo"))
        except ValueError:
            custo = None
            erro = "Custo de referência inválido. Use só números, ex.: 32,90."
        if not nome:
            erro = "O nome do insumo é obrigatório."
        elif not form.get("categoria", "").strip():
            erro = "Escolha a categoria."
        elif not erro and minimo is not None and ideal is not None and ideal < minimo:
            erro = "O estoque ideal não pode ser menor que o mínimo."
        elif not erro and conn.execute("SELECT 1 FROM insumos WHERE nome = ? AND id != ?", (nome, id)).fetchone():
            erro = f"Já existe outro insumo chamado '{nome}'."
        if not erro:
            conn.execute("""
                UPDATE insumos SET nome = ?, categoria = ?, unidade = ?, codigo = ?, marca = ?, fornecedor = ?,
                       local = ?, minimo = ?, ideal = ?, custo = ?, observacao = ?, ativo = ?
                WHERE id = ?
            """, (
                nome, form.get("categoria").strip(), form.get("unidade", "").strip() or insumo["unidade"],
                form.get("codigo", "").strip(), form.get("marca", "").strip(), form.get("fornecedor", "").strip(),
                form.get("local", "").strip(), minimo, ideal, custo, form.get("observacao", "").strip(),
                1 if form.get("ativo") else 0, id,
            ))
            conn.commit()
            conn.close()
            return redirect(url_for("insumo.editar", id=id, salvo=1))

    conversoes = conn.execute("SELECT * FROM insumo_conversoes WHERE insumo_id = ? ORDER BY unidade", (id,)).fetchall()
    categorias = lista_categorias(agrupar_por_categoria(conn.execute("SELECT * FROM insumos").fetchall()))
    locais = sorted({r["local"] for r in conn.execute("SELECT DISTINCT local FROM insumos WHERE local != ''")}
                    | set(LOCAIS_SUGERIDOS))
    conn.close()
    if request.method == "POST":
        valores = {k: form.get(k, "") for k in insumo.keys()}
        valores["ativo"] = 1 if form.get("ativo") else 0
    else:
        valores = dict(insumo)
        for campo in ("minimo", "ideal"):
            valores[campo] = formatar_quantidade(insumo[campo]) if insumo[campo] is not None else ""
        valores["custo"] = f"{insumo['custo']:.2f}".replace(".", ",") if insumo["custo"] is not None else ""
    return render_template(
        "insumo_editar.html", insumo=insumo, form=valores, erro=erro,
        conversoes=conversoes, categorias=categorias, locais=locais, unidades=UNIDADES_COMUNS,
        salvo=request.args.get("salvo"), erro_conversao=request.args.get("erro_conversao"),
    )


@bp.route("/insumos/<int:id>/medidas", methods=["POST"])
def adicionar_conversao(id):
    conn = get_connection()
    insumo = conn.execute("SELECT * FROM insumos WHERE id = ?", (id,)).fetchone()
    if insumo is None:
        conn.close()
        abort(404)
    unidade = request.form.get("unidade", "").strip()
    base = request.form.get("unidade_base", "").strip() or insumo["unidade"]
    try:
        fator = parse_quantidade(request.form.get("fator"))
    except ValueError:
        fator = None
    erro = None
    if not unidade:
        erro = "Escreva o nome da medida, ex.: saco, peça, fardo."
    elif not fator:
        erro = "Informe quanto vale 1 " + unidade + ", ex.: 5."
    elif unidade == base or converter_fixo(1, unidade, base) is not None:
        erro = f"{unidade} já converte sozinho para {base}, não precisa cadastrar."
    elif converter_fixo(1, base, insumo["unidade"]) is None:
        erro = (f"A medida precisa valer em {insumo['unidade']} (a unidade do estoque) ou numa unidade que "
                f"converte para ela. {base} não converte para {insumo['unidade']} sem uma regra.")
    if erro:
        conn.close()
        return redirect(url_for("insumo.editar", id=id, erro_conversao=erro) + "#medidas")
    conn.execute("""
        INSERT INTO insumo_conversoes (insumo_id, unidade, fator, unidade_base) VALUES (?, ?, ?, ?)
        ON CONFLICT (insumo_id, unidade) DO UPDATE SET fator = excluded.fator, unidade_base = excluded.unidade_base
    """, (id, unidade, fator, base))
    conn.commit()
    conn.close()
    return redirect(url_for("insumo.editar", id=id) + "#medidas")


@bp.route("/insumos/<int:id>/medidas/<int:conversao_id>/excluir", methods=["POST"])
def excluir_conversao(id, conversao_id):
    conn = get_connection()
    conn.execute("DELETE FROM insumo_conversoes WHERE id = ? AND insumo_id = ?", (conversao_id, id))
    conn.commit()
    conn.close()
    return redirect(url_for("insumo.editar", id=id) + "#medidas")


# ---------- Histórico de movimentações ----------

def historico_do_insumo(conn, insumo_id):
    """Tudo que mexeu no estoque do insumo, do mais novo para o mais antigo."""
    eventos = []
    for r in conn.execute("""
        SELECT c.id, c.data, c.responsavel, c.finalizada, ci.quantidade, ci.unidade, ci.observacao
        FROM contagem_itens ci JOIN contagens c ON c.id = ci.contagem_id
        WHERE ci.insumo_id = ? AND ci.quantidade IS NOT NULL
    """, (insumo_id,)):
        eventos.append({"data": r["data"], "tipo": "Contagem" + ("" if r["finalizada"] else " (em andamento)"),
                        "sinal": "=", "quantidade": r["quantidade"], "unidade": r["unidade"],
                        "quem": r["responsavel"], "detalhe": r["observacao"], "ordem": 0})
    for r in conn.execute("SELECT * FROM compras WHERE insumo_id = ?", (insumo_id,)):
        detalhe = " · ".join(x for x in (r["fornecedor"], dict(r).get("observacao") or "") if x)
        eventos.append({"data": r["data"], "tipo": "Compra", "sinal": "+", "quantidade": r["quantidade"],
                        "unidade": r["unidade"], "quem": dict(r).get("registrado_por") or "",
                        "detalhe": detalhe, "valor": r["valor_total"], "ordem": 1})
    for r in conn.execute("SELECT * FROM desperdicios WHERE insumo_id = ?", (insumo_id,)):
        situacao = {"aprovado": "", "pendente": " (aguardando gerência)", "recusado": " (recusado)"}
        eventos.append({"data": r["data"], "tipo": "Perda / desperdício" + situacao.get(r["status"], ""),
                        "sinal": "−" if r["status"] == "aprovado" else "", "quantidade": r["quantidade"],
                        "unidade": r["unidade"], "quem": r["responsavel"], "detalhe": r["motivo"], "ordem": 1})
    from movimentos import TIPOS
    for r in conn.execute("SELECT * FROM movimentacoes WHERE insumo_id = ?", (insumo_id,)):
        tipo = TIPOS.get(r["tipo"], {"nome": r["tipo"], "sinal": ""})
        eventos.append({"data": r["data"], "tipo": tipo["nome"], "sinal": tipo["sinal"],
                        "quantidade": r["quantidade"], "unidade": r["unidade"], "quem": r["responsavel"],
                        "detalhe": r["motivo"], "ordem": 1})
    eventos.sort(key=lambda e: (e["data"], e["ordem"]), reverse=True)
    return eventos


@bp.route("/insumos/<int:id>/historico")
def historico(id):
    conn = get_connection()
    insumo = conn.execute("SELECT * FROM insumos WHERE id = ?", (id,)).fetchone()
    if insumo is None:
        conn.close()
        abort(404)
    eventos = historico_do_insumo(conn, id)
    conn.close()
    from relatorio import calcular_linhas
    linha = next((l for l in calcular_linhas() if l["id"] == id), None)
    return render_template("insumo_historico.html", insumo=insumo, eventos=eventos, linha=linha)


@bp.route("/insumos/<int:id>/historico.csv")
def historico_csv(id):
    conn = get_connection()
    insumo = conn.execute("SELECT * FROM insumos WHERE id = ?", (id,)).fetchone()
    if insumo is None:
        conn.close()
        abort(404)
    eventos = historico_do_insumo(conn, id)
    conn.close()
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow(["Data", "Movimentação", "Sinal", "Quantidade", "Unidade", "Responsável", "Detalhe"])
    for e in eventos:
        escritor.writerow([e["data"], e["tipo"], e["sinal"], str(e["quantidade"]).replace(".", ","), e["unidade"],
                           e["quem"], e["detalhe"]])
    nome = f"historico_{insumo['id']}.csv"
    return Response("﻿" + saida.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={nome}"})
