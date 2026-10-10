# notas.py
# Lê notas fiscais de compra: XML da NF-e (o mais confiável), PDF da DANFE
# (quando o PDF tem texto) e planilhas Excel/CSV. Devolve fornecedor, data,
# número/chave e os itens com quantidade, unidade, valor e, quando a nota
# traz, NCM, código de barras (EAN) e CFOP.
import re
import xml.etree.ElementTree as ET

from importador import chave_nome, ler_csv, ler_xlsx, normalizar_unidade, parse_numero, sem_acento, separar_quantidade
from unidades import converter

EXTENSOES_NOTA = {"xml", "pdf", "xlsx", "xlsm", "csv"}
PALAVRAS_IGNORADAS = {"de", "da", "do", "das", "dos", "e", "com", "em", "a", "o", "kg", "un", "cx", "pct", "g", "l"}


def nota_vazia():
    # origem: de onde veio a nota; valor_nota: total da nota (só no XML), para conferir com a soma dos itens
    return {"fornecedor": "", "cnpj": "", "data": "", "numero": "", "chave": "", "itens": [],
            "origem": "", "valor_nota": None}


def so_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def item_nota(nome, quantidade, unidade_nota, valor_total, codigo="", ncm="", ean="", cfop="", unitario=None,
              valor_produto=None, acrescimos=0.0, desconto=0.0):
    # Sem o unitário da nota, ele sai do total (já com desconto), que é o que foi pago de fato
    if unitario is None and valor_total is not None and quantidade:
        unitario = round(valor_total / quantidade, 4)
    ean = so_digitos(ean)
    ncm = so_digitos(ncm)
    return {
        "nome": nome, "codigo": codigo, "quantidade": quantidade, "unidade_nota": unidade_nota,
        "valor_total": valor_total, "valor_unitario": unitario,
        "ncm": ncm if len(ncm) == 8 else "",
        "ean": ean if len(ean) in (8, 12, 13, 14) else "",  # "SEM GTIN" e vazios ficam de fora
        "cfop": so_digitos(cfop)[:4],
        # Composição do valor pago (só o XML traz impostos e frete por item)
        "valor_produto": valor_produto, "acrescimos": acrescimos, "desconto": desconto,
    }


def ler_nota(nome_arquivo, dados):
    ext = nome_arquivo.rsplit(".", 1)[-1].lower() if "." in nome_arquivo else ""
    if ext == "xml" or dados.lstrip()[:1] == b"<":
        return ler_xml(dados)
    if ext == "pdf":
        return ler_danfe(dados)
    if ext in ("xlsx", "xlsm"):
        return ler_planilha(ler_xlsx(dados))
    if ext == "csv":
        return ler_planilha(ler_csv(dados))
    if ext == "xls":
        raise ValueError("Arquivos .xls antigos não são suportados. Abra no Excel e salve como .xlsx.")
    raise ValueError("Formato não suportado. Use o XML da nota (o melhor), o PDF da DANFE ou Excel/CSV.")


# ---------- XML da NF-e ----------

