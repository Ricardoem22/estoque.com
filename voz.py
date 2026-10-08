# voz.py
# Assistente por voz (ou texto): o celular transforma a fala em texto pelo próprio navegador e o app
# entende comandos simples. Nada é gravado sem o funcionário confirmar.
#
#   "quanto tem de cerveja"                → responde o estoque
#   "comprei 2 caixas de cerveja por 90"   → compra (confirma antes)
#   "saída de 3 quilos de tomate"          → movimentação de saída (confirma antes)
#   "desperdício de 1 quilo de alface"     → abre o Desperdício preenchido (a foto é obrigatória)
#   "abrir compras"                        → abre a aba
import re

from flask import Blueprint, jsonify, request, session, url_for

import config
from contagem import formatar_quantidade, get_connection
from importador import sem_acento

bp = Blueprint("voz", __name__)

NUMEROS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
    "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "quatorze": 14, "catorze": 14,
    "quinze": 15, "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "cem": 100, "meio": 0.5,
    "meia": 0.5,
}
# Palavra falada → unidade do app
UNIDADES_FALADAS = {
    "kg": "kg", "quilo": "kg", "quilos": "kg", "kilo": "kg", "kilos": "kg", "quilograma": "kg",
    "quilogramas": "kg", "g": "g", "grama": "g", "gramas": "g", "l": "L", "litro": "L", "litros": "L",
    "ml": "ml", "mililitro": "ml", "mililitros": "ml", "un": "un", "unidade": "un", "unidades": "un",
    "cx": "cx", "caixa": "cx", "caixas": "cx", "pct": "pct", "pacote": "pct", "pacotes": "pct",
    "fardo": "fardo", "fardos": "fardo", "lata": "lata", "latas": "lata", "garrafa": "garrafa",
    "garrafas": "garrafa", "saco": "saco", "sacos": "saco", "duzia": "dz", "duzias": "dz",
    "bandeja": "bandeja", "bandejas": "bandeja", "peca": "peça", "pecas": "peça",
}
INTENCOES = [
    ("desperdicio", ("desperdic", "estragou", "estragado", "venceu", "vencido", "perdi", "joguei", "jogar fora")),
    ("compra", ("compr", "chegou", "chegaram", "recebi", "recebemos", "entrada")),
    ("saida", ("saida", "usei", "usamos", "retirei", "tirei", "consumi", "gastei", "baixa", "baixar")),
    ("consulta", ("quanto", "quantos", "quantas", "estoque de", "saldo", "tem de", "temos de", "sobrou")),
]
PAGINAS = [
    (("estoque", "painel", "inicio"), "relatorio.estoque"),
    (("contagem", "contar"), "contagem.contagens"),
    (("insumo",), "contagem.insumos"),
    (("compra", "nota"), "compras.compras"),
    (("desperdicio",), "desperdicio.desperdicio"),
    (("movimenta", "saida"), "movimentos.movimentacoes"),
    (("relatorio",), "relatorio.relatorio"),
    (("divergen",), "relatorio.divergencias"),
    (("mural", "recado"), "mural.mural"),
]
NAVEGAR = ("abrir", "abre", "abra", "ir para", "vai para", "va para", "mostrar", "mostra", "ver ", "entrar")
# Palavras que não ajudam a achar o insumo
IGNORAR = {
    "de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "no", "na", "em", "com", "para", "pra", "por",
    "reais", "real", "rs", "tem", "temos", "ainda", "hoje", "agora", "lancar", "lanca", "registrar", "registra",
    "ai", "voce", "me", "diz", "fala", "qual", "quanto", "quantos", "quantas", "estoque", "saldo", "sobrou",
    "que", "eu", "nos", "foi", "foram", "mais", "favor", "porfavor", "ok", "um", "uma",
}


def _numero(palavra):
    palavra = palavra.replace(",", ".")
    if re.fullmatch(r"\d+(\.\d+)?", palavra):
        return float(palavra)
    return NUMEROS.get(palavra)


def _raiz(palavra):
    # "tomates" ≈ "tomate", "limoes" ≈ "limao"
    for fim, troca in (("oes", "ao"), ("aes", "ao"), ("es", ""), ("s", "")):
        if len(palavra) > 3 and palavra.endswith(fim):
            return palavra[: -len(fim)] + troca
    return palavra


def _palavras(texto):
    return [p for p in re.findall(r"[a-z0-9]+", sem_acento(texto))]


