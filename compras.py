# compras.py
# Registro das compras (entradas de mercadoria), usado no cálculo do consumo.
from datetime import datetime
import re

import os
import uuid

from flask import Blueprint, abort, redirect, render_template, request, send_from_directory, session, url_for

from contagem import (agrupar_por_categoria, data_br_filter, formatar_quantidade, get_connection, lista_categorias,
                      parse_quantidade, unidade_digitada, unidade_padrao)
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
    # Observação, quem lançou e o arquivo da nota/comprovante guardado com a compra
    # data_compra: dia da compra ou da nota (a coluna data é o recebimento, que vale para o estoque); validade do lote
    for coluna in ("observacao", "registrado_por", "anexo", "data_compra", "validade"):
        if coluna not in colunas:
            conn.execute(f"ALTER TABLE compras ADD COLUMN {coluna} TEXT NOT NULL DEFAULT ''")
    # Arquivos a mais da mesma compra (o primeiro continua em compras.anexo)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS compra_anexos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compra_id INTEGER NOT NULL REFERENCES compras(id) ON DELETE CASCADE,
            arquivo TEXT NOT NULL
        )
    """)
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
    texto = f"{abs(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"−R$ {texto}" if round(valor, 2) < 0 else f"R$ {texto}"


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


def data_valida(texto):
    try:
        datetime.strptime(texto or "", "%Y-%m-%d")
        return texto
    except ValueError:
        return ""


def mes_selecionado():
    mes = request.args.get("mes", "")
    try:
        datetime.strptime(mes, "%Y-%m")
        return mes
    except ValueError:
        return config.hoje().strftime("%Y-%m")


EXTENSOES_ANEXO = {"pdf", "xml", "xlsx", "xlsm", "csv", "docx", "jpg", "jpeg", "png", "webp", "heic", "heif"}


def salvar_anexo(nome_arquivo, dados):
    """Guarda o arquivo da compra na pasta de uploads e devolve o nome salvo ('' se não der)."""
    ext = nome_arquivo.rsplit(".", 1)[-1].lower() if "." in nome_arquivo else ""
    if ext not in EXTENSOES_ANEXO or not dados:
        return ""
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    nome = f"compra_{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(config.UPLOAD_DIR, nome), "wb") as f:
        f.write(dados)
    return nome


@bp.route("/compras/anexo/<nome>")
def ver_anexo(nome):
    if not nome.startswith("compra_") or "/" in nome or "\\" in nome:
        abort(404)
    return send_from_directory(config.UPLOAD_DIR, nome)


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
        else:
            from insumo_cadastro import carregar_conversoes
            from unidades import converter
            unidade = unidade_digitada(form.get("quantidade"), form.get("unidade")) or insumo["unidade"]
            # O estoque soma na unidade da última contagem do insumo
            ultima = ultimas_contagens(conn).get(insumo["id"])
            destino = ultima["unidade"] if ultima else insumo["unidade"]
            if converter(1, unidade, destino, carregar_conversoes(conn).get(insumo["id"], [])) is None:
                erro = (f"{unidade} não converte para {destino} (a unidade do estoque de "
                        f"{insumo['nome']}). Cadastre a medida na ficha do insumo, ex.: 1 {unidade} = 5 "
                        f"{destino}.")
        if not erro and form.get("data_compra") and not data_valida(form.get("data_compra")):
            erro = "Data da compra inválida."
        elif not erro and form.get("validade") and not data_valida(form.get("validade")):
            erro = "Validade inválida."
        arquivos = [a for a in request.files.getlist("anexo") if a and a.filename][:10]
        anexos = []
        for arquivo in arquivos if not erro else []:
            nome = salvar_anexo(arquivo.filename, arquivo.read())
            if not nome:
                erro = f"Arquivo não aceito ({arquivo.filename}). Use PDF, foto (JPG/PNG), planilha (Excel/CSV), Word ou XML."
                break
            anexos.append(nome)
        if erro:
            for nome in anexos:
                remover_arquivo(nome)
            anexos = []
        anexo = anexos[0] if anexos else ""

        if not erro:
            compra_id = conn.execute("""
                INSERT INTO compras (data, insumo_id, quantidade, unidade, fornecedor, criado_em, valor_total,
                                     nota, observacao, registrado_por, anexo, data_compra, validade)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data, insumo["id"], quantidade,
                unidade_digitada(form.get("quantidade"), form.get("unidade")) or insumo["unidade"],
                form.get("fornecedor", "").strip(), config.agora().strftime("%Y-%m-%d %H:%M:%S"), valor_total,
                None, form.get("observacao", "").strip(), session.get("nome", ""),
                anexo, data_valida(form.get("data_compra")), data_valida(form.get("validade")),
            )).lastrowid
            for nome in anexos[1:]:
                conn.execute("INSERT INTO compra_anexos (compra_id, arquivo) VALUES (?, ?)", (compra_id, nome))
            conn.commit()
            conn.close()
            # Mantém a data e o fornecedor para lançar a nota inteira em sequência
            return redirect(url_for("compras.compras", mes=data[:7], salvo=compra_id, data=data,
                                    fornecedor=form.get("fornecedor", "").strip()))

    mes = mes_selecionado()
    # Filtro: o mês, ou um período (de/até), e o fornecedor
    de, ate = data_valida(request.args.get("de")), data_valida(request.args.get("ate"))
    filtro_fornecedor = request.args.get("fornecedor_filtro", "").strip()
    if de or ate:
        de, ate = de or "0000-01-01", ate or "9999-12-31"
        where, params = "c.data BETWEEN ? AND ?", [de, ate]
    else:
        where, params = "substr(c.data, 1, 7) = ?", [mes]
    if filtro_fornecedor:
        where += " AND c.fornecedor = ?"
        params.append(filtro_fornecedor)
    registros = conn.execute(f"""
        SELECT c.*, i.nome AS insumo_nome FROM compras c
        JOIN insumos i ON i.id = c.insumo_id
        WHERE {where}
        ORDER BY c.data DESC, c.id DESC
    """, params).fetchall()
    if request.args.get("formato"):
        from exportar import responder
        conn.close()
        periodo = f"{data_br_filter(de)} a {data_br_filter(ate)}" if request.args.get("de") or request.args.get("ate") \
            else f"{mes[5:]}/{mes[:4]}"
        tabela = [[data_br_filter(r["data"]), data_br_filter(r["data_compra"]) if r["data_compra"] else "", r["insumo_nome"],
                   formatar_quantidade(r["quantidade"]), r["unidade"],
                   f"{r['valor_total']:.2f}".replace(".", ",") if r["valor_total"] is not None else "", r["fornecedor"],
                   data_br_filter(r["validade"]) if r["validade"] else "", r["observacao"], r["registrado_por"]]
                  for r in registros]
        return responder(f"compras_{mes}", "Compras" + (f" · {filtro_fornecedor}" if filtro_fornecedor else ""),
                         ["Recebido", "Compra", "Insumo", "Qtd.", "Unidade", "Valor (R$)", "Fornecedor", "Validade",
                          "Observação", "Lançado por"], tabela, subtitulo=f"Período: {periodo}")
    fornecedores = [r["fornecedor"] for r in conn.execute(
        "SELECT DISTINCT fornecedor FROM compras WHERE fornecedor != '' ORDER BY fornecedor COLLATE NOCASE")]
    por_fornecedor = {}
    for r in registros:
        f = por_fornecedor.setdefault(r["fornecedor"] or "Sem fornecedor", {"nome": r["fornecedor"] or "Sem fornecedor",
                                                                             "itens": 0, "valor": 0})
        f["itens"] += 1
        f["valor"] += r["valor_total"] or 0
    extras = {}
    if registros:
        ids = [r["id"] for r in registros]
        for a in conn.execute(f"SELECT compra_id, arquivo FROM compra_anexos WHERE compra_id IN ({','.join('?' * len(ids))})"
                              " ORDER BY id", ids):
            extras.setdefault(a["compra_id"], []).append(a["arquivo"])
    from insumo_cadastro import insumos_para_formulario
    grupos = insumos_para_formulario(conn)
    fora = fora_do_estoque(conn, registros)
    salvo = request.args.get("salvo", type=int)
    resultado = resultado_compra(conn, salvo) if salvo else None
    # Depois de lançar uma nota: itens que entraram nas compras mas não somaram no estoque
    ids_nota = [int(i) for i in request.args.get("ids", "").split(",") if i.isdigit()][:200]
    nota_fora, nota_pulados = [], []
    if request.args.get("lancados") is not None:
        nota_pulados = session.pop("nota_pulados", [])
        if ids_nota:
            lancadas = conn.execute(f"""
                SELECT c.*, i.nome AS insumo_nome FROM compras c JOIN insumos i ON i.id = c.insumo_id
                WHERE c.id IN ({",".join("?" * len(ids_nota))})
            """, ids_nota).fetchall()
            motivos = fora_do_estoque(conn, lancadas)
            nota_fora = [{"compra": c, **motivos[c["id"]]} for c in lancadas if c["id"] in motivos]
    conn.close()
    return render_template(
        "compras.html", grupos=grupos, unidades=UNIDADES, registros=registros, mes=mes, erro=erro, form=form,
        fora=fora, resultado=resultado,
        total_mes=sum(r["valor_total"] or 0 for r in registros),
        data_padrao=form.get("data") or request.args.get("data") or config.hoje().isoformat(),
        fornecedor=form.get("fornecedor") or request.args.get("fornecedor", ""),
        salvo=salvo, lancados=request.args.get("lancados", type=int), nota_fora=nota_fora,
        somadas=request.args.get("somadas", type=int),
        de=request.args.get("de", ""), ate=request.args.get("ate", ""), filtro_fornecedor=filtro_fornecedor,
        fornecedores=fornecedores, extras=extras, hoje_iso=config.hoje().isoformat(),
        por_fornecedor=sorted(por_fornecedor.values(), key=lambda f: (-f["valor"], f["nome"])),
        nota_pulados=nota_pulados, voltar=request.full_path,
    )