def ler_xml(dados):
    try:
        raiz = ET.fromstring(dados)
    except ET.ParseError:
        raise ValueError("Esse XML está com defeito. Baixe de novo o XML da nota.")

    def achar(no, nome):
        # Ignora o namespace do portal fiscal
        for filho in no.iter():
            if filho.tag.rsplit("}", 1)[-1] == nome:
                return filho
        return None

    def texto(no, nome):
        alvo = achar(no, nome) if no is not None else None
        return (alvo.text or "").strip() if alvo is not None else ""

    inf = achar(raiz, "infNFe")
    if inf is None:
        raise ValueError("Esse XML não parece ser de uma NF-e.")
    nota = nota_vazia()
    nota["chave"] = re.sub(r"\D", "", inf.get("Id", ""))
    nota["numero"] = texto(achar(inf, "ide"), "nNF")
    data = texto(achar(inf, "ide"), "dhEmi") or texto(achar(inf, "ide"), "dEmi")
    nota["data"] = data[:10]
    emitente = achar(inf, "emit")
    nota["fornecedor"] = texto(emitente, "xFant") or texto(emitente, "xNome")
    nota["cnpj"] = texto(emitente, "CNPJ") or texto(emitente, "CPF")
    nota["origem"] = "xml"
    nota["valor_nota"] = parse_numero(texto(achar(inf, "ICMSTot"), "vNF").replace(".", ","))

    def numero(no, nome):
        return parse_numero(texto(no, nome).replace(".", ",")) or 0.0

    for det in inf.iter():
        if det.tag.rsplit("}", 1)[-1] != "det":
            continue
        prod = achar(det, "prod")
        imposto = achar(det, "imposto")
        quantidade = parse_numero(texto(prod, "qCom").replace(".", ",")) if prod is not None else None
        valor = parse_numero(texto(prod, "vProd").replace(".", ",")) if prod is not None else None
        if not quantidade:
            continue
        # Valor pago = produto − desconto + frete, seguro e outras despesas rateados no item
        # + impostos cobrados por fora (IPI, ICMS-ST, FCP-ST, imposto de importação)
        desconto = numero(prod, "vDesc")
        acrescimos = numero(prod, "vFrete") + numero(prod, "vSeg") + numero(prod, "vOutro")
        if imposto is not None:
            acrescimos += (numero(imposto, "vIPI") + numero(imposto, "vICMSST") + numero(imposto, "vFCPST")
                           + numero(imposto, "vII"))
        pago = round(valor - desconto + acrescimos, 2) if valor is not None else None
        # Sem desconto nem acréscimo, o unitário é o da própria nota; senão, é recalculado pelo valor pago
        unitario = None
        if not desconto and not acrescimos:
            unitario = parse_numero(texto(prod, "vUnCom").replace(".", ","))
        nota["itens"].append(item_nota(
            texto(prod, "xProd"), quantidade, texto(prod, "uCom"), pago,
            codigo=texto(prod, "cProd"), ncm=texto(prod, "NCM"), ean=texto(prod, "cEAN"), cfop=texto(prod, "CFOP"),
            unitario=round(unitario, 4) if unitario is not None else None,
            valor_produto=valor, acrescimos=round(acrescimos, 2), desconto=round(desconto, 2),
        ))
    return nota


# ---------- PDF da DANFE ----------

# Linha de item: ... descrição  NCM(8)  CST(3-4)  CFOP(4)  UN  QTD  V.UNIT  V.TOTAL ...
# Algumas DANFEs separam a origem do CST ("0 40"), deixam o fim da descrição passar por cima do NCM
# ("COD 70133700 2010") ou colam o CFOP na unidade ("5102CX24").
LINHA_DANFE = re.compile(
    r"^(?:(?P<codigo>\S+)\s+)?(?P<nome>.+?)\s+(?P<ncm>\d{8})(?:\s+(?P<resto>\S+?))??\s+(?P<cst>\d\s?\d{2,3})\s+"
    r"(?P<cfop>\d{4})\s*"
    r"(?P<un>[A-Za-zÇç]{1,6}\d{0,3})\s+(?P<qtd>[\d.,]+)\s+(?P<unit>[\d.,]+)\s+(?P<total>[\d.,]+)"
)


def _linhas_por_posicao(dados):
    """Linhas do PDF montadas pela posição das palavras. Muitas DANFEs (ex.: Koch) saem do pypdf coluna por coluna
    (todos os códigos, depois todas as descrições...); juntando as palavras da mesma altura a linha do item volta."""
    try:
        import pdfplumber
    except ImportError:
        return []
    import io
    linhas = []
    try:
        with pdfplumber.open(io.BytesIO(dados)) as pdf:
            for pagina in pdf.pages:
                atual, topo = [], None
                for p in sorted(pagina.extract_words(x_tolerance=1.5, use_text_flow=True),
                                  key=lambda p: (round(p["top"]), p["x0"])):
                    if topo is not None and abs(p["top"] - topo) > 2:
                        linhas.append(" ".join(w["text"] for w in sorted(atual, key=lambda w: w["x0"])))
                        atual = []
                    if not atual:
                        topo = p["top"]
                    atual.append(p)
                if atual:
                    linhas.append(" ".join(w["text"] for w in sorted(atual, key=lambda w: w["x0"])))
    except Exception:
        return []
    return linhas