def achar_insumos(palavras, insumos):
    """Insumos ordenados pelo quanto o nome bate com o que foi falado."""
    faladas = {_raiz(p) for p in palavras if p not in IGNORAR and not p.isdigit()}
    if not faladas:
        return []
    pontuados = []
    for insumo in insumos:
        nome = {_raiz(p) for p in _palavras(insumo["nome"]) if p not in IGNORAR}
        if not nome:
            continue
        acertos = len(nome & faladas)
        # aceita começo de palavra a partir de 4 letras ("refri" → "refrigerante")
        acertos += sum(0.5 for f in faladas - nome if len(f) >= 4 and any(n.startswith(f) for n in nome))
        if acertos:
            pontuados.append((-acertos, len(nome - faladas), insumo["nome"].lower(), insumo))
    pontuados.sort(key=lambda t: t[:3])
    return [t[3] for t in pontuados]


def interpretar(texto, insumos):
    """Transforma a frase em {tipo, quantidade, unidade, valor, insumos} sem tocar no banco."""
    limpo = sem_acento(texto)
    if limpo.startswith(NAVEGAR):
        tipo = "navegar"
    else:
        tipo = next((t for t, chaves in INTENCOES if any(c in limpo for c in chaves)), None)

    valor = None
    achado = re.search(r"(?:por|r\$|valor|paguei|custou)\s*r?\$?\s*(\d+(?:[.,]\d+)?)(?:\s*reais)?", limpo) \
        or re.search(r"(\d+(?:[.,]\d+)?)\s*reais", limpo)
    if achado:
        valor = float(achado.group(1).replace(",", "."))
        limpo = limpo[:achado.start()] + " " + limpo[achado.end():]

    palavras = re.findall(r"\d+(?:[.,]\d+)?|[a-z]+", limpo)
    quantidade, unidade, resto = None, None, []
    for i, palavra in enumerate(palavras):
        numero = _numero(palavra)
        seguinte = palavras[i + 1] if i + 1 < len(palavras) else ""
        if numero is not None and quantidade is None and (palavra not in ("um", "uma") or seguinte in UNIDADES_FALADAS
                                                          or _numero(seguinte) is None):
            quantidade = numero
            continue
        if palavra in ("e",) and quantidade is not None and seguinte in ("meio", "meia"):
            quantidade += 0.5
            continue
        if palavra in ("meio", "meia") and quantidade is not None:
            continue
        if palavra in UNIDADES_FALADAS and unidade is None and (quantidade is not None or i > 0):
            unidade = UNIDADES_FALADAS[palavra]
            continue
        resto.append(palavra)

    chaves = [c for _, cs in INTENCOES for c in cs] + list(NAVEGAR)
    resto = [p for p in resto if not any(p.startswith(c.strip()) for c in chaves if " " not in c.strip())]
    return {"tipo": tipo, "quantidade": quantidade, "unidade": unidade, "valor": valor,
            "insumos": achar_insumos(resto, insumos), "palavras": resto}


def _linha_estoque(insumo_id):
    from relatorio import calcular_linhas
    return next((l for l in calcular_linhas() if l["id"] == insumo_id), None)


def _texto_estoque(insumo):
    linha = _linha_estoque(insumo["id"])
    if not linha or linha["estoque"] is None:
        return f"{insumo['nome']}: ainda sem contagem nem compra."
    return f"{insumo['nome']}: {formatar_quantidade(round(linha['estoque'], 2))} {linha['unidade']} em estoque."


def _unidade_destino(conn, insumo, tipo):
    if tipo == "compra":
        from compras import ultimas_contagens
        ultima = ultimas_contagens(conn).get(insumo["id"])
        if ultima:
            return ultima["unidade"]
    return insumo["unidade"]


EXEMPLOS = ('Tente: "quanto tem de cerveja", "comprei 2 caixas de cerveja por 90 reais", '
            '"saída de 3 quilos de tomate", "desperdício de 1 quilo de alface" ou "abrir compras".')