def ultimas_contagens(conn):
    """Última contagem finalizada de cada insumo: {insumo_id: linha com data e unidade}."""
    ultimas = {}
    for r in conn.execute("""
        SELECT ci.insumo_id, ci.unidade, c.data FROM contagem_itens ci
        JOIN contagens c ON c.id = ci.contagem_id
        WHERE c.finalizada = 1 AND ci.quantidade IS NOT NULL ORDER BY c.data, c.id
    """):
        ultimas[r["insumo_id"]] = r
    return ultimas


def fora_do_estoque(conn, registros):
    """Compras que não somam no estoque, com o motivo. Segue a mesma regra do painel:
    só entra o que tem data a partir da última contagem e unidade que converte."""
    from insumo_cadastro import carregar_conversoes
    from unidades import converter
    ultimas = ultimas_contagens(conn)
    conversoes = carregar_conversoes(conn)
    unidades = {i["id"]: i["unidade"] for i in conn.execute("SELECT id, unidade FROM insumos")}
    fora = {}
    for r in registros:
        ultima = ultimas.get(r["insumo_id"])
        if ultima and r["data"] < ultima["data"]:
            fora[r["id"]] = {"motivo": "data", "contagem": ultima["data"]}
            continue
        destino = ultima["unidade"] if ultima else unidades.get(r["insumo_id"])
        if converter(1, r["unidade"], destino, conversoes.get(r["insumo_id"], [])) is None:
            fora[r["id"]] = {"motivo": "unidade", "unidade": destino}
    return fora