def _itens_danfe(linhas):
    itens = []
    for linha in linhas:
        m = LINHA_DANFE.match(re.sub(r"\s+", " ", linha.strip()))
        if not m:
            continue
        quantidade = parse_numero(m.group("qtd"))
        if not quantidade:
            continue
        nome = m.group("nome").strip() + (" " + m.group("resto") if m.group("resto") else "")
        itens.append(item_nota(
            nome, quantidade, m.group("un"), parse_numero(m.group("total")),
            codigo=m.group("codigo") or "", ncm=m.group("ncm"), cfop=m.group("cfop"),
        ))
    return itens


def ler_danfe(dados):
    from pypdf import PdfReader
    import io
    leitor = PdfReader(io.BytesIO(dados))
    texto = "\n".join((pagina.extract_text() or "") for pagina in leitor.pages)
    if not texto.strip():
        raise ValueError("Esse PDF não tem texto (parece uma foto da nota). Use o XML da nota ou digite os itens.")
    nota = nota_vazia()
    chave = re.search(r"((?:\d{4}\s?){10}\d{4})", texto)
    if chave:
        nota["chave"] = re.sub(r"\D", "", chave.group(1))
    data = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
    if data:
        nota["data"] = f"{data.group(3)}-{data.group(2)}-{data.group(1)}"
    numero = re.search(r"N[º°o.]\s*:?\s*([\d.]{3,})", texto)
    if numero:
        nota["numero"] = numero.group(1).replace(".", "").lstrip("0")
    # Pelo texto corrido e pela posição das palavras; fica a leitura que achou mais itens
    nota["itens"] = max(_itens_danfe(texto.splitlines()), _itens_danfe(_linhas_por_posicao(dados)), key=len)
    nota["origem"] = "pdf"
    if not nota["itens"]:
        import importlib.util
        if importlib.util.find_spec("pdfplumber") is None:
            raise ValueError("Falta instalar o leitor de notas no site. No Bash do PythonAnywhere rode: cd ~/estoque.com "
                             "e depois pip install --user -r requirements.txt; em seguida clique em Reload na aba Web.")
        raise ValueError("Não encontrei os itens nesse PDF. Use o XML da nota (o fornecedor manda por e-mail "
                         "ou dá para baixar no site da Sefaz com a chave de acesso).")
    return nota


# ---------- Foto da nota (texto lido no celular) e QR code ----------

_NUM = r"(?:\d[\d.,/]*\d|\d)(?![\d.,/])"
_UN = r"KG|KGS|UN|UND|UNID|CX|PC|PCT|FD|LT|L|G|DZ|BD|SC|GL|MC|PT|BJ|SAC"
# Unidade, quantidade, unitário e total em sequência: "KG 2,000 32,90 65,80" (DANFE, com os impostos depois)
# ou "2,000 KG X 32,90 65,80" (cupom NFC-e). Sujeira da leitura entre os números ("[", "]", "|") é ignorada.
_SUJ = r"[\s\[\]|()fjJIl=>—:;-]*"
LINHA_FOTO = [
    re.compile(rf"(?P<qtd>{_NUM})\s*(?P<un>{_UN})\.?\s*[xX*]\s*(?P<unit>{_NUM}){_SUJ}(?P<total>{_NUM})", re.I),
    re.compile(rf"(?<![A-Za-z])(?P<un>{_UN})[A-Z\dIl\]|]{{0,2}}{_SUJ}(?P<qtd>{_NUM}){_SUJ}(?P<unit>{_NUM}){_SUJ}(?P<total>{_NUM})", re.I),
]


