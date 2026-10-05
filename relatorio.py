# relatorio.py
# Relatório de estoque: consumo semanal de cada insumo e sugestão de compra.
#
# Consumo entre duas contagens = estoque anterior + compras no período - estoque atual.
# Usa só contagens finalizadas e as últimas MAX_INTERVALOS semanas de cada insumo.
import math
import unicodedata
from datetime import date

from flask import Blueprint, render_template, request

from contagem import agrupar_por_categoria, get_connection

bp = Blueprint("relatorio", __name__)

MAX_INTERVALOS = 4
UNIDADES_FRACIONADAS = {"kg", "L", "lt"}


def sem_acento(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


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


def analisar_insumo(insumo, contagens, compras, semanas):
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
    linha["estoque"] = ultima["quantidade"] + soma_compras(compras, unidade, ultima["data"])

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


@bp.route("/relatorio")
def relatorio():
    semanas = request.args.get("semanas", 1, type=float)
    if semanas not in (1, 1.5, 2, 3, 4):
        semanas = 1

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
    conn.close()

    contagens_por_insumo, compras_por_insumo = {}, {}
    for item in itens:
        lista = contagens_por_insumo.setdefault(item["insumo_id"], [])
        # Duas contagens no mesmo dia: vale a última
        if lista and lista[-1]["data"] == item["data"]:
            lista[-1] = item
        else:
            lista.append(item)
    for compra in compras:
        compras_por_insumo.setdefault(compra["insumo_id"], []).append(compra)

    linhas = [
        analisar_insumo(i, contagens_por_insumo.get(i["id"], []), compras_por_insumo.get(i["id"], []), semanas)
        for i in insumos
    ]
    return render_template(
        "relatorio.html", semanas=semanas,
        comprar=agrupar_por_categoria([l for l in linhas if l["status"] == "comprar"]),
        bons=sorted([l for l in linhas if l["status"] == "bom"], key=lambda l: -(l["dias_cobertura"] or 10**9)),
        sem_dados=sorted([l for l in linhas if l["status"] == "sem_dados"], key=lambda l: sem_acento(l["nome"])),
    )
