# relatorio.py
# Relatório de estoque: consumo semanal de cada insumo e sugestão de compra.
#
# Consumo entre duas contagens = estoque anterior + compras no período - estoque atual.
# Usa só contagens finalizadas e as últimas MAX_INTERVALOS semanas de cada insumo.
# Estoque atual = última contagem + compras depois dela - desperdício aprovado depois dela.
import math
from datetime import date, timedelta

from flask import Blueprint, Response, redirect, render_template, request, url_for

import config
from contagem import agrupar_por_categoria, data_br_filter, formatar_quantidade, get_connection
from importador import chave_nome, extrair_itens, ler_arquivo, ler_texto, sem_acento
from unidades import converter

bp = Blueprint("relatorio", __name__)

MAX_INTERVALOS = 4
UNIDADES_FRACIONADAS = {"kg", "L", "lt"}


def dia(texto):
    return date.fromisoformat(texto)


def arredondar_compra(valor, unidade):
    """Arredonda para cima: 0,1 em kg/L, inteiro nas outras unidades."""
    if unidade in UNIDADES_FRACIONADAS:
        return math.ceil(round(valor * 10, 6)) / 10
    return float(math.ceil(round(valor, 6)))


def soma_compras(compras, unidade, inicio, fim=None, conversoes=()):
    """Compras convertidas para a unidade dada (g↔kg, ml↔L e medidas do insumo) com data >= inicio e < fim.
    Uma compra no dia da contagem conta como chegada depois da contagem."""
    total = 0.0
    for c in compras:
        if c["data"] >= inicio and (fim is None or c["data"] < fim):
            quantidade = converter(c["quantidade"], c["unidade"], unidade, conversoes)
            if quantidade is not None:
                total += quantidade
    return total


def analisar_insumo(insumo, contagens, compras, semanas, desperdicios=(), movimentos=(), conversoes=()):
    """movimentos: saídas, devoluções e ajustes com a quantidade já com sinal (− desconta, + soma)."""
    dados = dict(insumo)
    linha = {
        "id": insumo["id"], "nome": insumo["nome"], "categoria": insumo["categoria"],
        "unidade": insumo["unidade"], "estoque": None, "ultima_contagem": None,
        "consumo_semanal": None, "dias_cobertura": None, "sugestao": 0, "status": "sem_dados",
        "local": dados.get("local") or "", "minimo": dados.get("minimo"), "ideal": dados.get("ideal"),
        "custo": dados.get("custo"), "fornecedor": dados.get("fornecedor") or "",
        "ativo": dados.get("ativo", 1), "conversoes": conversoes,
    }
    # Devolução ao fornecedor desfaz parte da compra (vale também no cálculo do consumo)
    compras_liquidas = list(compras) + [m for m in movimentos if m["tipo"] == "devolucao"]
    if not contagens:
        # Nunca contado: o estoque é o que entrou pelas compras
        if compras:
            unidade = insumo["unidade"]
            linha["contado"] = 0.0
            linha["compras_desde"] = soma_compras(compras, unidade, "", None, conversoes)
            linha["movimentos"] = soma_compras(movimentos, unidade, "", None, conversoes)
            linha["desperdicio"] = soma_compras(desperdicios, unidade, "", None, conversoes)
            linha["estoque"] = max(0.0, linha["compras_desde"] + linha["movimentos"] - linha["desperdicio"])
        return marcar_situacao(linha)

    ultima = contagens[-1]
    unidade = ultima["unidade"]
    linha["unidade"] = unidade
    linha["ultima_contagem"] = ultima["data"]
    linha["contado"] = ultima["quantidade"]
    linha["contado_por"] = dict(ultima).get("responsavel", "")
    linha["compras_desde"] = soma_compras(compras, unidade, ultima["data"], None, conversoes)
    linha["movimentos"] = soma_compras(movimentos, unidade, ultima["data"], None, conversoes)
    linha["desperdicio"] = soma_compras(desperdicios, unidade, ultima["data"], None, conversoes)
    linha["estoque"] = max(0.0, ultima["quantidade"] + linha["compras_desde"] + linha["movimentos"]
                           - linha["desperdicio"])
    marcar_situacao(linha)

    consumo_total = 0.0
    dias_total = 0
    intervalos = 0
    for anterior, atual in reversed(list(zip(contagens, contagens[1:]))):
        if intervalos >= MAX_INTERVALOS:
            break
        dias = (dia(atual["data"]) - dia(anterior["data"])).days
        if atual["unidade"] != unidade:
            break  # histórico mais antigo em outra unidade
        if dias <= 0 or anterior["unidade"] != atual["unidade"]:
            continue
        consumo = anterior["quantidade"] - atual["quantidade"] + soma_compras(
            compras_liquidas, atual["unidade"], anterior["data"], atual["data"], conversoes)
        if consumo < 0:
            # Estoque subiu sem compra registrada: o intervalo não serve para o cálculo
            continue
        consumo_total += consumo
        dias_total += dias
        intervalos += 1

    if not intervalos:
        return linha

    semanal = consumo_total / dias_total * 7
    linha["consumo_semanal"] = semanal
    linha["intervalos"] = intervalos
    if semanal > 0:
        linha["dias_cobertura"] = linha["estoque"] / (semanal / 7)
    falta = semanal * semanas - linha["estoque"]
    if falta > 0:
        linha["sugestao"] = arredondar_compra(falta, unidade)
        linha["status"] = "comprar"
    else:
        linha["status"] = "bom"
    return linha


