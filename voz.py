# voz.py
# Assistente por voz (ou texto): o celular transforma a fala em texto pelo próprio navegador e o app
# entende comandos simples. Nada é gravado sem o funcionário confirmar.
#
#   "quanto tem de cerveja"                → responde o estoque
#   "comprei 2 caixas de cerveja por 90"   → compra (confirma antes)
#   "saída de 3 quilos de tomate"          → movimentação de saída (confirma antes)
#   "desperdício de 1 quilo de alface"     → abre o Desperdício preenchido (a foto é obrigatória)
#   "abrir compras"                        → abre a aba
#   "exclua a compra de tomate"            → apaga a última compra do insumo (confirma antes)
#   "adicione 2 quilos de tomate no estoque" → ajuste de entrada (confirma antes)
#   "adicione picanha na lista de insumos" → cadastra o insumo novo (confirma antes)
#   "exclua o tomate do estoque"           → desativa o insumo (confirma antes; reativa na ficha)
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
    (("refeic",), "refeicao.refeicao"),
    (("movimenta", "saida"), "movimentos.movimentacoes"),
    (("relatorio",), "relatorio.relatorio"),
    (("divergen",), "relatorio.divergencias"),
    (("mural", "recado"), "mural.mural"),
]
# Verbos de excluir/adicionar: decidem a ação junto com "compra" ou "estoque" na frase
EXCLUIR = ("exclu", "apag", "remov", "delet", "cancel")
EXCLUIR_PALAVRAS = {"tira", "tire", "tirar", "tirem", "retira", "retire", "retirar"}
ADICIONAR = ("adicion", "acrescent", "inclu", "coloc", "cadastr")
ADICIONAR_PALAVRAS = {"bota", "bote", "botar", "ponha", "ponham"}
NAVEGAR = ("abrir", "abre", "abra", "ir para", "vai para", "va para", "mostrar", "mostra", "ver ", "entrar")
# Palavras que não ajudam a achar o insumo
IGNORAR = {
    "de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "no", "na", "em", "com", "para", "pra", "por",
    "reais", "real", "rs", "tem", "temos", "ainda", "hoje", "agora", "lancar", "lanca", "registrar", "registra",
    "ai", "voce", "me", "diz", "fala", "qual", "quanto", "quantos", "quantas", "estoque", "saldo", "sobrou",
    "que", "eu", "nos", "foi", "foram", "mais", "favor", "porfavor", "ok", "um", "uma", "lista", "item", "itens",
    "insumo", "insumos", "produto", "produtos", "tambem", "ultima", "ultimo",
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


def _pontuar(palavras, insumos):
    """[(acertos, palavras do nome que sobraram, insumo)] dos insumos que batem com o que foi falado."""
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
            pontuados.append((acertos, len(nome - faladas), nome == faladas, insumo))
    pontuados.sort(key=lambda t: (-t[0], t[1], t[3]["nome"].lower()))
    return pontuados


def achar_insumos(palavras, insumos):
    """Insumos ordenados pelo quanto o nome bate com o que foi falado."""
    return [t[3] for t in _pontuar(palavras, insumos)]


def mais_exatos(palavras, insumos):
    """Só o que foi pedido: "frango desfiado" traz o Frango desfiado, não todo insumo com "frango".
    Nome idêntico ao falado vence; senão ficam os que acertaram mais palavras e sobram menos."""
    pontuados = _pontuar(palavras, insumos)
    if not pontuados:
        return []
    exatos = [t[3] for t in pontuados if t[2]]
    if exatos:
        return exatos[:1]
    melhor = pontuados[0][:2]
    return [t[3] for t in pontuados if t[:2] == melhor][:3]


def interpretar(texto, insumos):
    """Transforma a frase em {tipo, quantidade, unidade, valor, insumos} sem tocar no banco."""
    limpo = sem_acento(texto)
    if limpo.startswith(NAVEGAR):
        tipo = "navegar"
    else:
        tipo = next((t for t, chaves in INTENCOES if any(c in limpo for c in chaves)), None)
    todas = re.findall(r"[a-z]+", limpo)
    verbo = None
    if any(p.startswith(EXCLUIR) or p in EXCLUIR_PALAVRAS for p in todas):
        verbo = "excluir"
    elif any(p.startswith(ADICIONAR) or p in ADICIONAR_PALAVRAS for p in todas):
        verbo = "adicionar"
    if verbo:
        tipo = verbo

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

    chaves = [c for _, cs in INTENCOES for c in cs] + list(NAVEGAR) + list(EXCLUIR) + list(ADICIONAR)
    resto = [p for p in resto if not any(p.startswith(c.strip()) for c in chaves if " " not in c.strip())
             and p not in EXCLUIR_PALAVRAS and p not in ADICIONAR_PALAVRAS]
    return {"tipo": tipo, "quantidade": quantidade, "unidade": unidade, "valor": valor,
            "insumos": achar_insumos(resto, insumos), "exatos": mais_exatos(resto, insumos), "palavras": resto,
            "compras": "compr" in limpo, "estoque": "estoque" in limpo, "cadastro": "insumo" in limpo}


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
            '"saída de 3 quilos de tomate", "adicione 2 quilos de tomate no estoque", '
            '"exclua a compra de tomate", "adicione picanha nos insumos" ou "abrir compras".')


