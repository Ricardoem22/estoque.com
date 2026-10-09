# insumo_cadastro.py
# Ficha de cada insumo: código, marca, fornecedor, local, estoque mínimo e ideal, custo de referência,
# situação (ativo/inativo), medidas de compra ("1 saco = 5 kg") e histórico de movimentações.
import io
import json
import re
from datetime import date

from flask import Blueprint, abort, redirect, render_template, request, url_for

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
                       local = ?, minimo = ?, ideal = ?, custo = ?, observacao = ?, ativo = ?, ncm = ?
                WHERE id = ?
            """, (
                nome, form.get("categoria").strip(), form.get("unidade", "").strip() or insumo["unidade"],
                form.get("codigo", "").strip(), form.get("marca", "").strip(), form.get("fornecedor", "").strip(),
                form.get("local", "").strip(), minimo, ideal, custo, form.get("observacao", "").strip(),
                1 if form.get("ativo") else 0, re.sub(r"\D", "", form.get("ncm", "")), id,
            ))
            nova = form.get("unidade", "").strip() or insumo["unidade"]
            aviso = ""
            if nova != insumo["unidade"]:
                # Contagem zerada vale zero em qualquer medida: passa para a unidade nova, senão o estoque
                # continuaria na unidade antiga e as compras na nova não somariam
                antigas = conn.execute("""
                    SELECT ci.rowid AS id, ci.quantidade, ci.unidade FROM contagem_itens ci
                    WHERE ci.insumo_id = ? AND ci.quantidade IS NOT NULL
                """, (id,)).fetchall()
                for c in antigas:
                    if converter_fixo(1, c["unidade"], nova) is not None:
                        continue
                    if c["quantidade"] == 0:
                        conn.execute("UPDATE contagem_itens SET unidade = ? WHERE rowid = ?", (nova, c["id"]))
                    else:
                        aviso = "contagem"
            conn.commit()
            conn.close()
            return redirect(url_for("insumo.editar", id=id, salvo=1, aviso=aviso or None))

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
        salvo=request.args.get("salvo"), aviso=request.args.get("aviso"), erro_conversao=request.args.get("erro_conversao"),
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
    # Cadastrada direto do aviso das compras: volta para lá
    voltar = request.form.get("voltar", "")
    if voltar.startswith("/compras"):
        return redirect(voltar)
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


# ---------- Preço e NCM por planilha ----------

def ler_planilha_precos(dados):
    """Lê a planilha de preços (relação de produtos das notas) e devolve as linhas com produto, NCM e preço.
    Aceita abas com 'Preço/kg último' (preço por kg) ou 'Preço unitário último' + 'Unidade'."""
    from openpyxl import load_workbook
    livro = load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
    linhas = []
    for aba in livro.worksheets:
        cabecalho, colunas = None, {}
        for valores in aba.iter_rows(values_only=True):
            if cabecalho is None:
                nomes = [str(v or "").strip().lower() for v in valores]
                if "produto" not in nomes:
                    continue
                cabecalho = nomes
                for i, nome in enumerate(nomes):
                    if nome == "produto":
                        colunas["produto"] = i
                    elif nome == "ncm":
                        colunas["ncm"] = i
                    elif nome.startswith("preço/kg último") or nome.startswith("preco/kg ultimo"):
                        colunas["preco_kg"] = i
                    elif nome.startswith("preço unitário último") or nome.startswith("preco unitario ultimo"):
                        colunas["preco_un"] = i
                    elif nome == "unidade":
                        colunas["unidade"] = i
                    elif nome.startswith("data"):
                        colunas.setdefault("data", i)
                    elif nome.startswith("fornecedor"):
                        colunas.setdefault("fornecedor", i)
                if "preco_kg" not in colunas and "preco_un" not in colunas:
                    break  # aba sem preço (ex.: detalhe das notas)
                continue

            def campo(nome):
                i = colunas.get(nome)
                return valores[i] if i is not None and i < len(valores) else None
            produto = str(campo("produto") or "").strip()
            if not produto:
                continue
            ncm = re.sub(r"\D", "", str(campo("ncm") or ""))
            data = campo("data")
            data = data.isoformat()[:10] if isinstance(data, date) else str(data or "")[:10]
            linha = {"produto": produto, "ncm": ncm, "data": data, "fornecedor": str(campo("fornecedor") or "")}
            try:
                if "preco_kg" in colunas:
                    linha.update(preco=float(campo("preco_kg")), por="kg")
                else:
                    # UN/UN1 = preço da unidade; FD6, CX12 = pacote com 6, 12 unidades
                    codigo = str(campo("unidade") or "").strip().upper()
                    pacote = re.fullmatch(r"([A-Z]+)(\d*)", codigo)
                    quantas = int(pacote.group(2)) if pacote and pacote.group(2) else (1 if codigo == "UN" else 0)
                    preco = float(campo("preco_un"))
                    if quantas:
                        linha.update(preco=preco / quantas, por="un")
                    else:
                        linha.update(preco=preco, por=codigo)
            except (TypeError, ValueError):
                linha.update(preco=None, por="")
            linhas.append(linha)
    return linhas


def preco_na_unidade(linha, unidade):
    """Preço da planilha na unidade do estoque do insumo (kg, g ou un); None se não dá para converter."""
    if linha.get("preco") is None:
        return None
    if linha["por"] == "kg":
        por_unidade = converter_fixo(1, unidade, "kg")
        return linha["preco"] * por_unidade if por_unidade is not None else None
    if linha["por"] == "un" and unidade == "un":
        return linha["preco"]
    return None


@bp.route("/insumos/precos", methods=["GET", "POST"])
def precos_planilha():
    """Atualiza o custo de referência e o NCM dos insumos a partir da planilha de produtos das notas."""
    erro = None
    itens = []
    if request.method == "POST":
        arquivo = request.files.get("arquivo")
        if not arquivo or not arquivo.filename:
            erro = "Escolha a planilha (.xlsx)."
        elif not arquivo.filename.lower().endswith((".xlsx", ".xlsm")):
            erro = "Use a planilha em Excel (.xlsx)."
        else:
            try:
                linhas = ler_planilha_precos(arquivo.read())
            except Exception:
                linhas = None
            if not linhas:
                erro = "Não encontrei produtos com preço nessa planilha. Ela precisa da coluna Produto e de Preço/kg último ou Preço unitário último."
            else:
                from notas import achar_insumo, palavras
                conn = get_connection()
                insumos = conn.execute("SELECT * FROM insumos WHERE ativo = 1").fetchall()
                apelidos = {r["chave"]: r["insumo_id"] for r in conn.execute("SELECT * FROM nota_apelidos")}
                conn.close()
                por_insumo = {}
                for linha in linhas:
                    insumo_id = achar_insumo(linha["produto"], insumos, apelidos)
                    if insumo_id:
                        por_insumo.setdefault(insumo_id, []).append(linha)
                for insumo in sorted(insumos, key=lambda i: i["nome"].lower()):
                    candidatos = por_insumo.get(insumo["id"])
                    if not candidatos:
                        continue
                    for c in candidatos:
                        c["preco_insumo"] = preco_na_unidade(c, insumo["unidade"])
                    # A compra mais recente primeiro; com preço na unidade do estoque antes das outras
                    # Primeiro o produto com o nome exato do insumo ("ALHO PORO UN"), depois o que tem preço
                    # na unidade do estoque, depois o com menos palavras a mais ("ALHO KG" antes de
                    # "ALHO FRITO 500G") e, por fim, a compra mais recente
                    nome_insumo = palavras(insumo["nome"])
                    candidatos.sort(key=lambda c: c["data"], reverse=True)
                    candidatos.sort(key=lambda c: (bool(palavras(c["produto"]) - nome_insumo),
                                                   c["preco_insumo"] is None,
                                                   len(palavras(c["produto"]) - nome_insumo)))
                    itens.append({"insumo": insumo, "candidatos": candidatos,
                                  "opcoes": [json.dumps({"preco": c["preco_insumo"], "ncm": c["ncm"]})
                                             for c in candidatos]})
                if not itens:
                    erro = "Nenhum produto da planilha casou com os nomes dos insumos cadastrados."
    return render_template("insumo_precos.html", erro=erro, itens=itens,
                           atualizados=request.args.get("atualizados", type=int))


@bp.route("/insumos/precos/confirmar", methods=["POST"])
def confirmar_precos():
    conn = get_connection()
    atualizados = 0
    for chave, valor in request.form.items():
        if not chave.startswith("escolha_") or not valor:
            continue
        try:
            insumo_id = int(chave[len("escolha_"):])
            escolha = json.loads(valor)
        except (ValueError, TypeError):
            continue
        campos, valores = [], []
        if request.form.get("atualizar_preco") and isinstance(escolha.get("preco"), (int, float)):
            campos.append("custo = ?")
            valores.append(round(escolha["preco"], 4))
        ncm = re.sub(r"\D", "", str(escolha.get("ncm") or ""))
        if request.form.get("atualizar_ncm") and ncm:
            campos.append("ncm = ?")
            valores.append(ncm)
        if campos:
            conn.execute(f"UPDATE insumos SET {', '.join(campos)} WHERE id = ?", valores + [insumo_id])
            atualizados += 1
    conn.commit()
    conn.close()
    return redirect(url_for("insumo.precos_planilha", atualizados=atualizados))


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
    from exportar import responder
    tabela = [[e["data"], e["tipo"], e["sinal"], str(e["quantidade"]).replace(".", ","), e["unidade"], e["quem"],
               e["detalhe"]] for e in eventos]
    return responder(f"historico_{insumo['id']}", f"Histórico: {insumo['nome']}",
                     ["Data", "Movimentação", "Sinal", "Quantidade", "Unidade", "Responsável", "Detalhe"], tabela)