def marcar_situacao(linha):
    """sem_saldo, abaixo_minimo, ok ou sem_minimo (para os alertas do painel)."""
    estoque, minimo = linha["estoque"], linha.get("minimo")
    if estoque is None:
        linha["situacao"] = "sem_contagem"
    elif estoque <= 0:
        linha["situacao"] = "sem_saldo"
    elif minimo is not None and estoque < minimo:
        linha["situacao"] = "abaixo_minimo"
    else:
        linha["situacao"] = "ok"
    return linha


def calcular_linhas(semanas=1, ate=None):
    """ate: data (AAAA-MM-DD) para calcular o estoque como estava logo antes dela; só valem
    contagens e lançamentos com data anterior."""
    from insumo_cadastro import carregar_conversoes
    from movimentos import TIPOS
    conn = get_connection()
    insumos = conn.execute("SELECT * FROM insumos").fetchall()
    itens = conn.execute("""
        SELECT ci.insumo_id, ci.quantidade, ci.unidade, c.data, c.responsavel
        FROM contagem_itens ci
        JOIN contagens c ON c.id = ci.contagem_id
        WHERE c.finalizada = 1 AND ci.quantidade IS NOT NULL
        ORDER BY c.data, c.id
    """).fetchall()
    compras = conn.execute("SELECT insumo_id, quantidade, unidade, data FROM compras ORDER BY data").fetchall()
    desperdicios = conn.execute("""
        SELECT insumo_id, quantidade, unidade, data FROM desperdicios
        WHERE status = 'aprovado' AND insumo_id IS NOT NULL ORDER BY data
    """).fetchall()
    movimentos = [
        {"insumo_id": m["insumo_id"], "data": m["data"], "unidade": m["unidade"], "tipo": m["tipo"],
         "quantidade": m["quantidade"] * TIPOS.get(m["tipo"], {"fator": 0})["fator"]}
        for m in conn.execute("SELECT * FROM movimentacoes ORDER BY data")
        if TIPOS.get(m["tipo"], {"fator": 0})["fator"]
    ]
    conversoes = carregar_conversoes(conn)
    conn.close()
    if ate:
        itens = [i for i in itens if i["data"] < ate]
        compras = [c for c in compras if c["data"] < ate]
        desperdicios = [d for d in desperdicios if d["data"] < ate]
        movimentos = [m for m in movimentos if m["data"] < ate]
    movimentos_por_insumo = {}
    for m in movimentos:
        movimentos_por_insumo.setdefault(m["insumo_id"], []).append(m)

    contagens_por_insumo, compras_por_insumo, desperdicios_por_insumo = {}, {}, {}
    for item in itens:
        lista = contagens_por_insumo.setdefault(item["insumo_id"], [])
        # Duas contagens no mesmo dia: vale a última
        if lista and lista[-1]["data"] == item["data"]:
            lista[-1] = item
        else:
            lista.append(item)
    for compra in compras:
        compras_por_insumo.setdefault(compra["insumo_id"], []).append(compra)
    for d in desperdicios:
        desperdicios_por_insumo.setdefault(d["insumo_id"], []).append(d)

    return [
        analisar_insumo(i, contagens_por_insumo.get(i["id"], []), compras_por_insumo.get(i["id"], []), semanas,
                        desperdicios_por_insumo.get(i["id"], []), movimentos_por_insumo.get(i["id"], []),
                        conversoes.get(i["id"], []))
        for i in insumos
    ]


