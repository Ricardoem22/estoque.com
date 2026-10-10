# melhor_preco.py
# Busca de melhor preço: a gerência guarda as planilhas de preço dos fornecedores (Koch, SEGS, Delly's...)
# e cola a lista de compras; o app procura cada item em todas as planilhas e mostra o mais barato por kg
# ou por unidade, com o total estimado quando a lista traz a quantidade.
import re

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

import config
from contagem import get_connection
from importador import extrair_itens, ler_arquivo, ler_texto
from insumo_cadastro import ler_planilha_precos
from notas import chave_nome, palavras
from unidades import converter_fixo

bp = Blueprint("precos", __name__)

# Quantas opções de marca/produto mostrar por item
OPCOES = 12


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS precos_fornecedor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fornecedor TEXT NOT NULL,
            produto TEXT NOT NULL,
            preco REAL NOT NULL,
            por TEXT NOT NULL,
            data TEXT NOT NULL DEFAULT '',
            link TEXT NOT NULL DEFAULT '',
            arquivo TEXT NOT NULL DEFAULT '',
            enviado_em TEXT NOT NULL
        )
    """)
    # Marca/produto que a gerência prefere para cada item da lista (mesmo quando não é o mais barato)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS preco_escolhas (
            chave TEXT PRIMARY KEY,
            fornecedor TEXT NOT NULL,
            produto TEXT NOT NULL,
            salvo_em TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def nome_do_arquivo(nome):
    """'precos-koch-site-2026-10-10.xlsx' -> 'Koch Site', usado quando a planilha não tem a coluna Fornecedor."""
    base = re.sub(r"\.\w+$", "", nome or "")
    base = re.sub(r"\d{4}-\d{2}-\d{2}|precos?|preços?", " ", base, flags=re.I)
    base = re.sub(r"[-_]+", " ", base).strip()
    return base.title() or "Fornecedor"


def guardar_planilha(conn, nome_arquivo, dados):
    """Lê a planilha e troca os preços guardados dos fornecedores que aparecem nela. Devolve {fornecedor: linhas}."""
    linhas = [l for l in ler_planilha_precos(dados) if l["preco"] and l["por"] in ("kg", "un")]
    padrao = nome_do_arquivo(nome_arquivo)
    por_fornecedor = {}
    for l in linhas:
        por_fornecedor.setdefault(l["fornecedor"].strip() or padrao, []).append(l)
    agora = config.agora().strftime("%Y-%m-%d %H:%M")
    for fornecedor, itens in por_fornecedor.items():
        conn.execute("DELETE FROM precos_fornecedor WHERE fornecedor = ?", (fornecedor,))
        conn.executemany(
            "INSERT INTO precos_fornecedor (fornecedor, produto, preco, por, data, link, arquivo, enviado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(fornecedor, l["produto"], round(l["preco"], 4), l["por"], l["data"], l.get("link", ""),
              nome_arquivo, agora) for l in itens])
    conn.commit()
    return {f: len(i) for f, i in por_fornecedor.items()}


def resumo_planilhas(conn):
    return conn.execute("""
        SELECT fornecedor, COUNT(*) AS produtos, MAX(data) AS data, MAX(enviado_em) AS enviado_em, MAX(arquivo) AS arquivo
        FROM precos_fornecedor GROUP BY fornecedor ORDER BY fornecedor COLLATE NOCASE
    """).fetchall()


def produtos_do_item(nome, precos):
    """Produtos das planilhas que têm todas as palavras do item, com a primeira palavra do item entre as duas
    primeiras do produto ("Mussarela" acha "Queijo Mussarela Peça"; "Sal" acha "Sal Grosso", não "Margarina com Sal")."""
    alvo = palavras(nome)
    if not alvo:
        return []
    achados = [p for p in precos if alvo <= p["palavras"]]
    primeira = chave_nome(nome).split()[0]
    mesmos = [p for p in achados if primeira in p["chave"].split()[:2]]
    return mesmos or [p for p in achados if len(p["palavras"] - alvo) <= 3]


def quantidade_em(item, por):
    """Quantidade da lista na unidade do preço (kg ou un); None quando não converte."""
    if item["quantidade"] is None:
        return None
    unidade = item.get("unidade") or ""
    if por == "kg":
        return converter_fixo(item["quantidade"], unidade, "kg")
    if por == "un" and unidade in ("un", ""):
        return item["quantidade"]
    return None


def buscar(itens, precos, escolhas=None):
    """Para cada item da lista: as opções de marca/produto, mais barato primeiro, com a marca que a gerência
    escolheu antes já marcada. escolhas: {chave do item: (fornecedor, produto)}."""
    escolhas = escolhas or {}
    linhas, nao_achados = [], []
    for item in itens:
        produtos = produtos_do_item(item["nome"], precos)
        if not produtos:
            nao_achados.append(item)
            continue
        # Compara no jeito que a lista pede (kg ou un); sem unidade, o preço por kg vem primeiro
        por = "un" if (item.get("unidade") or "") == "un" else "kg"
        produtos = sorted(produtos, key=lambda p: (p["por"] != por, p["preco"]))[:OPCOES]
        barato = produtos[0]
        chave = chave_nome(item["nome"])
        salvo = escolhas.get(chave)
        escolhido = next((p for p in produtos if salvo and (p["fornecedor"], p["produto"]) == salvo), barato)
        opcoes = []
        for p in produtos:
            qtd = quantidade_em(item, p["por"])
            opcoes.append({**p, "total": round(qtd * p["preco"], 2) if qtd is not None else None,
                           "barato": p is barato, "salvo": bool(salvo) and p is escolhido})
        linhas.append({"item": item, "chave": chave, "opcoes": opcoes,
                       "escolhido": next(o for o in opcoes if o["id"] == escolhido["id"])})
    por_fornecedor = {}
    for l in linhas:
        e = l["escolhido"]
        grupo = por_fornecedor.setdefault(e["fornecedor"], {"itens": 0, "total": 0.0})
        grupo["itens"] += 1
        grupo["total"] += e["total"] or 0
    return {"linhas": linhas, "nao_achados": nao_achados,
            "por_fornecedor": sorted(por_fornecedor.items(), key=lambda g: -g[1]["itens"]),
            "total": round(sum(l["escolhido"]["total"] or 0 for l in linhas), 2)}


def carregar_escolhas(conn):
    return {r["chave"]: (r["fornecedor"], r["produto"]) for r in conn.execute("SELECT * FROM preco_escolhas")}


def carregar_precos(conn):
    precos = []
    for r in conn.execute("SELECT * FROM precos_fornecedor"):
        p = dict(r)
        p["chave"] = chave_nome(p["produto"])
        p["palavras"] = palavras(p["produto"])
        precos.append(p)
    return precos


@bp.route("/melhor-preco", methods=["GET", "POST"])
def melhor_preco():
    conn = get_connection()
    erro, resultado = None, None
    texto = request.form.get("texto", "")
    if request.method == "POST":
        arquivo = request.files.get("arquivo")
        try:
            if texto.strip():
                linhas = ler_texto(texto)
            elif arquivo and arquivo.filename:
                linhas = ler_arquivo(arquivo.filename, arquivo.read())
            else:
                linhas = None
                erro = "Digite a lista de compras ou anexe o arquivo."
            if linhas is not None:
                itens = extrair_itens(linhas, [])
                precos = carregar_precos(conn)
                if not itens:
                    erro = "Não encontrei itens na lista. Use uma linha por item, por exemplo \"Bacon 2 kg\"."
                elif not precos:
                    erro = "Ainda não há planilha de preços guardada. Envie as planilhas dos fornecedores abaixo."
                else:
                    resultado = buscar(itens, precos, carregar_escolhas(conn))
        except ValueError as e:
            erro = str(e)
        except Exception:
            erro = "Não consegui ler esse arquivo. Confira se ele não está corrompido ou protegido por senha."
    planilhas = resumo_planilhas(conn)
    conn.close()
    return render_template("melhor_preco.html", erro=erro, resultado=resultado, texto=texto, planilhas=planilhas,
                           enviadas=request.args.get("enviadas", ""), removido=request.args.get("removido", ""))


@bp.route("/melhor-preco/planilhas", methods=["POST"])
def enviar_planilhas():
    conn = get_connection()
    enviados, erros = {}, []
    for arquivo in request.files.getlist("planilhas"):
        if not arquivo or not arquivo.filename:
            continue
        if not arquivo.filename.lower().endswith((".xlsx", ".xlsm")):
            erros.append(f"{arquivo.filename}: use a planilha em Excel (.xlsx)")
            continue
        try:
            achados = guardar_planilha(conn, arquivo.filename, arquivo.read())
        except Exception:
            achados = None
        if not achados:
            erros.append(f"{arquivo.filename}: sem colunas Produto e Preço/kg último ou Preço unitário último")
        else:
            enviados.update(achados)
    conn.close()
    partes = [f"{f}: {n} produtos" for f, n in enviados.items()] + erros
    return redirect(url_for("precos.melhor_preco", enviadas=" · ".join(partes) or "Nenhuma planilha escolhida."))


@bp.route("/melhor-preco/remover", methods=["POST"])
def remover_fornecedor():
    fornecedor = request.form.get("fornecedor", "")
    conn = get_connection()
    conn.execute("DELETE FROM precos_fornecedor WHERE fornecedor = ?", (fornecedor,))
    conn.commit()
    conn.close()
    return redirect(url_for("precos.melhor_preco", removido=fornecedor))


@bp.route("/melhor-preco/escolha", methods=["POST"])
def salvar_escolha():
    """Guarda a marca escolhida para um item; escolher o mais barato apaga a preferência."""
    dados = request.get_json(silent=True) or {}
    chave = chave_nome(str(dados.get("item", "")))
    if not chave:
        return jsonify(ok=False), 400
    conn = get_connection()
    linha = conn.execute("SELECT fornecedor, produto FROM precos_fornecedor WHERE id = ?",
                         (dados.get("id"),)).fetchone()
    if linha is None or dados.get("barato"):
        conn.execute("DELETE FROM preco_escolhas WHERE chave = ?", (chave,))
    else:
        conn.execute("INSERT OR REPLACE INTO preco_escolhas (chave, fornecedor, produto, salvo_em) VALUES (?, ?, ?, ?)",
                     (chave, linha["fornecedor"], linha["produto"], config.agora().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    return jsonify(ok=True)
