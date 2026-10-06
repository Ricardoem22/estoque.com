# unidades.py
# Conversão de quantidades entre unidades.
#
# Conversões fixas (peso e volume) valem para todos os insumos. As outras ("1 saco = 5 kg",
# "1 peça = 4,5 kg") são cadastradas em cada insumo, na tabela insumo_conversoes.
# Nada é convertido sem regra: litro não vira quilo, caixa não vira unidade.

# Fator para converter 1 unidade em gramas ou mililitros
_PESO = {"mg": 0.001, "g": 1, "kg": 1000}
_VOLUME = {"ml": 1, "L": 1000, "lt": 1000}

# Medidas oferecidas nos formulários, além das personalizadas de cada insumo
UNIDADES_COMUNS = ["kg", "g", "mg", "L", "ml", "un", "pct", "cx", "dz", "bandeja", "fardo", "garrafa", "lata",
                   "saco", "peça", "fd", "gf", "mç", "lt"]


def converter_fixo(quantidade, de, para):
    if de == para:
        return quantidade
    for grupo in (_PESO, _VOLUME):
        if de in grupo and para in grupo:
            return quantidade * grupo[de] / grupo[para]
    return None


def converter(quantidade, de, para, conversoes=()):
    """Converte quantidade de uma unidade para outra; None quando não há regra.
    conversoes: [(unidade, fator, unidade_base)] do insumo, ex.: ("saco", 5, "kg")."""
    if quantidade is None:
        return None
    direto = converter_fixo(quantidade, de, para)
    if direto is not None:
        return direto
    for unidade, fator, base in conversoes:
        if not fator:
            continue
        if de == unidade:
            resultado = converter_fixo(quantidade * fator, base, para)
            if resultado is not None:
                return resultado
        if para == unidade:
            na_base = converter_fixo(quantidade, de, base)
            if na_base is not None:
                return na_base / fator
    # Duas medidas personalizadas (ex.: fardo → saco) passando pela unidade base
    for unidade, fator, base in conversoes:
        if de == unidade and fator:
            for outra, fator2, base2 in conversoes:
                if para == outra and fator2:
                    na_base = converter_fixo(quantidade * fator, base, base2)
                    if na_base is not None:
                        return na_base / fator2
    return None


def unidades_do_insumo(unidade_base, conversoes=()):
    """Unidade do estoque primeiro, depois as personalizadas, depois as comuns."""
    lista = [unidade_base] + [c[0] for c in conversoes]
    return list(dict.fromkeys(lista + UNIDADES_COMUNS))