def divergencias(contagem):
    """Compara cada item contado com o que o sistema tinha logo antes da contagem
    (contagem anterior + compras − saídas − desperdício aprovado até a véspera)."""
    from insumo_cadastro import carregar_conversoes
    sistema = {l["id"]: l for l in calcular_linhas(ate=contagem["data"])}
    precos = {l["id"]: l for c in calcular_valor_estoque()["categorias"] for l in c["itens"]}
    conn = get_connection()
    itens = conn.execute("""
        SELECT ci.insumo_id, ci.quantidade, ci.unidade, ci.justificativa, i.nome, i.categoria FROM contagem_itens ci
        JOIN insumos i ON i.id = ci.insumo_id WHERE ci.contagem_id = ? AND ci.quantidade IS NOT NULL
    """, (contagem["id"],)).fetchall()
    conversoes = carregar_conversoes(conn)
    conn.close()
    linhas = {}
    for item in itens:
        linha = {"id": item["insumo_id"], "nome": item["nome"], "categoria": item["categoria"],
                 "unidade": item["unidade"], "contado": item["quantidade"], "esperado": None,
                 "diferenca": None, "valor": None, "justificativa": item["justificativa"]}
        antes = sistema.get(item["insumo_id"])
        conv = conversoes.get(item["insumo_id"], [])
        if antes and antes["estoque"] is not None:
            linha["esperado"] = converter(antes["estoque"], antes["unidade"], item["unidade"], conv)
        if linha["esperado"] is not None:
            linha["diferenca"] = round(item["quantidade"] - linha["esperado"], 3)
            preco = precos.get(item["insumo_id"])
            if preco:
                # preço por unidade do estoque atual → por unidade desta contagem
                por_unidade = converter(1, item["unidade"], preco["unidade"], conv)
                if por_unidade is not None:
                    linha["valor"] = linha["diferenca"] * por_unidade * preco["preco"]
        linhas[item["insumo_id"]] = linha
    com_diferenca = [l for l in linhas.values() if l["diferenca"]]
    resumo = {
        "comparados": sum(1 for l in linhas.values() if l["esperado"] is not None),
        "com_diferenca": len(com_diferenca),
        "faltou": sum(l["valor"] for l in com_diferenca if l["valor"] and l["valor"] < 0),
        "sobrou": sum(l["valor"] for l in com_diferenca if l["valor"] and l["valor"] > 0),
    }
    return linhas, resumo


@bp.route("/relatorio/divergencias")
def relatorio_divergencias():
    conn = get_connection()
    contagens = conn.execute(
        "SELECT * FROM contagens WHERE finalizada = 1 ORDER BY data DESC, id DESC LIMIT 30").fetchall()
    conn.close()
    escolhida = request.args.get("contagem", type=int)
    contagem = next((c for c in contagens if c["id"] == escolhida), contagens[0] if contagens else None)
    linhas, resumo = divergencias(contagem) if contagem else ({}, None)
    lista = sorted((l for l in linhas.values() if l["diferenca"]),
                   key=lambda l: (l["valor"] is None, l["valor"] or 0, l["diferenca"]))
    return render_template("divergencias.html", contagens=contagens, contagem=contagem, linhas=lista,
                           resumo=resumo)


@bp.route("/relatorio")
def relatorio():
    semanas = request.args.get("semanas", 1, type=float)
    if semanas not in (1, 1.5, 2, 3, 4):
        semanas = 1
    linhas = calcular_linhas(semanas)
    return render_template(
        "relatorio.html", semanas=semanas,
        comprar=agrupar_por_categoria([l for l in linhas if l["status"] == "comprar"]),
        bons=sorted([l for l in linhas if l["status"] == "bom"], key=lambda l: -(l["dias_cobertura"] or 10**9)),
        sem_dados=sorted([l for l in linhas if l["status"] == "sem_dados"], key=lambda l: sem_acento(l["nome"])),
    )