@bp.route("/voz/entender", methods=["POST"])
def entender():
    texto = (request.get_json(silent=True) or {}).get("texto", "").strip()[:300]
    if not texto:
        return jsonify(tipo="erro", resposta="Não ouvi nada. " + EXEMPLOS)
    conn = get_connection()
    insumos = conn.execute("SELECT * FROM insumos WHERE ativo = 1").fetchall()
    pedido = interpretar(texto, insumos)
    tipo = pedido["tipo"]

    if tipo == "navegar" or (tipo is None and not pedido["insumos"]):
        limpo = sem_acento(texto)
        for chaves, endpoint in PAGINAS:
            if any(c in limpo for c in chaves):
                conn.close()
                return jsonify(tipo="navegar", url=url_for(endpoint), resposta="Abrindo…")
        if not pedido["insumos"]:
            conn.close()
            return jsonify(tipo="erro", resposta=f'Não entendi "{texto}". ' + EXEMPLOS)
        tipo = None  # "mostra o tomate": responde o estoque

    if not pedido["insumos"]:
        conn.close()
        return jsonify(tipo="erro", resposta=f'Não achei nenhum insumo em "{texto}". Fale o nome como está na aba Insumos.')

    insumo = pedido["insumos"][0]
    if tipo in (None, "consulta"):
        conn.close()
        respostas = [_texto_estoque(i) for i in pedido["insumos"][:3]]
        return jsonify(tipo="consulta", resposta=" ".join(respostas))

    unidade = pedido["unidade"] or _unidade_destino(conn, insumo, tipo)
    quantidade = pedido["quantidade"]
    opcoes = [{"id": i["id"], "nome": i["nome"], "unidade": i["unidade"]} for i in pedido["insumos"][:6]]
    conn.close()
    if tipo == "desperdicio":
        url = url_for("desperdicio.desperdicio", insumo_id=insumo["id"], unidade=unidade,
                      quantidade=formatar_quantidade(quantidade) if quantidade else "")
        return jsonify(tipo="desperdicio", url=url, opcoes=opcoes, insumo_id=insumo["id"], quantidade=quantidade,
                       unidade=unidade,
                       resposta="O desperdício precisa de foto. Vou abrir o formulário já preenchido.")
    if not quantidade:
        return jsonify(tipo="erro", resposta=f"Quanto de {insumo['nome']}? Fale a quantidade, ex.: \"2 quilos\".")
    acao = "Lançar compra" if tipo == "compra" else "Lançar saída"
    return jsonify(tipo=tipo, insumo_id=insumo["id"], quantidade=quantidade, unidade=unidade, valor=pedido["valor"],
                   opcoes=opcoes, resposta=f"{acao}?")


@bp.route("/voz/confirmar", methods=["POST"])
def confirmar():
    from insumo_cadastro import carregar_conversoes
    from unidades import converter
    dados = request.get_json(silent=True) or {}
    tipo = dados.get("tipo")
    if tipo not in ("compra", "saida"):
        return jsonify(ok=False, resposta="Nada para confirmar.")
    try:
        quantidade = float(dados.get("quantidade"))
        valor = float(dados["valor"]) if dados.get("valor") not in (None, "") else None
        insumo_id = int(dados.get("insumo_id"))
    except (TypeError, ValueError):
        return jsonify(ok=False, resposta="Quantidade ou valor inválido.")
    if quantidade <= 0 or (valor is not None and valor < 0):
        return jsonify(ok=False, resposta="A quantidade precisa ser maior que zero.")
    conn = get_connection()
    insumo = conn.execute("SELECT * FROM insumos WHERE id = ?", (insumo_id,)).fetchone()
    if insumo is None:
        conn.close()
        return jsonify(ok=False, resposta="Insumo não encontrado.")
    unidade = (dados.get("unidade") or "").strip() or _unidade_destino(conn, insumo, tipo)
    destino = _unidade_destino(conn, insumo, tipo)
    if converter(1, unidade, destino, carregar_conversoes(conn).get(insumo["id"], [])) is None:
        conn.close()
        return jsonify(ok=False, resposta=(
            f"{unidade} não converte para {destino} (a unidade do estoque de {insumo['nome']}). "
            f"Escolha {destino} ou cadastre a medida na ficha do insumo, ex.: 1 {unidade} = 12 {destino}."))
    agora = config.agora().strftime("%Y-%m-%d %H:%M:%S")
    hoje = config.hoje().isoformat()
    if tipo == "compra":
        conn.execute("""
            INSERT INTO compras (data, insumo_id, quantidade, unidade, fornecedor, criado_em, valor_total, nota,
                                 observacao, registrado_por, anexo)
            VALUES (?, ?, ?, ?, '', ?, ?, NULL, 'lançado por voz', ?, '')
        """, (hoje, insumo["id"], quantidade, unidade, agora, valor, session.get("nome", "")))
        feito = "Compra lançada"
    else:
        conn.execute("""
            INSERT INTO movimentacoes (data, insumo_id, tipo, quantidade, unidade, motivo, local_origem,
                                       local_destino, responsavel, criado_em)
            VALUES (?, ?, 'saida', ?, ?, 'lançado por voz', ?, '', ?, ?)
        """, (hoje, insumo["id"], quantidade, unidade, insumo["local"] or "", session.get("nome", ""), agora))
        feito = "Saída lançada"
    conn.commit()
    conn.close()
    return jsonify(ok=True, resposta=f"✅ {feito}: {formatar_quantidade(quantidade)} {unidade} de {insumo['nome']}. "
                                     + _texto_estoque(insumo))