def _data_br(data):
    return f"{data[8:10]}/{data[5:7]}" if data and len(data) >= 10 else data


def _nome_falado(texto, palavras):
    """O nome como foi falado/escrito (com acento), só com as palavras que sobraram do comando."""
    restantes = set(palavras) - IGNORAR
    nome = " ".join(p for p in re.findall(r"[^\W\d_]+", texto) if sem_acento(p) in restantes)
    return nome[:1].upper() + nome[1:]


def _resolver(pedido):
    """Excluir/adicionar viram a ação de verdade conforme "compra", "estoque" e a quantidade da frase."""
    tipo, qtd = pedido["tipo"], pedido["quantidade"]
    exato = bool(pedido["exatos"]) and len(pedido["exatos"]) == 1 and \
        set(_raiz(p) for p in pedido["palavras"] if p not in IGNORAR and not p.isdigit()) == \
        {_raiz(p) for p in _palavras(pedido["exatos"][0]["nome"]) if p not in IGNORAR}
    if tipo == "excluir":
        if pedido["compras"]:
            return "excluir_compra"
        return "saida" if qtd else "desativar"
    if tipo == "adicionar":
        if exato and pedido["cadastro"] and not qtd:
            return "ja_existe"
        if not pedido["insumos"] or (not exato and (not qtd or pedido["cadastro"])):
            return "novo_insumo"
        if pedido["compras"]:
            return "compra"
        return "entrada" if qtd else "pedir_quantidade"
    return tipo