@bp.route("/relatorio/comparar", methods=["GET", "POST"])
def comparar():
    erro = None
    resultado = None
    texto = request.form.get("texto", "")

    if request.method == "POST":
        arquivo = request.files.get("arquivo")
        try:
            if arquivo and arquivo.filename:
                linhas_arquivo = ler_arquivo(arquivo.filename, arquivo.read())
            elif texto.strip():
                linhas_arquivo = ler_texto(texto)
            else:
                linhas_arquivo = None
                erro = "Cole o texto da lista ou anexe um arquivo."
            if linhas_arquivo is not None:
                app = calcular_linhas()
                itens = extrair_itens(linhas_arquivo, sorted({l["categoria"] for l in app}))
                itens = [i for i in itens if i["quantidade"] is not None]
                if not itens:
                    erro = ("Não encontrei itens com quantidade. Use uma linha por insumo, por exemplo "
                            "\"Bacon 2 kg\". Foto de lista escrita à mão não dá para ler.")
                else:
                    resultado = montar_comparacao(itens, app)
        except ValueError as e:
            erro = str(e)
        except Exception:
            erro = "Não consegui ler esse arquivo. Confira se ele não está corrompido ou protegido por senha."

    return render_template("comparar.html", erro=erro, resultado=resultado, texto=texto)




def montar_comparacao(itens, linhas_app):
    por_nome = {chave_nome(l["nome"]): l for l in linhas_app}
    resultado = {"linhas": [], "nao_encontrados": [], "faltando_na_lista": []}
    usados = set()
    for item in itens:
        app = por_nome.get(chave_nome(item["nome"]))
        if app is None:
            resultado["nao_encontrados"].append(item)
            continue
        usados.add(app["id"])
        linha = {"nome": app["nome"], "lista": item["quantidade"], "unidade_lista": item["unidade"] or app["unidade"],
                 "app": app["estoque"], "unidade": app["unidade"], "diferenca": None}
        if app["estoque"] is None:
            linha["situacao"] = "sem_contagem"
        elif converter(item["quantidade"], linha["unidade_lista"], app["unidade"]) is None:
            linha["situacao"] = "unidade"
        else:
            linha["lista"] = converter(item["quantidade"], linha["unidade_lista"], app["unidade"])
            linha["unidade_lista"] = app["unidade"]
            linha["diferenca"] = round(linha["lista"] - app["estoque"], 3)
            tolerancia = max(0.01, abs(app["estoque"]) * 0.05)
            if abs(linha["diferenca"]) <= tolerancia:
                linha["situacao"] = "ok"
            else:
                linha["situacao"] = "sobra" if linha["diferenca"] > 0 else "falta"
        resultado["linhas"].append(linha)
    ordem = {"falta": 0, "sobra": 1, "unidade": 2, "sem_contagem": 3, "ok": 4}
    resultado["linhas"].sort(key=lambda l: (ordem[l["situacao"]], sem_acento(l["nome"])))
    resultado["faltando_na_lista"] = sorted(
        (l["nome"] for l in linhas_app if l["id"] not in usados and l["estoque"]), key=sem_acento)
    resultado["divergentes"] = sum(1 for l in resultado["linhas"] if l["situacao"] in ("falta", "sobra"))
    return resultado


# ---------- Saída por semana (entre duas contagens) ----------

def contagens_finalizadas(conn):
    return conn.execute("SELECT * FROM contagens WHERE finalizada = 1 ORDER BY data, id").fetchall()


def escolher_periodo(contagens):
    """Contagens de início e fim pedidas na URL; por padrão, as duas últimas."""
    por_id = {c["id"]: c for c in contagens}
    inicio = por_id.get(request.args.get("inicio", type=int))
    fim = por_id.get(request.args.get("fim", type=int))
    if not (inicio and fim) and len(contagens) >= 2:
        inicio, fim = contagens[-2], contagens[-1]
    if inicio and fim and (inicio["data"], inicio["id"]) > (fim["data"], fim["id"]):
        inicio, fim = fim, inicio
    return inicio, fim


