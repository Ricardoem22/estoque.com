# contagem.py
# Módulo de contagem de estoque (insumos do restaurante).
import csv
import io
import sqlite3
from datetime import datetime
from itertools import groupby

from flask import Blueprint, Response, abort, redirect, render_template, request, url_for

import config
from importador import EXTENSOES, chave_nome, extrair_itens, ler_arquivo, sem_acento
from insumos_iniciais import CATEGORIAS, UNIDADES

DB_NAME = config.DB_PATH

bp = Blueprint("contagem", __name__)


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS insumos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            categoria TEXT NOT NULL,
            unidade TEXT NOT NULL DEFAULT 'un',
            ordem INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS contagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            responsavel TEXT NOT NULL,
            finalizada INTEGER NOT NULL DEFAULT 0,
            criada_em TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS contagem_itens (
            contagem_id INTEGER NOT NULL REFERENCES contagens(id) ON DELETE CASCADE,
            insumo_id INTEGER NOT NULL REFERENCES insumos(id) ON DELETE CASCADE,
            unidade TEXT NOT NULL,
            quantidade REAL,
            observacao TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (contagem_id, insumo_id)
        );
    """)
    # Cadastro completo do insumo (requisitos do restaurante)
    colunas = {c["name"] for c in conn.execute("PRAGMA table_info(insumos)")}
    for coluna, tipo in (("codigo", "TEXT NOT NULL DEFAULT ''"), ("marca", "TEXT NOT NULL DEFAULT ''"),
                         ("fornecedor", "TEXT NOT NULL DEFAULT ''"), ("local", "TEXT NOT NULL DEFAULT ''"),
                         ("minimo", "REAL"), ("ideal", "REAL"), ("custo", "REAL"),
                         ("observacao", "TEXT NOT NULL DEFAULT ''"), ("ativo", "INTEGER NOT NULL DEFAULT 1"),
                         ("ncm", "TEXT NOT NULL DEFAULT ''")):
        if coluna not in colunas:
            conn.execute(f"ALTER TABLE insumos ADD COLUMN {coluna} {tipo}")
    # Medidas de compra de cada insumo: 1 <unidade> = <fator> <unidade_base>
    conn.execute("""
        CREATE TABLE IF NOT EXISTS insumo_conversoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            insumo_id INTEGER NOT NULL REFERENCES insumos(id) ON DELETE CASCADE,
            unidade TEXT NOT NULL,
            fator REAL NOT NULL,
            unidade_base TEXT NOT NULL,
            UNIQUE (insumo_id, unidade)
        )
    """)
    # Popula os insumos da planilha na primeira execução
    if conn.execute("SELECT COUNT(*) FROM insumos").fetchone()[0] == 0:
        ordem = 0
        for categoria, unidade, nomes in CATEGORIAS:
            for nome in nomes:
                ordem += 1
                conn.execute(
                    "INSERT INTO insumos (nome, categoria, unidade, ordem) VALUES (?, ?, ?, ?)",
                    (nome, categoria, unidade, ordem)
                )
    conn.commit()
    conn.close()


def ordem_categorias():
    return {categoria: i for i, (categoria, _, _) in enumerate(CATEGORIAS)}


def agrupar_por_categoria(linhas):
    ordem = ordem_categorias()
    linhas = sorted(linhas, key=lambda l: (ordem.get(l["categoria"], len(ordem)), l["categoria"], l["nome"]))
    return [(cat, list(itens)) for cat, itens in groupby(linhas, key=lambda l: l["categoria"])]


def parse_quantidade(valor):
    """Aceita '1,5', '1.5', '1.250,5' e também com a unidade junto: '4,5 kg' vale 4,5. None se vazio."""
    import re
    from importador import _unidade_antes, normalizar_unidade
    valor = (valor or "").strip()
    if not valor:
        return None
    valor = _unidade_antes(valor)[0]  # "kg 4,5"
    m = re.fullmatch(r"(\d[\d.,\s]*?)\s*([^\W\d_]+)\.?", valor)
    if m and normalizar_unidade(m.group(2)):
        valor = m.group(1)
    valor = valor.replace(" ", "")
    # "1.250,5" (ponto de milhar com vírgula decimal); sem vírgula, o ponto é decimal: "1.5" = 1,5
    valor = valor.replace(".", "").replace(",", ".") if "," in valor and "." in valor else valor.replace(",", ".")
    quantidade = float(valor)
    if quantidade < 0:
        raise ValueError
    return quantidade


def unidade_digitada(valor, outra=""):
    """A unidade escrita junto da quantidade ('4,5 kg' -> 'kg') vale mais que a do seletor ao lado."""
    from importador import separar_quantidade
    return separar_quantidade(valor or "")[1] or (outra or "").strip()


def formatar_quantidade(valor):
    if valor is None:
        return ""
    if float(valor).is_integer():
        return str(int(valor))
    return f"{valor:.3f}".rstrip("0").replace(".", ",")


def carregar_contagem(conn, contagem_id):
    contagem = conn.execute("SELECT * FROM contagens WHERE id = ?", (contagem_id,)).fetchone()
    if contagem is None:
        conn.close()
        abort(404)
    return contagem


def itens_da_contagem(conn, contagem_id):
    return conn.execute("""
        SELECT i.id, i.nome, i.categoria,
               COALESCE(ci.unidade, i.unidade) AS unidade,
               ci.quantidade, COALESCE(ci.observacao, '') AS observacao
        FROM insumos i
        LEFT JOIN contagem_itens ci ON ci.insumo_id = i.id AND ci.contagem_id = ?
        WHERE i.ativo = 1 OR ci.quantidade IS NOT NULL
    """, (contagem_id,)).fetchall()


@bp.app_template_filter("qtd")
def qtd_filter(valor):
    return formatar_quantidade(valor)


@bp.app_template_filter("data_br")
def data_br_filter(valor):
    try:
        return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return valor


# ---------- Contagens ----------

@bp.route("/contagens")
def contagens():
    conn = get_connection()
    lista = conn.execute("""
        SELECT c.*,
               (SELECT COUNT(*) FROM contagem_itens ci
                WHERE ci.contagem_id = c.id AND ci.quantidade IS NOT NULL) AS contados
        FROM contagens c
        ORDER BY c.data DESC, c.id DESC
    """).fetchall()
    total_insumos = conn.execute("SELECT COUNT(*) FROM insumos WHERE ativo = 1").fetchone()[0]
    conn.close()
    return render_template("contagens.html", contagens=lista, total_insumos=total_insumos)


@bp.route("/contagens/nova", methods=["GET", "POST"])
def nova_contagem():
    erro = None
    data = request.form.get("data", config.hoje().isoformat())
    responsavel = request.form.get("responsavel", "").strip()

    if request.method == "POST":
        try:
            datetime.strptime(data, "%Y-%m-%d")
        except ValueError:
            erro = "Informe uma data válida."
        if not responsavel:
            erro = "Informe o nome do responsável."

        if not erro:
            conn = get_connection()
            cur = conn.execute(
                "INSERT INTO contagens (data, responsavel, criada_em) VALUES (?, ?, ?)",
                (data, responsavel, config.agora().strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            contagem_id = cur.lastrowid
            conn.close()
            return redirect(url_for("contagem.contar", id=contagem_id))

    return render_template("nova_contagem.html", erro=erro, data=data, responsavel=responsavel)


@bp.route("/contagens/<int:id>", methods=["GET", "POST"])
def contar(id):
    conn = get_connection()
    contagem = carregar_contagem(conn, id)
    erros = []

    if request.method == "POST":
        insumos = conn.execute("SELECT id, nome, unidade FROM insumos").fetchall()
        for insumo in insumos:
            iid = insumo["id"]
            if f"qtd_{iid}" not in request.form:
                continue
            try:
                quantidade = parse_quantidade(request.form.get(f"qtd_{iid}"))
            except ValueError:
                erros.append(f"Quantidade inválida para {insumo['nome']}.")
                continue
            unidade = unidade_digitada(request.form.get(f"qtd_{iid}"), request.form.get(f"un_{iid}")) or insumo["unidade"]
            observacao = request.form.get(f"obs_{iid}", "").strip()
            conn.execute("""
                INSERT INTO contagem_itens (contagem_id, insumo_id, unidade, quantidade, observacao)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (contagem_id, insumo_id) DO UPDATE SET
                    unidade = excluded.unidade,
                    quantidade = excluded.quantidade,
                    observacao = excluded.observacao
            """, (id, iid, unidade, quantidade, observacao))
            # A unidade escolhida vira o padrão para as próximas contagens
            conn.execute("UPDATE insumos SET unidade = ? WHERE id = ?", (unidade, iid))

        if not erros:
            finalizar = request.form.get("acao") == "finalizar"
            if finalizar:
                conn.execute("UPDATE contagens SET finalizada = 1 WHERE id = ?", (id,))
            conn.commit()
            conn.close()
            if finalizar:
                return redirect(url_for("contagem.ver_contagem", id=id))
            return redirect(url_for("contagem.contar", id=id, salvo=1))
        conn.rollback()

    grupos = agrupar_por_categoria(itens_da_contagem(conn, id))
    conn.close()
    return render_template(
        "contar.html", contagem=contagem, grupos=grupos, unidades=UNIDADES,
        erros=erros, salvo=request.args.get("salvo"), importados=request.args.get("importados"),
    )


def salvar_item(conn, contagem_id, insumo_id, quantidade, unidade, observacao=None):
    """Grava a quantidade do insumo na contagem, mantendo a observação se não vier outra."""
    conn.execute("""
        INSERT INTO contagem_itens (contagem_id, insumo_id, unidade, quantidade, observacao)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (contagem_id, insumo_id) DO UPDATE SET
            unidade = excluded.unidade,
            quantidade = excluded.quantidade,
            observacao = COALESCE(?, contagem_itens.observacao)
    """, (contagem_id, insumo_id, unidade, quantidade, observacao or "", observacao))
    # A unidade escolhida vira o padrão para as próximas contagens
    conn.execute("UPDATE insumos SET unidade = ? WHERE id = ?", (unidade, insumo_id))


PALAVRAS_VAZIAS = {"de", "do", "da", "dos", "das", "com", "e", "p", "para", "em"}


def insumos_parecidos(nome, insumos, usados=()):
    """Insumos cujo nome contém todas as palavras do nome do arquivo, ou o contrário:
    "Bife do Vazio" → "Bife do Vazio Empanado". Os mais próximos primeiro.
    Devolve (lista, sugestão): a sugestão só existe quando um único insumo contém o nome do arquivo inteiro."""
    palavras = set(chave_nome(nome).split()) - PALAVRAS_VAZIAS
    if not palavras:
        return []
    achados = []
    for insumo in insumos:
        if insumo["id"] in usados:
            continue
        outras = set(chave_nome(insumo["nome"]).split()) - PALAVRAS_VAZIAS
        if outras and (palavras <= outras or outras <= palavras):
            achados.append((len(palavras ^ outras), insumo["nome"].lower(), insumo, palavras <= outras))
    achados.sort(key=lambda a: a[:2])
    contem = [a[2] for a in achados if a[3]]
    return [a[2] for a in achados][:5], (contem[0] if len(contem) == 1 else None)


def unidade_do_arquivo(item, insumo):
    """Unidade com que o item do arquivo entra no insumo. A coluna "Un" do arquivo (muitas vezes a do sistema
    de vendas) não muda a unidade do insumo quando não converte: "Bife do Vazio Empanado | un | 4,5" num insumo
    em kg entra como 4,5 kg. Unidade escrita junto do número ("4,5 kg") ou que converte (g -> kg) é mantida."""
    from unidades import converter_fixo
    unidade = item["unidade"]
    if not unidade:
        return insumo["unidade"]
    if item.get("unidade_na_qtd") or converter_fixo(1, unidade, insumo["unidade"]) is not None:
        return unidade
    return insumo["unidade"]


@bp.route("/contagens/<int:id>/importar", methods=["GET", "POST"])
def importar_contagem(id):
    conn = get_connection()
    contagem = carregar_contagem(conn, id)
    insumos = conn.execute("SELECT * FROM insumos").fetchall()
    conn.close()
    if contagem["finalizada"]:
        return redirect(url_for("contagem.ver_contagem", id=id))

    categorias = lista_categorias(agrupar_por_categoria(insumos))
    erro = None
    encontrados = novos = None
    sem_quantidade = 0

    if request.method == "POST":
        arquivo = request.files.get("arquivo")
        if not arquivo or not arquivo.filename:
            erro = "Escolha um arquivo."
        else:
            try:
                itens = extrair_itens(ler_arquivo(arquivo.filename, arquivo.read()), categorias)
            except ValueError as e:
                itens, erro = [], str(e)
            except Exception:
                itens, erro = [], "Não consegui ler esse arquivo. Confira se ele não está corrompido ou protegido por senha."
            com_quantidade = [i for i in itens if i["quantidade"] is not None]
            sem_quantidade = len(itens) - len(com_quantidade)
            if not erro and not com_quantidade:
                erro = ("Não encontrei quantidades nesse arquivo. Se for um PDF escaneado (foto de papel), "
                        "ele não tem texto para ler.")
            por_nome = {chave_nome(i["nome"]): i for i in insumos}
            encontrados, novos = [], []
            for item in com_quantidade:
                insumo = por_nome.get(chave_nome(item["nome"]))
                if insumo:
                    item["insumo"] = insumo
                    item["unidade"] = unidade_do_arquivo(item, insumo)
                    encontrados.append(item)
                else:
                    item["categoria"] = item["categoria"] or categorias[0]
                    item["unidade"] = item["unidade"] or unidade_padrao(item["categoria"])
                    novos.append(item)
            # Nome diferente do cadastro ("Bife do Vazio" x "Bife do Vazio Empanado"): sugere o parecido
            usados = {i["insumo"]["id"] for i in encontrados}
            ativos = [i for i in insumos if i["ativo"]]
            for item in novos:
                item["parecidos"], item["sugestao"] = insumos_parecidos(item["nome"], ativos, usados)
            # Dois nomes do arquivo apontando para o mesmo insumo: nenhum vem escolhido
            vezes = {}
            for item in novos:
                if item["sugestao"]:
                    vezes[item["sugestao"]["id"]] = vezes.get(item["sugestao"]["id"], 0) + 1
            for item in novos:
                if item["sugestao"] and vezes[item["sugestao"]["id"]] > 1:
                    item["sugestao"] = None
                item["unidade_arquivo"] = item["unidade"]
                if item["sugestao"]:
                    item["unidade"] = unidade_do_arquivo(item, item["sugestao"])
            if erro:
                encontrados = novos = None
            elif novos:
                categorias += sorted({i["categoria"] for i in novos if i["categoria"] not in categorias})

    return render_template(
        "importar_contagem.html", contagem=contagem, erro=erro, encontrados=encontrados, novos=novos,
        sem_quantidade=sem_quantidade, categorias=categorias, unidades=UNIDADES,
        extensoes=", ".join(sorted("." + e for e in EXTENSOES)),
    )


@bp.route("/contagens/<int:id>/importar/confirmar", methods=["POST"])
def confirmar_importacao_contagem(id):
    conn = get_connection()
    contagem = carregar_contagem(conn, id)
    if contagem["finalizada"]:
        conn.close()
        return redirect(url_for("contagem.ver_contagem", id=id))
    form = request.form
    preenchidos = 0
    for i in range(form.get("total", 0, type=int)):
        try:
            quantidade = parse_quantidade(form.get(f"qtd_{i}"))
        except ValueError:
            continue
        if quantidade is None:
            continue
        unidade = unidade_digitada(form.get(f"qtd_{i}"), form.get(f"unidade_{i}")) or "un"
        observacao = form.get(f"obs_{i}", "").strip() or None
        insumo_id = form.get(f"insumo_{i}", type=int)
        destino = form.get(f"destino_{i}", "")
        if destino.isdigit():
            insumo_id = int(destino)
        if (form.get(f"incluir_{i}") or destino.isdigit()) and insumo_id:
            if conn.execute("SELECT 1 FROM insumos WHERE id = ?", (insumo_id,)).fetchone():
                salvar_item(conn, id, insumo_id, quantidade, unidade, observacao)
                preenchidos += 1
        elif form.get(f"criar_{i}") or destino == "novo":
            nome = form.get(f"nome_{i}", "").strip()
            categoria = form.get(f"categoria_{i}", "").strip()
            if not nome or not categoria:
                continue
            existente = conn.execute("SELECT id FROM insumos WHERE nome = ?", (nome,)).fetchone()
            if existente:
                novo_id = existente["id"]
            else:
                novo_id = conn.execute("INSERT INTO insumos (nome, categoria, unidade) VALUES (?, ?, ?)",
                                       (nome, categoria, unidade)).lastrowid
            salvar_item(conn, id, novo_id, quantidade, unidade, observacao)
            preenchidos += 1
    conn.commit()
    conn.close()
    return redirect(url_for("contagem.contar", id=id, importados=preenchidos))


@bp.route("/contagens/<int:id>/ver")
def ver_contagem(id):
    conn = get_connection()
    contagem = carregar_contagem(conn, id)
    grupos = agrupar_por_categoria(itens_da_contagem(conn, id))
    conn.close()
    from relatorio import divergencias
    sistema, resumo = divergencias(contagem)
    return render_template("ver_contagem.html", contagem=contagem, grupos=grupos, sistema=sistema, resumo=resumo)


@bp.route("/contagens/<int:id>/reabrir", methods=["POST"])
def reabrir_contagem(id):
    conn = get_connection()
    conn.execute("UPDATE contagens SET finalizada = 0 WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("contagem.contar", id=id))


@bp.route("/contagens/<int:id>/excluir", methods=["POST"])
def excluir_contagem(id):
    conn = get_connection()
    conn.execute("DELETE FROM contagens WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("contagem.contagens"))


@bp.route("/contagens/<int:id>/csv")
def exportar_csv(id):
    conn = get_connection()
    contagem = carregar_contagem(conn, id)
    grupos = agrupar_por_categoria(itens_da_contagem(conn, id))
    conn.close()
    from relatorio import divergencias
    sistema, _ = divergencias(contagem)

    saida = io.StringIO()
    writer = csv.writer(saida, delimiter=";")
    writer.writerow(["Data da contagem", data_br_filter(contagem["data"]), "Responsável", contagem["responsavel"]])
    writer.writerow([])
    writer.writerow(["Categoria", "Insumo", "Unidade", "Qtd. Contada", "No sistema", "Diferença",
                     "Valor da diferença (R$)", "Observações / Validade"])
    for categoria, itens in grupos:
        for item in itens:
            d = sistema.get(item["id"], {})
            writer.writerow([
                categoria, item["nome"], item["unidade"], formatar_quantidade(item["quantidade"]),
                formatar_quantidade(d.get("esperado")), formatar_quantidade(d.get("diferenca")),
                f"{d['valor']:.2f}".replace(".", ",") if d.get("valor") is not None else "", item["observacao"],
            ])

    nome_arquivo = f"contagem_{contagem['data']}_{id}.csv"
    # BOM para o Excel reconhecer os acentos
    return Response(
        "﻿" + saida.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )


# ---------- Insumos ----------

@bp.route("/insumos", methods=["GET", "POST"])
def insumos():
    erro = None
    conn = get_connection()

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        categoria = request.form.get("categoria", "").strip()
        unidade = request.form.get("unidade", "un").strip() or "un"
        if not nome:
            erro = "O nome do insumo é obrigatório."
        elif not categoria:
            erro = "Escolha a categoria."
        else:
            try:
                conn.execute(
                    "INSERT INTO insumos (nome, categoria, unidade) VALUES (?, ?, ?)",
                    (nome, categoria, unidade)
                )
                conn.commit()
                conn.close()
                return redirect(url_for("contagem.insumos"))
            except sqlite3.IntegrityError:
                erro = f"O insumo '{nome}' já está cadastrado."

    grupos = agrupar_por_categoria(conn.execute("SELECT * FROM insumos").fetchall())
    conn.close()
    categorias = lista_categorias(grupos)
    return render_template(
        "insumos.html", grupos=grupos, categorias=categorias, unidades=UNIDADES, erro=erro,
        importados=request.args.get("importados"),
    )


def lista_categorias(grupos):
    categorias = [c for c, _, _ in CATEGORIAS]
    return categorias + [c for c, _ in grupos if c not in categorias]


def unidade_padrao(categoria):
    for nome, unidade, _ in CATEGORIAS:
        if nome == categoria:
            return unidade
    return "un"


@bp.route("/insumos/importar", methods=["GET", "POST"])
def importar_insumos():
    conn = get_connection()
    existentes = conn.execute("SELECT * FROM insumos").fetchall()
    conn.close()
    categorias = lista_categorias(agrupar_por_categoria(existentes))
    erro = None
    itens = None
    padrao = request.form.get("categoria_padrao") or categorias[0]

    if request.method == "POST":
        arquivo = request.files.get("arquivo")
        if not arquivo or not arquivo.filename:
            erro = "Escolha um arquivo."
        else:
            try:
                linhas = ler_arquivo(arquivo.filename, arquivo.read())
                itens = extrair_itens(linhas, categorias)
                if not itens:
                    erro = ("Não encontrei nenhum insumo nesse arquivo. Se for um PDF escaneado (foto de papel), "
                            "ele não tem texto para ler.")
                    itens = None
            except ValueError as e:
                erro = str(e)
            except Exception:
                erro = "Não consegui ler esse arquivo. Confira se ele não está corrompido ou protegido por senha."

    if itens:
        nomes = {sem_acento(i["nome"]) for i in existentes}
        for item in itens:
            item["existe"] = sem_acento(item["nome"]) in nomes
            if not item["categoria"]:
                item["categoria"] = padrao
            item["unidade"] = item["unidade"] or unidade_padrao(item["categoria"])
        novas = sorted({i["categoria"] for i in itens if i["categoria"] not in categorias})
        categorias = categorias + novas

    return render_template(
        "importar_insumos.html", erro=erro, itens=itens, categorias=categorias, unidades=UNIDADES,
        padrao=padrao, extensoes=", ".join(sorted("." + e for e in EXTENSOES)),
    )


@bp.route("/insumos/importar/confirmar", methods=["POST"])
def confirmar_importacao():
    conn = get_connection()
    nomes = {sem_acento(r["nome"]) for r in conn.execute("SELECT nome FROM insumos")}
    adicionados = 0
    for i in range(request.form.get("total", 0, type=int)):
        if not request.form.get(f"incluir_{i}"):
            continue
        nome = request.form.get(f"nome_{i}", "").strip()
        categoria = request.form.get(f"categoria_{i}", "").strip()
        unidade = request.form.get(f"unidade_{i}", "").strip() or "un"
        if not nome or not categoria or sem_acento(nome) in nomes:
            continue
        conn.execute("INSERT INTO insumos (nome, categoria, unidade) VALUES (?, ?, ?)", (nome, categoria, unidade))
        nomes.add(sem_acento(nome))
        adicionados += 1
    conn.commit()
    conn.close()
    return redirect(url_for("contagem.insumos", importados=adicionados))


@bp.route("/insumos/<int:id>/excluir", methods=["POST"])
def excluir_insumo(id):
    conn = get_connection()
    conn.execute("DELETE FROM insumos WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("contagem.insumos"))