def resultado_compra(conn, compra_id):
    """Depois de registrar: quanto ficou o estoque do insumo, ou por que a compra não somou."""
    compra = conn.execute("""
        SELECT c.*, i.nome AS insumo_nome FROM compras c JOIN insumos i ON i.id = c.insumo_id WHERE c.id = ?
    """, (compra_id,)).fetchone()
    if compra is None:
        return None
    from relatorio import calcular_linhas
    linha = next((l for l in calcular_linhas() if l["id"] == compra["insumo_id"]), None)
    return {"compra": compra, "linha": linha, "fora": fora_do_estoque(conn, [compra]).get(compra_id)}


@bp.route("/compras/<int:id>/data-da-contagem", methods=["POST"])
def mover_para_contagem(id):
    """A mercadoria chegou depois da contagem, mas a compra ficou com data anterior: passa para o dia da contagem."""
    conn = get_connection()
    compra = conn.execute("SELECT * FROM compras WHERE id = ?", (id,)).fetchone()
    if compra is None:
        conn.close()
        abort(404)
    ultima = ultimas_contagens(conn).get(compra["insumo_id"])
    if ultima and compra["data"] < ultima["data"]:
        conn.execute("UPDATE compras SET data = ? WHERE id = ?", (ultima["data"], id))
        conn.commit()
        data = ultima["data"]
    else:
        data = compra["data"]
    conn.close()
    return redirect(url_for("compras.compras", mes=data[:7], salvo=id, data=data))