def calcular_saida(conn, inicio, fim):
    """Saída de cada insumo = contagem inicial + compras - contagem final.
    Vendido/usado = saída - desperdício aprovado no período."""
    def quantidades(contagem_id):
        return {r["insumo_id"]: r for r in conn.execute(
            "SELECT insumo_id, quantidade, unidade FROM contagem_itens WHERE contagem_id = ? AND quantidade IS NOT NULL",
            (contagem_id,))}

    def movimentos(sql):
        totais = {}
        for r in conn.execute(sql, (inicio["data"], fim["data"])):
            chave = (r["insumo_id"], r["unidade"])
            totais[chave] = totais.get(chave, 0) + r["quantidade"]
        return totais

    ini, fin = quantidades(inicio["id"]), quantidades(fim["id"])
    compras = movimentos("SELECT insumo_id, quantidade, unidade FROM compras WHERE data >= ? AND data < ?")
    perdas = movimentos("""SELECT insumo_id, quantidade, unidade FROM desperdicios
                           WHERE status = 'aprovado' AND data >= ? AND data < ?""")
    linhas, incompletos = [], []
    for insumo in conn.execute("SELECT * FROM insumos"):
        a, b = ini.get(insumo["id"]), fin.get(insumo["id"])
        if not a and not b:
            continue
        if not a or not b or a["unidade"] != b["unidade"]:
            incompletos.append(insumo["nome"])
            continue
        unidade = b["unidade"]
        entrada = compras.get((insumo["id"], unidade), 0)
        perda = perdas.get((insumo["id"], unidade), 0)
        saida = round(a["quantidade"] + entrada - b["quantidade"], 3)
        linhas.append({
            "nome": insumo["nome"], "categoria": insumo["categoria"], "unidade": unidade,
            "inicio": a["quantidade"], "compras": entrada, "desperdicio": perda, "final": b["quantidade"],
            "saida": saida, "vendido": round(saida - perda, 3), "inconsistente": saida < 0,
        })
    return linhas, sorted(incompletos, key=sem_acento)


@bp.route("/relatorio/semanas")
def semanas():
    conn = get_connection()
    contagens = contagens_finalizadas(conn)
    inicio, fim = escolher_periodo(contagens)
    linhas, incompletos = calcular_saida(conn, inicio, fim) if inicio and fim and inicio["id"] != fim["id"] else ([], [])
    conn.close()
    pares = list(zip(contagens, contagens[1:]))[::-1][:12]
    dias = (dia(fim["data"]) - dia(inicio["data"])).days if inicio and fim else 0
    return render_template(
        "semanas.html", contagens=contagens, inicio=inicio, fim=fim, dias=dias, pares=pares,
        grupos=agrupar_por_categoria(linhas), incompletos=incompletos,
        inconsistentes=sum(1 for l in linhas if l["inconsistente"]),
    )


@bp.route("/relatorio/semanas/csv")
def semanas_csv():
    conn = get_connection()
    inicio, fim = escolher_periodo(contagens_finalizadas(conn))
    if not (inicio and fim) or inicio["id"] == fim["id"]:
        conn.close()
        return Response("Escolha duas contagens finalizadas.", status=400)
    linhas, _ = calcular_saida(conn, inicio, fim)
    conn.close()

    from exportar import responder
    tabela = [[categoria, l["nome"], l["unidade"]] + [formatar_quantidade(l[c]) for c in
              ("inicio", "compras", "desperdicio", "final", "saida", "vendido")]
              for categoria, itens in agrupar_por_categoria(linhas) for l in itens]
    return responder(f"saida_{inicio['data']}_a_{fim['data']}", "Saída por semana",
                     ["Categoria", "Insumo", "Unidade", "Contagem inicial", "Compras", "Desperdício aprovado",
                      "Contagem final", "Saída total", "Vendido / usado"], tabela,
                     subtitulo=f"Período: {data_br_filter(inicio['data'])} a {data_br_filter(fim['data'])}")


# ---------- Valor do estoque ----------

