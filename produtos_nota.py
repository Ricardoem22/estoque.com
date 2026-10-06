# produtos_nota.py
# Cadastra e atualiza produtos (com NCM, código, EAN, unidade e valor) a partir
# da nota fiscal de compra. A leitura do arquivo fica em notas.py.
from flask import Blueprint, redirect, render_template, request, url_for

from compras import parse_valor
import config
from contagem import get_connection, parse_quantidade
from importador import chave_nome
from insumos_iniciais import UNIDADES
from notas import EXTENSOES_NOTA, ler_nota, unidade_do_item

bp = Blueprint("produtos_nota", __name__)


def init_db():
    conn = get_connection()
    # Notas já usadas na aba Produtos, para avisar antes de somar o estoque duas vezes
    conn.execute("""
        CREATE TABLE IF NOT EXISTS produtos_notas (
            chave TEXT PRIMARY KEY,
            numero TEXT NOT NULL DEFAULT '',
            fornecedor TEXT NOT NULL DEFAULT '',
            data TEXT NOT NULL DEFAULT '',
            itens INTEGER NOT NULL DEFAULT 0,
            importada_em TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


@bp.app_template_filter("ncm")
def ncm_filter(ncm):
    """'04021010' -> '0402.10.10'."""
    if ncm and len(ncm) == 8 and ncm.isdigit():
        return f"{ncm[:4]}.{ncm[4:6]}.{ncm[6:]}"
    return ncm or ""


def achar_produto(item, produtos, fornecedor):
    """Produto já cadastrado para o item: mesmo EAN, mesmo código do mesmo fornecedor ou mesmo nome."""
    if item["ean"]:
        for p in produtos:
            if p["ean"] == item["ean"]:
                return p["id"]
    if item["codigo"] and fornecedor:
        for p in produtos:
            if p["codigo"] == item["codigo"] and chave_nome(p["fornecedor"]) == chave_nome(fornecedor):
                return p["id"]
    chave = chave_nome(item["nome"])
    for p in produtos:
        if chave_nome(p["nome"]) == chave:
            return p["id"]
    return None


def numero_br(valor, casas=2):
    if valor is None:
        return ""
    texto = f"{valor:.{casas}f}".rstrip("0").rstrip(".") if casas > 2 else f"{valor:.2f}"
    return texto.replace(".", ",")


@bp.route("/produtos/nota", methods=["GET", "POST"])
def importar_nota():
    conn = get_connection()
    produtos = conn.execute("SELECT * FROM produtos ORDER BY nome COLLATE NOCASE").fetchall()
    erro = None
    nota = None
    ja_importada = None

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
            for item in nota["itens"]:
                item["produto_id"] = achar_produto(item, produtos, nota["fornecedor"])
                item["unidade"] = unidade_do_item(item) or item["unidade_nota"] or "un"
            if nota["chave"]:
                ja_importada = conn.execute("SELECT importada_em FROM produtos_notas WHERE chave = ?",
                                            (nota["chave"],)).fetchone()
    conn.close()
    return render_template(
        "importar_nota_produtos.html", erro=erro, nota=nota, produtos=produtos, unidades=UNIDADES,
        ja_importada=ja_importada, numero_br=numero_br,
        extensoes=", ".join(sorted("." + e for e in EXTENSOES_NOTA)),
    )


@bp.route("/produtos/nota/confirmar", methods=["POST"])
def confirmar_nota():
    form = request.form
    fornecedor = form.get("fornecedor", "").strip()
    somar_estoque = bool(form.get("somar_estoque"))
    atualizar_preco = bool(form.get("atualizar_preco"))
    conn = get_connection()
    novos = atualizados = 0

    for i in range(form.get("total", 0, type=int)):
        destino = form.get(f"produto_{i}", "")
        if not form.get(f"incluir_{i}") or not destino:
            continue
        try:
            quantidade = parse_quantidade(form.get(f"qtd_{i}")) or 0
            preco = parse_valor(form.get(f"valor_{i}"))
        except ValueError:
            continue
        ncm = "".join(c for c in form.get(f"ncm_{i}", "") if c.isdigit())
        caracteristicas = {
            "ncm": ncm if len(ncm) == 8 else "",
            "codigo": form.get(f"codigo_{i}", "").strip(),
            "ean": form.get(f"ean_{i}", "").strip(),
            "unidade": form.get(f"unidade_{i}", "").strip(),
            "fornecedor": fornecedor,
        }

        produto = None
        if destino == "novo":
            nome = form.get(f"novo_nome_{i}", "").strip() or form.get(f"nome_{i}", "").strip()
            if not nome:
                continue
            # Se já existe um produto com esse nome, atualiza ele em vez de duplicar
            produto = conn.execute("SELECT * FROM produtos WHERE nome = ? COLLATE NOCASE", (nome,)).fetchone()
            if produto is None:
                conn.execute(
                    "INSERT INTO produtos (nome, quantidade, preco, ncm, codigo, ean, unidade, fornecedor)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (nome, quantidade if somar_estoque else 0, preco or 0, *caracteristicas.values())
                )
                novos += 1
                continue
        elif destino.isdigit():
            produto = conn.execute("SELECT * FROM produtos WHERE id = ?", (int(destino),)).fetchone()
        if produto is None:
            continue

        # Só troca o que a nota trouxe; campo vazio na nota não apaga o que já estava cadastrado
        mudancas = {k: v for k, v in caracteristicas.items() if v}
        if atualizar_preco and preco is not None:
            mudancas["preco"] = preco
        if somar_estoque:
            mudancas["quantidade"] = (produto["quantidade"] or 0) + quantidade
        if mudancas:
            sets = ", ".join(f"{campo} = ?" for campo in mudancas)
            conn.execute(f"UPDATE produtos SET {sets} WHERE id = ?", (*mudancas.values(), produto["id"]))
        atualizados += 1

    chave = form.get("chave", "").strip()
    if chave and (novos or atualizados):
        conn.execute("""
            INSERT OR REPLACE INTO produtos_notas (chave, numero, fornecedor, data, itens, importada_em)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (chave, form.get("numero", "").strip(), fornecedor, form.get("data", "").strip(),
              novos + atualizados, config.agora().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    return redirect(url_for("index", novos=novos, atualizados=atualizados))
