# relatorio.py
# Relatório de estoque: consumo semanal de cada insumo e sugestão de compra.
#
# Consumo entre duas contagens = estoque anterior + compras no período - estoque atual.
# Usa só contagens finalizadas e as últimas MAX_INTERVALOS semanas de cada insumo.
# Estoque atual = última contagem + compras depois dela - desperdício aprovado depois dela.
import csv
import io
import math
from datetime import date

from flask import Blueprint, Response, render_template, request

from contagem import agrupar_por_categoria, data_br_filter, formatar_quantidade, get_connection
from importador import chave_nome, extrair_itens, ler_arquivo, ler_texto, sem_acento

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


def soma_compras(compras, unidade, inicio, fim=None):
    """Compras na unidade dada com data >= inicio e < fim.
    Uma compra no dia da contagem conta como chegada depois da contagem."""
    return sum(
        c["quantidade"] for c in compras
        if c["unidade"] == unidade and c["data"] >= inicio and (fim is None or c["data"] < fim)
    )


def analisar_insumo(insumo, contagens, compras, semanas, desperdicios=()):
    linha = {
        "id": insumo["id"], "nome": insumo["nome"], "categoria": insumo["categoria"],
        "unidade": insumo["unidade"], "estoque": None, "ultima_contagem": None,
        "consumo_semanal": None, "dias_cobertura": None, "sugestao": 0, "status": "sem_dados",
    }
    if not contagens:
        return linha

    ultima = contagens[-1]
    unidade = ultima["unidade"]
    linha["unidade"] = unidade
    linha["ultima_contagem"] = ultima["data"]
    linha["desperdicio"] = soma_compras(desperdicios, unidade, ultima["data"])
    linha["estoque"] = max(0.0, ultima["quantidade"] + soma_compras(compras, unidade, ultima["data"])
                           - linha["desperdicio"])

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
        consumo = anterior["quantidade"] + soma_compras(compras, atual["unidade"], anterior["data"], atual["data"]) \
            - atual["quantidade"]
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


def calcular_linhas(semanas=1):
    conn = get_connection()
    insumos = conn.execute("SELECT * FROM insumos").fetchall()
    itens = conn.execute("""
        SELECT ci.insumo_id, ci.quantidade, ci.unidade, c.data
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
    conn.close()

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
                        desperdicios_por_insumo.get(i["id"], []))
        for i in insumos
    ]


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


CONVERSOES = {("g", "kg"): 0.001, ("kg", "g"): 1000, ("ml", "L"): 0.001, ("L", "ml"): 1000}


def converter(quantidade, de, para):
    if de == para:
        return quantidade
    fator = CONVERSOES.get((de, para))
    return quantidade * fator if fator else None


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

    saida = io.StringIO()
    writer = csv.writer(saida, delimiter=";")
    writer.writerow(["Período", f"{data_br_filter(inicio['data'])} a {data_br_filter(fim['data'])}"])
    writer.writerow([])
    writer.writerow(["Categoria", "Insumo", "Unidade", "Contagem inicial", "Compras", "Desperdício aprovado",
                     "Contagem final", "Saída total", "Vendido / usado"])
    for categoria, itens in agrupar_por_categoria(linhas):
        for l in itens:
            writer.writerow([categoria, l["nome"], l["unidade"]] + [formatar_quantidade(l[c]) for c in
                            ("inicio", "compras", "desperdicio", "final", "saida", "vendido")])
    nome = f"saida_{inicio['data']}_a_{fim['data']}.csv"
    return Response("\ufeff" + saida.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={nome}"})


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
            fator = converter(1, compra["unidade"], linha["unidade"])
            if fator:
                preco = compra["valor_total"] / compra["quantidade"] / fator
                linha["preco_data"] = compra["data"]
                break
        if preco is None:
            linha["motivo"] = ("compra registrada em outra unidade" if compras
                               else "nenhuma compra com valor registrado")
            sem_preco.append(linha)
            continue
        linha["preco"] = preco
        linha["valor"] = preco * linha["estoque"]
        com_preco.append(linha)

    categorias = []
    for categoria, itens in agrupar_por_categoria(com_preco):
        itens = sorted(itens, key=lambda l: -l["valor"])
        categorias.append({"nome": categoria, "itens": itens, "total": sum(l["valor"] for l in itens)})
    return {
        "categorias": categorias,
        "total": sum(c["total"] for c in categorias),
        "sem_preco": sorted(sem_preco, key=lambda l: sem_acento(l["nome"])),
        "sem_contagem": sem_contagem,
        "com_preco": len(com_preco),
    }


@bp.route("/relatorio/valor")
def valor_estoque():
    return render_template("valor_estoque.html", **calcular_valor_estoque())