@bp.route("/voz/entender", methods=["POST"])
def entender():
    from contagem import agrupar_por_categoria, lista_categorias, unidade_padrao
    texto = (request.get_json(silent=True) or {}).get("texto", "").strip()[:300]
    if not texto:
        return jsonify(tipo="erro", resposta="Não ouvi nada. " + EXEMPLOS)
    conn = get_connection()
    insumos = conn.execute("SELECT * FROM insumos WHERE ativo = 1").fetchall()
    pedido = interpretar(texto, insumos)
    tipo = _resolver(pedido)

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

    if tipo == "novo_insumo":
        nome = _nome_falado(texto, pedido["palavras"])
        if not nome:
            conn.close()
            return jsonify(tipo="erro", resposta='Qual insumo? Ex.: "adicione picanha nos insumos".')
        todos = conn.execute("SELECT * FROM insumos").fetchall()
        conn.close()
        parecido = pedido["insumos"][0] if pedido["insumos"] else None
        categorias = lista_categorias(agrupar_por_categoria(todos))
        categoria = parecido["categoria"] if parecido else categorias[0]
        aviso = f' Já existe parecido: {parecido["nome"]}. Se for ele, cancele e fale o nome completo.' if parecido else ""
        return jsonify(tipo="novo_insumo", nome=nome, categorias=categorias, categoria=categoria,
                       unidade=pedido["unidade"] or (parecido["unidade"] if parecido else unidade_padrao(categoria)),
                       quantidade=pedido["quantidade"],
                       resposta=f'"{nome}" não está nos insumos. Cadastrar?' + aviso)

    if not pedido["insumos"]:
        conn.close()
        return jsonify(tipo="erro", resposta=f'Não achei nenhum insumo em "{texto}". Fale o nome como está na aba Insumos.')

    if tipo in (None, "consulta"):
        conn.close()
        respostas = [_texto_estoque(i) for i in pedido["exatos"]]
        return jsonify(tipo="consulta", resposta=" ".join(respostas))

    # O que bate exatamente com o falado vem primeiro; os outros ficam de opção no seletor
    insumo = pedido["exatos"][0]
    lista = [insumo] + [i for i in pedido["insumos"] if i["id"] != insumo["id"]]
    opcoes = [{"id": i["id"], "nome": i["nome"], "unidade": i["unidade"]} for i in lista[:6]]
    quantidade = pedido["quantidade"]

    if tipo == "excluir_compra":
        compras = conn.execute("""
            SELECT * FROM compras WHERE insumo_id = ? ORDER BY data DESC, id DESC LIMIT 30
        """, (insumo["id"],)).fetchall()
        conn.close()
        if not compras:
            return jsonify(tipo="erro", resposta=f"Não achei compra de {insumo['nome']} para excluir.")
        compra = next((c for c in compras if quantidade and abs(c["quantidade"] - quantidade) < 1e-9), compras[0])
        valor = f" (R$ {compra['valor_total']:.2f})".replace(".", ",") if compra["valor_total"] else ""
        return jsonify(tipo="excluir_compra", compra_id=compra["id"], resposta=(
            f"Excluir a compra de {formatar_quantidade(compra['quantidade'])} {compra['unidade']} de "
            f"{insumo['nome']} do dia {_data_br(compra['data'])}{valor}?"))

    if tipo == "desativar":
        conn.close()
        return jsonify(tipo="desativar", insumo_id=insumo["id"], opcoes=opcoes, resposta=(
            f"Tirar {insumo['nome']} da lista de insumos? Ele some do estoque e da contagem. "
            "Para voltar, abra a ficha do insumo na aba Insumos e marque Ativo."))

    if tipo == "ja_existe":
        conn.close()
        return jsonify(tipo="erro", resposta=f"{insumo['nome']} já está nos insumos. " + _texto_estoque(insumo))

    if tipo == "pedir_quantidade":
        conn.close()
        return jsonify(tipo="erro", resposta=(
            f"Quanto de {insumo['nome']}? Ex.: \"adicione 2 quilos de {insumo['nome'].lower()} no estoque\" "
            f"ou \"adicione 2 quilos de {insumo['nome'].lower()} nas compras\"."))

    unidade = pedido["unidade"] or _unidade_destino(conn, insumo, tipo)
    conn.close()
    if tipo == "desperdicio":
        url = url_for("desperdicio.desperdicio", insumo_id=insumo["id"], unidade=unidade,
                      quantidade=formatar_quantidade(quantidade) if quantidade else "")
        return jsonify(tipo="desperdicio", url=url, opcoes=opcoes, insumo_id=insumo["id"], quantidade=quantidade,
                       unidade=unidade,
                       resposta="O desperdício precisa de foto. Vou abrir o formulário já preenchido.")
    if not quantidade:
        return jsonify(tipo="erro", resposta=f"Quanto de {insumo['nome']}? Fale a quantidade, ex.: \"2 quilos\".")
    acao = {"compra": "Lançar compra", "saida": "Tirar do estoque (saída)", "entrada": "Somar no estoque (ajuste)"}[tipo]
    return jsonify(tipo=tipo, insumo_id=insumo["id"], quantidade=quantidade, unidade=unidade, valor=pedido["valor"],
                   opcoes=opcoes, resposta=f"{acao}?")