def calcular_valor_estoque():
    """Estoque atual de cada insumo × último preço pago (valor da nota ÷ quantidade)."""
    linhas = calcular_linhas()
    conn = get_connection()
    compras_com_valor = conn.execute("""
        SELECT insumo_id, quantidade, unidade, valor_total, data FROM compras
        WHERE valor_total IS NOT NULL AND quantidade > 0
        ORDER BY data DESC, id DESC
    """).fetchall()
    conn.close()
    por_insumo = {}
    for compra in compras_com_valor:
        por_insumo.setdefault(compra["insumo_id"], []).append(compra)

    com_preco, sem_preco = [], []
    sem_contagem = 0
    for linha in linhas:
        if linha["estoque"] is None:
            sem_contagem += 1
            continue
        if linha["estoque"] <= 0:
            continue
        compras = por_insumo.get(linha["id"], [])
        # Último preço numa unidade que dá para converter para a do estoque
        preco = None
        for compra in compras:
            fator = converter(1, compra["unidade"], linha["unidade"], linha["conversoes"])
            if fator:
                preco = compra["valor_total"] / compra["quantidade"] / fator
                linha["preco_data"] = compra["data"]
                break
        if preco is None and linha.get("custo"):
            # Sem compra com valor: usa o custo de referência da ficha do insumo
            linha.update(preco=linha["custo"], preco_medio=linha["custo"], preco_data=None, compras_com_valor=0,
                         valor=linha["custo"] * linha["estoque"], valor_medio=linha["custo"] * linha["estoque"],
                         preco_referencia=True)
            com_preco.append(linha)
            continue
        if preco is None:
            linha["motivo"] = ("compra registrada em outra unidade" if compras
                               else "nenhuma compra com valor registrado")
            sem_preco.append(linha)
            continue
        # Preço médio ponderado de todas as compras com valor (total pago ÷ quantidade total)
        pago = quantidade = 0.0
        for compra in compras:
            fator = converter(1, compra["unidade"], linha["unidade"], linha["conversoes"])
            if fator:
                pago += compra["valor_total"]
                quantidade += compra["quantidade"] * fator
        linha["preco"] = preco
        linha["preco_medio"] = pago / quantidade if quantidade else preco
        linha["compras_com_valor"] = sum(1 for c in compras if converter(1, c["unidade"], linha["unidade"], linha["conversoes"]))
        linha["valor"] = preco * linha["estoque"]
        linha["valor_medio"] = linha["preco_medio"] * linha["estoque"]
        com_preco.append(linha)

    categorias = []
    for categoria, itens in agrupar_por_categoria(com_preco):
        itens = sorted(itens, key=lambda l: -l["valor"])
        categorias.append({"nome": categoria, "itens": itens, "total": sum(l["valor"] for l in itens),
                           "total_medio": sum(l["valor_medio"] for l in itens)})
    return {
        "categorias": categorias,
        "total": sum(c["total"] for c in categorias),
        "total_medio": sum(c["total_medio"] for c in categorias),
        "sem_preco": sorted(sem_preco, key=lambda l: sem_acento(l["nome"])),
        "sem_contagem": sem_contagem,
        "com_preco": len(com_preco),
    }


@bp.route("/relatorio/valor")
def valor_estoque():
    # O valor do estoque agora fica no painel do Estoque
    return redirect(url_for("relatorio.estoque"))


def montar_estoque():
    valor = calcular_valor_estoque()
    precos = {l["id"]: l for c in valor["categorias"] for l in c["itens"]}
    linhas = [l for l in calcular_linhas() if l["estoque"] is not None and (l["ativo"] or l["estoque"] > 0)]
    for linha in linhas:
        com_preco = precos.get(linha["id"])
        if com_preco:
            linha.update(preco=com_preco["preco"], preco_medio=com_preco["preco_medio"],
                         valor=com_preco["valor"], valor_medio=com_preco["valor_medio"],
                         preco_referencia=com_preco.get("preco_referencia", False))
    return valor, linhas