def _leituras(texto):
    """Valores possíveis de um número lido da foto: com vírgula vale como está; sem vírgula a leitura pode ter
    perdido a vírgula ("650" pode ser 6,50)."""
    texto = texto.strip(".,/").replace("/", ",")
    digitos = texto.replace(".", "").replace(",", "")
    if len(digitos) >= 4 and len(digitos) % 2 == 0 and digitos[:len(digitos) // 2] == digitos[len(digitos) // 2:]:
        texto = digitos[:len(digitos) // 2]  # duas colunas iguais grudadas ("659659" = 6,59 e 6,59)
    if "," in texto:
        valor = parse_numero(texto)
        return [(valor, 0)] if valor else []
    digitos = texto.replace(".", "")
    if not digitos.isdigit():
        return []
    # Valor sem vírgula com 3 dígitos ou mais quase sempre perdeu a vírgula na leitura
    return [(int(digitos) / 10 ** k, 1 if k or len(digitos) >= 3 else 0) for k in range(5) if int(digitos)]


def _confere(qtd, unit, total):
    """Quantidade, unitário e total que fecham a conta (com 3% de folga), preferindo os números como foram lidos."""
    melhor = None
    for q, cq in _leituras(qtd):
        for u, cu in _leituras(unit):
            for t, ct in _leituras(total):
                if 0.1 <= u <= 5000 and 0.05 <= t <= 50000 and q <= 2000 and abs(q * u - t) <= max(0.03 * t, 0.02):
                    custo = cq + cu + ct
                    # Total lido sem vírgula: vale a conta, que tem os centavos certos
                    t = round(q * u, 2) if ct else t
                    if melhor is None or (custo, t) < melhor[:2]:
                        melhor = (custo, t, q, u)
    return (melhor[2], melhor[3], melhor[1]) if melhor else None


def _itens_foto(linhas):
    """Itens do texto que o celular leu da foto. Só fica a linha em que quantidade x unitário dá o total,
    para não lançar lixo de leitura."""
    itens = []
    for linha in linhas:
        linha = re.sub(r"\s+", " ", linha).strip()
        for regra in LINHA_FOTO:
            achou = None
            for m in regra.finditer(linha):
                valores = _confere(m.group("qtd"), m.group("unit"), m.group("total"))
                if valores:
                    achou = (m, valores)
                    break
            if not achou:
                continue
            m, (qtd, unit, total) = achou
            nome = linha[:m.start()]
            # Tira da frente o nº do item e o código; do fim, NCM/CST/CFOP e a sujeira das colunas
            nome = re.sub(r"[\[\]|{}“”\"—_]", " ", nome)
            nome = re.sub(r"^\W*(?:\S*\d\S*\s+)+", "", nome + " ")
            nome = re.split(r"\s\S*\d{5,}", " " + nome.strip())[0]
            nome = re.sub(r"\s+\S{1,2}$", "", nome).strip(" -.,")
            nome = re.sub(r"^(?:(?:\S{1,2}|\S*[^\w\s]\S*)\s+)+", "", nome).strip(" =-")
            if len(re.sub(r"[^A-Za-z]", "", nome)) < 3:
                continue
            un = m.group("un").upper()
            if un == "G" and unit > 1:  # "KG" com o K perdido: ninguém paga mais de R$ 1 o grama
                un = "KG"
            itens.append(item_nota(nome, qtd, un, round(total, 2), unitario=unit))
            break
    return itens


def ler_texto_nota(texto):
    """Nota a partir do texto lido de uma foto: os itens pelas regras da DANFE e do cupom, mais chave e data."""
    nota = nota_vazia()
    linhas = [l for l in (texto or "").splitlines() if l.strip()]
    chave = (re.search(r"(?<!\d)((?:\d{4} ){10}\d{4})(?!\d)", texto or "")
             or re.search(r"(?<!\d)(\d{44})(?!\d)", texto or ""))
    if chave:
        nota["chave"] = so_digitos(chave.group(1))
    data = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto or "")
    if data:
        nota["data"] = f"{data.group(3)}-{data.group(2)}-{data.group(1)}"
    nota["itens"] = max(_itens_danfe(linhas), _itens_foto(linhas), key=len)
    nota["origem"] = "foto"
    return nota


def chave_do_codigo(texto):
    """Chave de acesso (44 dígitos) do QR code da NFC-e ("...?p=4224...|2|1|...") ou do código de barras da DANFE."""
    m = re.search(r"(?<!\d)(\d{44})(?!\d)", so_digitos_mantendo_separadores(texto))
    return m.group(1) if m else ""


def so_digitos_mantendo_separadores(texto):
    # Espaços entre os blocos da chave somem; outros separadores ficam para não juntar números diferentes
    return re.sub(r"(?<=\d)\s+(?=\d)", "", texto or "")


def dados_da_chave(chave):
    """O que a chave de acesso diz sozinha: mês da emissão, CNPJ do emitente, modelo, série e número."""
    if len(chave) != 44:
        return None
    return {
        "chave": chave, "mes": f"20{chave[2:4]}-{chave[4:6]}", "cnpj": chave[6:20],
        "modelo": "NFC-e (cupom)" if chave[20:22] == "65" else "NF-e",
        "serie": chave[22:25].lstrip("0") or "0", "numero": chave[25:34].lstrip("0") or "0",
    }


# ---------- Planilha ----------

COLUNAS = {
    "nome": ["descricao", "produto", "item", "mercadoria", "nome", "xprod", "insumo"],
    "quantidade": ["quantidade", "qtd", "qtde", "quant", "qcom"],
    "unidade": ["unidade", "un", "und", "unid", "ucom", "medida"],
    "valor_total": ["total", "vprod", "subtotal"],
    "valor_unitario": ["unitario", "vuncom", "unit", "preco"],
    "ncm": ["ncm"],
    # EAN antes de código: "Cód. barras" é EAN, não código do fornecedor
    "ean": ["ean", "gtin", "barras", "cean"],
    "codigo": ["codigo", "cod", "cprod", "sku"],
}


def ler_planilha(linhas):
    cabecalho, mapa = None, {}
    for i, linha in enumerate(linhas[:30]):
        candidato = {}
        for col, celula in enumerate(linha):
            palavras = re.findall(r"[a-z]+", sem_acento(celula))
            for campo, chaves in COLUNAS.items():
                if campo not in candidato and any(p in chaves for p in palavras):
                    candidato[campo] = col
                    break
            # "Valor" sozinho conta como total
            if "valor_total" not in candidato and palavras == ["valor"]:
                candidato["valor_total"] = col
        if "nome" in candidato and "quantidade" in candidato:
            cabecalho, mapa = i, candidato
            break
    if cabecalho is None:
        raise ValueError("Não achei as colunas da planilha. Ela precisa ter pelo menos Produto e Quantidade "
                         "(e de preferência Valor total).")
    nota = nota_vazia()
    nota["origem"] = "planilha"

    def celula(linha, campo):
        col = mapa.get(campo)
        return linha[col] if col is not None and col < len(linha) else ""

    for linha in linhas[cabecalho + 1:]:
        nome = str(celula(linha, "nome")).strip()
        quantidade = parse_numero(celula(linha, "quantidade"))
        if not nome or not quantidade:
            continue
        total = parse_numero(str(celula(linha, "valor_total")).replace("R$", ""))
        if total is None:
            unitario = parse_numero(str(celula(linha, "valor_unitario")).replace("R$", ""))
            total = round(unitario * quantidade, 2) if unitario is not None else None
        nota["itens"].append(item_nota(
            nome, quantidade,
            str(celula(linha, "unidade")).strip() or separar_quantidade(celula(linha, "quantidade"))[1] or "", total,
            codigo=str(celula(linha, "codigo")).strip(), ncm=str(celula(linha, "ncm")),
            ean=str(celula(linha, "ean")),
        ))
    return nota


# ---------- Ligar itens da nota aos insumos ----------

def palavras(nome):
    return {p for p in chave_nome(nome).split() if p not in PALAVRAS_IGNORADAS and not p.isdigit()}


def achar_insumo(nome_nota, insumos, apelidos, unidade=None, conversoes=None):
    """Insumo do item da nota: apelido salvo antes, nome igual ou todas as palavras do insumo no item.
    Com a unidade do item, a busca por palavras só aceita insumo cuja medida converte dela
    (ex.: "BEBIDA MISTA ABACAXI" em cx não cai no insumo Abacaxi em kg)."""
    chave = chave_nome(nome_nota)
    if chave in apelidos:
        return apelidos[chave]
    por_nome = {chave_nome(i["nome"]): i["id"] for i in insumos}
    if chave in por_nome:
        return por_nome[chave]
    do_item = palavras(nome_nota)
    melhor, tamanho = None, 0
    for insumo in insumos:
        do_insumo = palavras(insumo["nome"])
        if do_insumo and do_insumo <= do_item and len(do_insumo) > tamanho:
            if unidade and converter(1, unidade, insumo["unidade"], (conversoes or {}).get(insumo["id"], ())) is None:
                continue
            melhor, tamanho = insumo["id"], len(do_insumo)
    return melhor


def unidade_do_item(item):
    if not item["unidade_nota"]:
        return None
    # "KG1" / "UN1" de alguns supermercados: o número no fim não muda a unidade
    return normalizar_unidade(item["unidade_nota"]) or normalizar_unidade(re.sub(r"\d+$", "", item["unidade_nota"]))
