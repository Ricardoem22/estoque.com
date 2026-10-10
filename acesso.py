# acesso.py
# Abas do menu e quais delas cada funcionário pode abrir.
# A gerência vê tudo; para a equipe, a gerência marca as abas na tela Funcionários.
from flask import redirect, render_template, request, session, url_for

# (chave, ícone, nome, página da aba)
ABAS = [
    ("estoque", "🏪", "Estoque", "relatorio.estoque"),
    ("contagens", "📋", "Contagem", "contagem.contagens"),
    ("insumos", "🧾", "Insumos", "contagem.insumos"),
    ("compras", "🛒", "Compras", "compras.compras"),
    ("desperdicio", "🗑️", "Desperdício", "desperdicio.desperdicio"),
    ("movimentos", "🔄", "Movimentações", "movimentos.movimentacoes"),
    ("refeicao", "🍽️", "Refeição", "refeicao.refeicao"),
    ("relatorio", "📊", "Relatório", "relatorio.relatorio"),
    ("precos", "💲", "Preços", "precos.melhor_preco"),
    ("mural", "💬", "Mural", "mural.mural"),
]
CHAVES = [a[0] for a in ABAS]
NOMES = {a[0]: a[2] for a in ABAS}

# O que cada comando de voz faz conta como a aba correspondente
ABA_DA_VOZ = {
    "consulta": "estoque", "compra": "compras", "excluir_compra": "compras", "saida": "movimentos",
    "entrada": "movimentos", "novo_insumo": "insumos", "desativar": "insumos", "desperdicio": "desperdicio",
}


def aba_do_endpoint(ep):
    ep = ep or ""
    if "insumo" in ep or ep == "contagem.confirmar_importacao":
        return "insumos"
    if ep.startswith("contagem."):
        return "contagens"
    if ep.startswith("movimentos."):
        return "movimentos"
    if ep.startswith("refeicao."):
        return "refeicao"
    if ep.startswith("compras."):
        return "compras"
    if ep.startswith("desperdicio.") or ep.startswith("gerencia"):
        return "desperdicio"
    if ep in ("relatorio.estoque", "relatorio.estoque_csv"):
        return "estoque"
    if ep.startswith("relatorio."):
        return "relatorio"
    if ep.startswith("precos."):
        return "precos"
    if ep.startswith("mural."):
        return "mural"
    if ep.startswith("funcionarios."):
        return "funcionarios"
    return ""


def ler_abas(texto):
    """Coluna funcionarios.abas: vazia = todas; senão as chaves separadas por vírgula."""
    escolhidas = [a for a in (texto or "").split(",") if a in CHAVES]
    return escolhidas or None


def gravar_abas(lista):
    escolhidas = [a for a in CHAVES if a in lista]
    return "" if len(escolhidas) == len(CHAVES) else ",".join(escolhidas)


def pode_ver(aba):
    if session.get("gerente") or aba not in CHAVES:
        return True
    permitidas = session.get("abas")
    return not permitidas or aba in permitidas


def abas_do_menu():
    return [{"chave": c, "icone": i, "nome": n, "url": url_for(e)} for c, i, n, e in ABAS if pode_ver(c)]


def primeira_aba():
    abas = abas_do_menu()
    return abas[0]["url"] if abas else url_for("funcionarios.trocar_senha")


def conferir_aba():
    """Chamado a cada página, depois do login: bloqueia as abas que a gerência não liberou."""
    if request.endpoint == "gerencia":
        return None
    aba = aba_do_endpoint(request.endpoint)
    if pode_ver(aba):
        return None
    # Tela inicial (Estoque) fechada: vai direto para a primeira aba liberada
    if request.method == "GET" and request.endpoint == "relatorio.estoque":
        return redirect(primeira_aba())
    return render_template("sem_acesso.html", aba=NOMES.get(aba, aba)), 403