@bp.route("/estoque")
def estoque():
    """Painel: estoque atual (última contagem + compras − saídas − desperdício), alertas e valor pelas notas."""
    valor, linhas = montar_estoque()
    categorias = [{"nome": cat, "itens": itens, "total": sum(l.get("valor", 0) for l in itens)}
                  for cat, itens in agrupar_por_categoria(linhas)]
    alertas = {
        "abaixo_minimo": sorted((l for l in linhas if l["situacao"] == "abaixo_minimo"), key=lambda l: l["nome"]),
        "sem_saldo": sorted((l for l in linhas if l["situacao"] == "sem_saldo"), key=lambda l: l["nome"]),
    }
    conn = get_connection()
    ultima_contagem = conn.execute(
        "SELECT * FROM contagens WHERE finalizada = 1 ORDER BY data DESC, id DESC LIMIT 1").fetchone()
    ultimas_entradas = conn.execute("""
        SELECT c.data, c.quantidade, c.unidade, c.fornecedor, i.nome, i.id AS insumo_id FROM compras c
        JOIN insumos i ON i.id = c.insumo_id ORDER BY c.data DESC, c.id DESC LIMIT 5
    """).fetchall()
    ultimas_saidas = conn.execute("""
        SELECT * FROM (
            SELECT m.data, m.id, m.quantidade, m.unidade, m.tipo, i.nome, i.id AS insumo_id FROM movimentacoes m
            JOIN insumos i ON i.id = m.insumo_id WHERE m.tipo != 'transferencia'
            UNION ALL
            SELECT d.data, d.id, d.quantidade, d.unidade, 'desperdicio' AS tipo, d.insumo_nome AS nome,
                   d.insumo_id FROM desperdicios d WHERE d.status = 'aprovado'
        ) ORDER BY data DESC, id DESC LIMIT 5
    """).fetchall()
    # Desperdício lançado pela equipe que ainda espera a gerência: ainda não saiu do estoque
    pendentes = conn.execute("""
        SELECT insumo_id, quantidade, unidade, data FROM desperdicios
        WHERE status = 'pendente' AND insumo_id IS NOT NULL
    """).fetchall()
    # Compras cuja medida não converte para a do estoque (ex.: cx para un sem "1 cx = 12 un"): não somaram
    from compras import fora_do_estoque
    compras = conn.execute("SELECT id, insumo_id, data, unidade FROM compras ORDER BY data").fetchall()
    fora = fora_do_estoque(conn, compras)
    # Validade dos lotes comprados: vencidos ou vencendo nos próximos 7 dias, de insumos que ainda têm saldo
    limite = (config.hoje() + timedelta(days=7)).isoformat()
    lotes = conn.execute("""
        SELECT c.validade, c.quantidade, c.unidade, c.insumo_id, i.nome FROM compras c
        JOIN insumos i ON i.id = c.insumo_id
        WHERE c.validade != '' AND c.validade <= ? ORDER BY c.validade
    """, (limite,)).fetchall()
    conn.close()
    por_id = {l["id"]: l for l in linhas}
    hoje_iso = config.hoje().isoformat()
    validades = [{"nome": v["nome"], "insumo_id": v["insumo_id"], "validade": v["validade"],
                  "quantidade": v["quantidade"], "unidade": v["unidade"], "vencido": v["validade"] < hoje_iso}
                 for v in lotes if (por_id.get(v["insumo_id"]) or {}).get("estoque", 0) > 0]
    for c in compras:
        motivo = fora.get(c["id"])
        linha = por_id.get(c["insumo_id"])
        if linha is not None and motivo and motivo["motivo"] == "unidade":
            linha["nao_somou"] = linha.get("nao_somou", 0) + 1
            linha["nao_somou_unidade"] = c["unidade"]
            linha["nao_somou_mes"] = c["data"][:7]
    total_pendentes = 0
    for d in pendentes:
        linha = por_id.get(d["insumo_id"])
        if linha is None or (linha["ultima_contagem"] and d["data"] < linha["ultima_contagem"]):
            continue
        quantidade = converter(d["quantidade"], d["unidade"], linha["unidade"], linha["conversoes"])
        if quantidade:
            linha["pendente"] = linha.get("pendente", 0) + quantidade
            total_pendentes += 1
    from movimentos import TIPOS
    locais = sorted({l["local"] for l in linhas if l["local"]})
    return render_template(
        "estoque.html", categorias=categorias, total=valor["total"], total_medio=valor["total_medio"],
        itens=len(linhas), sem_preco=len(valor["sem_preco"]), sem_contagem=valor["sem_contagem"],
        alertas=alertas, ultima_contagem=ultima_contagem, ultimas_entradas=ultimas_entradas,
        ultimas_saidas=ultimas_saidas, tipos=TIPOS, locais=locais, total_pendentes=total_pendentes,
        validades=validades,
    )


@bp.route("/estoque/csv")
def estoque_csv():
    from exportar import responder
    _, linhas = montar_estoque()
    tabela = []
    situacoes = {"ok": "OK", "abaixo_minimo": "Abaixo do mínimo", "sem_saldo": "Sem saldo"}

    def numero(v, casas=3):
        if v is None:
            return ""
        return f"{v:.2f}".replace(".", ",") if casas == 2 else formatar_quantidade(round(v, 3))

    for categoria, itens in agrupar_por_categoria(linhas):
        for l in itens:
            tabela.append([categoria, l["nome"], l["local"], numero(l["estoque"]), l["unidade"],
                           numero(l["minimo"]), situacoes.get(l["situacao"], ""), data_br_filter(l["ultima_contagem"]) if l["ultima_contagem"] else "",
                           numero(l.get("preco"), 2), numero(l.get("valor"), 2)])
    hoje = config.hoje()
    return responder(f"estoque_{hoje.isoformat()}", "Estoque - Gestor Full de Restaurante",
                     ["Categoria", "Insumo", "Local", "Estoque", "Unidade", "Mínimo", "Situação", "Última contagem",
                      "Preço (R$)", "Valor (R$)"], tabela, subtitulo=f"La Barca · {hoje.strftime('%d/%m/%Y')}")