def _confirmar_cadastro(dados):
    from importador import chave_nome
    nome = " ".join((dados.get("nome") or "").split())[:80]
    categoria = (dados.get("categoria") or "").strip()[:60]
    unidade = (dados.get("unidade") or "").strip()[:20] or "un"
    if not nome or not categoria:
        return jsonify(ok=False, resposta="Preencha o nome e a categoria.")
    conn = get_connection()
    existente = next((r for r in conn.execute("SELECT * FROM insumos")
                      if chave_nome(r["nome"]) == chave_nome(nome)), None)
    if existente:
        if not existente["ativo"]:
            conn.execute("UPDATE insumos SET ativo = 1 WHERE id = ?", (existente["id"],))
            conn.commit()
            conn.close()
            return jsonify(ok=True, resposta=f"✅ {existente['nome']} já existia e voltou para a lista de insumos.")
        conn.close()
        return jsonify(ok=False, resposta=f"{existente['nome']} já está nos insumos.")
    conn.execute("INSERT INTO insumos (nome, categoria, unidade) VALUES (?, ?, ?)", (nome, categoria, unidade))
    conn.commit()
    conn.close()
    return jsonify(ok=True, resposta=(f"✅ {nome} cadastrado em {categoria} ({unidade}). "
                                      f"Para lançar, diga: \"comprei 2 {unidade} de {nome.lower()}\"."))


def _confirmar_exclusao_compra(dados):
    from compras import apagar_compra
    try:
        compra_id = int(dados.get("compra_id"))
    except (TypeError, ValueError):
        return jsonify(ok=False, resposta="Compra inválida.")
    conn = get_connection()
    compra = conn.execute("""
        SELECT c.*, i.nome FROM compras c JOIN insumos i ON i.id = c.insumo_id WHERE c.id = ?
    """, (compra_id,)).fetchone()
    if compra is None:
        conn.close()
        return jsonify(ok=False, resposta="Essa compra já não existe.")
    apagar_compra(conn, compra_id)
    conn.commit()
    insumo = conn.execute("SELECT * FROM insumos WHERE id = ?", (compra["insumo_id"],)).fetchone()
    conn.close()
    return jsonify(ok=True, resposta=(
        f"✅ Compra excluída: {formatar_quantidade(compra['quantidade'])} {compra['unidade']} de {compra['nome']} "
        f"do dia {_data_br(compra['data'])}. " + _texto_estoque(insumo)))


@bp.route("/voz/confirmar", methods=["POST"])
def confirmar():
    from insumo_cadastro import carregar_conversoes
    from unidades import converter
    dados = request.get_json(silent=True) or {}
    tipo = dados.get("tipo")
    if tipo == "novo_insumo":
        return _confirmar_cadastro(dados)
    if tipo == "excluir_compra":
        return _confirmar_exclusao_compra(dados)
    if tipo == "desativar":
        try:
            insumo_id = int(dados.get("insumo_id"))
        except (TypeError, ValueError):
            return jsonify(ok=False, resposta="Insumo inválido.")
        conn = get_connection()
        insumo = conn.execute("SELECT * FROM insumos WHERE id = ?", (insumo_id,)).fetchone()
        if insumo is None:
            conn.close()
            return jsonify(ok=False, resposta="Insumo não encontrado.")
        conn.execute("UPDATE insumos SET ativo = 0 WHERE id = ?", (insumo_id,))
        conn.commit()
        conn.close()
        return jsonify(ok=True, resposta=f"✅ {insumo['nome']} saiu da lista de insumos. "
                                         "Para voltar, abra a ficha dele na aba Insumos e marque Ativo.")
    if tipo not in ("compra", "saida", "entrada"):
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
        mov, motivo = ("saida", "lançado por voz") if tipo == "saida" else ("ajuste_mais", "ajuste por voz")
        conn.execute("""
            INSERT INTO movimentacoes (data, insumo_id, tipo, quantidade, unidade, motivo, local_origem,
                                       local_destino, responsavel, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, ?)
        """, (hoje, insumo["id"], mov, quantidade, unidade, motivo, insumo["local"] or "", session.get("nome", ""),
              agora))
        feito = "Saída lançada" if tipo == "saida" else "Somado no estoque"
    conn.commit()
    conn.close()
    return jsonify(ok=True, resposta=f"✅ {feito}: {formatar_quantidade(quantidade)} {unidade} de {insumo['nome']}. "
                                     + _texto_estoque(insumo))
