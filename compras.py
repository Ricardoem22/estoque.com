# compras.py
# Registro das compras (entradas de mercadoria), usado no cálculo do consumo.
from datetime import datetime
import re

from flask import Blueprint, redirect, render_template, request, url_for

from contagem import agrupar_por_categoria, get_connection, lista_categorias, parse_quantidade, unidade_padrao
import config
from importador import chave_nome
from insumos_iniciais import UNIDADES
from notas import EXTENSOES_NOTA, achar_insumo, ler_nota, unidade_do_item

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
    # Chave de acesso (ou número) da nota fiscal de onde a compra veio
    if "nota" not in colunas:
        conn.execute("ALTER TABLE compras ADD COLUMN nota TEXT")
    # Como cada produto da nota foi ligado a um insumo, para a próxima nota já vir ligada
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nota_apelidos (
            chave TEXT PRIMARY KEY,
            insumo_id INTEGER NOT NULL REFERENCES insumos(id) ON DELETE CASCADE
        )
    """)
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
        salvo=request.args.get("salvo"), lancados=request.args.get("lancados", type=int),
    )


@bp.route("/compras/<int:id>/excluir", methods=["POST"])
def excluir_compra(id):
    conn = get_connection()
    conn.execute("DELETE FROM compras WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("compras.compras", mes=request.form.get("mes", "")))


# ---------- Lançar compras pela nota fiscal ----------

@bp.route("/compras/nota", methods=["GET", "POST"])
def importar_nota():
    conn = get_connection()
    insumos = conn.execute("SELECT * FROM insumos ORDER BY nome COLLATE NOCASE").fetchall()
    grupos = agrupar_por_categoria(insumos)
    erro = None
    nota = None
    ja_lancada = None

    if request.method == "POST":
        arquivo = request.files.get("arquivo")
        if not arquivo or not arquivo.filename:
            erro = "Escolha o arquivo da nota."
        else:
            try:
                nota = ler_nota(arquivo.filename, arquivo.read())
                if not nota["itens"]:
                    erro = "Não encontrei itens nessa nota."
            except ValueError as e:
                erro = str(e)
            except Exception:
                erro = "Não consegui ler esse arquivo. Confira se ele não está corrompido ou protegido por senha."
            if erro:
                nota = None
        if nota:
            apelidos = {r["chave"]: r["insumo_id"] for r in conn.execute("SELECT * FROM nota_apelidos")}
            unidade_insumo = {i["id"]: i["unidade"] for i in insumos}
            for item in nota["itens"]:
                item["insumo_id"] = achar_insumo(item["nome"], insumos, apelidos)
                item["unidade"] = unidade_do_item(item) or unidade_insumo.get(item["insumo_id"]) or "un"
            if nota["chave"]:
                ja_lancada = conn.execute("SELECT MIN(data) AS data FROM compras WHERE nota = ?",
                                          (nota["chave"],)).fetchone()["data"]
    conn.close()
    return render_template(
        "importar_nota.html", erro=erro, nota=nota, grupos=grupos, unidades=UNIDADES,
        categorias=lista_categorias(grupos), ja_lancada=ja_lancada, hoje=config.hoje().isoformat(),
        extensoes=", ".join(sorted("." + e for e in EXTENSOES_NOTA)),
    )


@bp.route("/compras/nota/confirmar", methods=["POST"])
def confirmar_nota():
    form = request.form
    data = form.get("data", "")
    try:
        datetime.strptime(data, "%Y-%m-%d")
    except ValueError:
        data = config.hoje().isoformat()
    fornecedor = form.get("fornecedor", "").strip()
    nota = form.get("nota", "").strip() or None
    agora = config.agora().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    lancados = 0
    for i in range(form.get("total", 0, type=int)):
        destino = form.get(f"insumo_{i}", "")
        if not form.get(f"incluir_{i}") or not destino:
            continue
        try:
            quantidade = parse_quantidade(form.get(f"qtd_{i}"))
            valor = parse_valor(form.get(f"valor_{i}"))
        except ValueError:
            continue
        if not quantidade:
            continue
        unidade = form.get(f"unidade_{i}", "").strip() or "un"
        nome_nota = form.get(f"nome_{i}", "").strip()
        if destino == "novo":
            nome = form.get(f"novo_nome_{i}", "").strip() or nome_nota
            categoria = form.get(f"categoria_{i}", "").strip()
            if not nome or not categoria:
                continue
            existente = conn.execute("SELECT id FROM insumos WHERE nome = ?", (nome,)).fetchone()
            insumo_id = existente["id"] if existente else conn.execute(
                "INSERT INTO insumos (nome, categoria, unidade) VALUES (?, ?, ?)",
                (nome, categoria, unidade if unidade else unidade_padrao(categoria))).lastrowid
        else:
            insumo_id = int(destino) if destino.isdigit() else None
            if not insumo_id or not conn.execute("SELECT 1 FROM insumos WHERE id = ?", (insumo_id,)).fetchone():
                continue
        conn.execute("""
            INSERT INTO compras (data, insumo_id, quantidade, unidade, fornecedor, criado_em, valor_total, nota)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (data, insumo_id, quantidade, unidade, fornecedor, agora, valor, nota))
        if nome_nota:
            conn.execute("INSERT OR REPLACE INTO nota_apelidos (chave, insumo_id) VALUES (?, ?)",
                         (chave_nome(nome_nota), insumo_id))
        lancados += 1
    conn.commit()
    conn.close()
    return redirect(url_for("compras.compras", mes=data[:7], lancados=lancados))