# ---------- Conferir pedido de compra ----------

def montar_conferencia(itens, linhas_app):
    """Compara cada item do pedido com a sugestão de compra do relatório."""
    from notas import achar_insumo
    por_id = {l["id"]: l for l in linhas_app}
    resultado = {"linhas": [], "nao_encontrados": [], "faltou_pedir": []}
    usados = set()
    for item in itens:
        insumo_id = achar_insumo(item["nome"], linhas_app, {})
        app = por_id.get(insumo_id)
        if app is None:
            resultado["nao_encontrados"].append(item)
            continue
        usados.add(app["id"])
        unidade_pedido = item["unidade"] or app["unidade"]
        linha = {"nome": app["nome"], "nome_pedido": item["nome"], "pedido": item["quantidade"],
                 "unidade_pedido": unidade_pedido, "unidade": app["unidade"], "estoque": app["estoque"],
                 "ultima_contagem": app["ultima_contagem"],
                 "consumo": app["consumo_semanal"], "sugestao": app["sugestao"], "dias": app["dias_cobertura"]}
        convertido = converter(item["quantidade"], unidade_pedido, app["unidade"], app.get("conversoes", ()))
        if app["estoque"] is None:
            linha["situacao"] = "sem_contagem"
        elif convertido is None:
            linha["situacao"] = "unidade"
        elif app["consumo_semanal"] is None:
            linha["situacao"] = "sem_historico"
        else:
            linha["pedido"], linha["unidade_pedido"] = convertido, app["unidade"]
            sugestao = app["sugestao"]
            folga = max(0.1, sugestao * 0.3)
            if sugestao <= 0:
                linha["situacao"] = "desnecessario"
            elif convertido > sugestao + folga:
                linha["situacao"] = "demais"
                linha["diferenca"] = convertido - sugestao
            elif convertido < sugestao - folga:
                linha["situacao"] = "pouco"
                linha["diferenca"] = sugestao - convertido
            else:
                linha["situacao"] = "ok"
        resultado["linhas"].append(linha)
    ordem = {"desnecessario": 0, "demais": 1, "pouco": 2, "unidade": 3, "sem_historico": 4, "sem_contagem": 5, "ok": 6}
    resultado["linhas"].sort(key=lambda l: (ordem[l["situacao"]], sem_acento(l["nome"])))
    resultado["faltou_pedir"] = sorted(
        (l for l in linhas_app if l["status"] == "comprar" and l["id"] not in usados), key=lambda l: sem_acento(l["nome"]))
    contagem = {}
    for l in resultado["linhas"]:
        contagem[l["situacao"]] = contagem.get(l["situacao"], 0) + 1
    resultado["contagem"] = contagem
    return resultado


@bp.route("/relatorio/pedido", methods=["GET", "POST"])
def conferir_pedido():
    erro = None
    resultado = None
    texto = request.form.get("texto", "")
    semanas = request.values.get("semanas", 1, type=float)
    if semanas not in (1, 1.5, 2, 3, 4):
        semanas = 1

    if request.method == "POST":
        arquivo = request.files.get("arquivo")
        try:
            if texto.strip():
                linhas_arquivo = ler_texto(texto)
            elif arquivo and arquivo.filename:
                linhas_arquivo = ler_arquivo(arquivo.filename, arquivo.read())
            else:
                linhas_arquivo = None
                erro = "Digite o pedido ou anexe o arquivo."
            if linhas_arquivo is not None:
                app = calcular_linhas(semanas)
                itens = extrair_itens(linhas_arquivo, sorted({l["categoria"] for l in app}))
                itens = [i for i in itens if i["quantidade"] is not None]
                if not itens:
                    erro = ("Não encontrei itens com quantidade no pedido. Use uma linha por item, por exemplo "
                            "\"Bacon 2 kg\". Foto de papel escrito à mão não dá para ler.")
                else:
                    resultado = montar_conferencia(itens, app)
        except ValueError as e:
            erro = str(e)
        except Exception:
            erro = "Não consegui ler esse arquivo. Confira se ele não está corrompido ou protegido por senha."

    return render_template("conferir_pedido.html", erro=erro, resultado=resultado, texto=texto, semanas=semanas)