@bp.route("/compras/data-da-contagem", methods=["POST"])
def mover_varias_para_contagem():
    """Todos os itens da nota que chegaram depois da contagem: cada compra passa para o dia da última contagem
    do seu insumo e soma no estoque."""
    ids = [int(i) for i in request.form.getlist("ids") if i.isdigit()][:200]
    conn = get_connection()
    ultimas = ultimas_contagens(conn)
    movidas = 0
    for compra in conn.execute(f"SELECT * FROM compras WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall() \
            if ids else []:
        ultima = ultimas.get(compra["insumo_id"])
        if ultima and compra["data"] < ultima["data"]:
            conn.execute("UPDATE compras SET data = ? WHERE id = ?", (ultima["data"], compra["id"]))
            movidas += 1
    conn.commit()
    conn.close()
    return redirect(url_for("compras.compras", somadas=movidas))


def remover_arquivo(nome):
    try:
        os.remove(os.path.join(config.UPLOAD_DIR, nome))
    except OSError:
        pass


def apagar_compra(conn, id):
    """Apaga a compra (sem commit). O arquivo só sai da pasta quando nenhuma outra compra (da mesma nota) usa."""
    compra = conn.execute("SELECT anexo FROM compras WHERE id = ?", (id,)).fetchone()
    extras = [a["arquivo"] for a in conn.execute("SELECT arquivo FROM compra_anexos WHERE compra_id = ?", (id,))]
    conn.execute("DELETE FROM compra_anexos WHERE compra_id = ?", (id,))
    conn.execute("DELETE FROM compras WHERE id = ?", (id,))
    if compra and compra["anexo"] and not conn.execute("SELECT 1 FROM compras WHERE anexo = ?",
                                                       (compra["anexo"],)).fetchone():
        remover_arquivo(compra["anexo"])
    for nome in extras:
        remover_arquivo(nome)


@bp.route("/compras/<int:id>/excluir", methods=["POST"])
def excluir_compra(id):
    conn = get_connection()
    apagar_compra(conn, id)
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
                dados = arquivo.read()
                nota = ler_nota(arquivo.filename, dados)
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
            conversoes = {}
            for c in conn.execute("SELECT insumo_id, unidade, fator, unidade_base FROM insumo_conversoes"):
                conversoes.setdefault(c["insumo_id"], []).append((c["unidade"], c["fator"], c["unidade_base"]))
            for item in nota["itens"]:
                item["insumo_id"] = achar_insumo(item["nome"], insumos, apelidos, unidade_do_item(item), conversoes)
                item["unidade"] = unidade_do_item(item) or unidade_insumo.get(item["insumo_id"]) or "un"
            nota["anexo"] = salvar_anexo(arquivo.filename, dados)
            if nota["chave"]:
                ja_lancada = conn.execute("SELECT MIN(data) AS data FROM compras WHERE nota = ?",
                                          (nota["chave"],)).fetchone()["data"]
    ultima_contagem = conn.execute("SELECT MAX(data) AS data FROM contagens WHERE finalizada = 1").fetchone()["data"]
    conn.close()
    return render_template(
        "importar_nota.html", erro=erro, nota=nota, grupos=grupos, unidades=UNIDADES, ultima_contagem=ultima_contagem,
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
    data_compra = data_valida(form.get("data_compra"))
    fornecedor = form.get("fornecedor", "").strip()
    nota = form.get("nota", "").strip() or None
    anexo = form.get("anexo", "").strip()
    if not (anexo.startswith("compra_") and os.path.exists(os.path.join(config.UPLOAD_DIR, anexo))):
        anexo = ""
    agora = config.agora().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    lancados = 0
    ids, pulados = [], []
    for i in range(form.get("total", 0, type=int)):
        destino = form.get(f"insumo_{i}", "")
        nome_nota = form.get(f"nome_{i}", "").strip()
        if not form.get(f"incluir_{i}"):
            continue
        if not destino:
            pulados.append([nome_nota, "nenhum insumo escolhido"])
            continue
        try:
            quantidade = parse_quantidade(form.get(f"qtd_{i}"))
            valor = parse_valor(form.get(f"valor_{i}"))
        except ValueError:
            pulados.append([nome_nota, "quantidade ou valor inválido"])
            continue
        if not quantidade:
            pulados.append([nome_nota, "quantidade zerada"])
            continue
        unidade = unidade_digitada(form.get(f"qtd_{i}"), form.get(f"unidade_{i}")) or "un"
        if destino == "novo":
            nome = form.get(f"novo_nome_{i}", "").strip() or nome_nota
            categoria = form.get(f"categoria_{i}", "").strip()
            if not nome or not categoria:
                pulados.append([nome_nota, "insumo novo sem nome ou categoria"])
                continue
            existente = conn.execute("SELECT id FROM insumos WHERE nome = ?", (nome,)).fetchone()
            insumo_id = existente["id"] if existente else conn.execute(
                "INSERT INTO insumos (nome, categoria, unidade) VALUES (?, ?, ?)",
                (nome, categoria, unidade if unidade else unidade_padrao(categoria))).lastrowid
        else:
            insumo_id = int(destino) if destino.isdigit() else None
            if not insumo_id or not conn.execute("SELECT 1 FROM insumos WHERE id = ?", (insumo_id,)).fetchone():
                pulados.append([nome_nota, "insumo não encontrado"])
                continue
        ids.append(conn.execute("""
            INSERT INTO compras (data, insumo_id, quantidade, unidade, fornecedor, criado_em, valor_total, nota,
                                 registrado_por, anexo, data_compra)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (data, insumo_id, quantidade, unidade, fornecedor, agora, valor, nota, session.get("nome", ""),
              anexo, data_compra)).lastrowid)
        if nome_nota:
            conn.execute("INSERT OR REPLACE INTO nota_apelidos (chave, insumo_id) VALUES (?, ?)",
                         (chave_nome(nome_nota), insumo_id))
        lancados += 1
    conn.commit()
    conn.close()
    # O que não entrou fica guardado para a tela das compras explicar
    session["nota_pulados"] = pulados[:30]
    return redirect(url_for("compras.compras", mes=data[:7], lancados=lancados,
                            ids=",".join(str(i) for i in ids)))
