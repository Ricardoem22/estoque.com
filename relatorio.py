# relatorio.py
# Relatório de estoque: consumo semanal de cada insumo e sugestão de compra.
#
# Consumo entre duas contagens = estoque anterior + compras no período - estoque atual.
# Usa só contagens finalizadas e as últimas MAX_INTERVALOS semanas de cada insumo.
# Estoque atual = última contagem + compras depois dela - desperdício aprovado depois dela.
import math
from datetime import date

from flask import Blueprint, render_template, request

from contagem import agrupar_por_categoria, get_connection
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
