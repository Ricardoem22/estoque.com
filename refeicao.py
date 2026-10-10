# refeicao.py
# Refeição da equipe: o funcionário lança tudo o que usou na refeição dos funcionários (vários itens de uma
# vez) e cada item vira uma movimentação "Refeição da equipe", que já desconta do estoque.
from datetime import datetime

from flask import Blueprint, redirect, render_template, request, session, url_for

import config
from contagem import formatar_quantidade, get_connection, parse_quantidade, unidade_digitada
from insumo_cadastro import carregar_conversoes, insumos_para_formulario, precos_dos_insumos, valor_em_reais
from movimentos import mes_selecionado
from unidades import UNIDADES_COMUNS, converter

bp = Blueprint("refeicao", __name__)

LINHAS_EM_BRANCO = 3


def ler_itens(form):
    """[(insumo_id, quantidade texto, unidade)] das linhas preenchidas do formulário."""
    itens = []
    for i in range(form.get("total", 0, type=int)):
        insumo_id = form.get(f"insumo_{i}", type=int)
        quantidade = form.get(f"qtd_{i}", "").strip()
        if insumo_id or quantidade:
            itens.append((insumo_id, quantidade, unidade_digitada(quantidade, form.get(f"un_{i}"))))
    return itens


@bp.route("/refeicao", methods=["GET", "POST"])
def refeicao():
    conn = get_connection()
    erro = None
    form = request.form
    itens = ler_itens(form) if request.method == "POST" else []
    if request.method == "POST":
        data = form.get("data", "")
        refeicao_nome = form.get("refeicao", "").strip()
        conversoes = carregar_conversoes(conn)
        gravar = []
        try:
            datetime.strptime(data, "%Y-%m-%d")
        except ValueError:
            erro = "Informe uma data válida."
        if not erro and not itens:
            erro = "Escolha pelo menos um item e a quantidade usada."
        for insumo_id, texto, unidade in itens if not erro else []:
            insumo = conn.execute("SELECT * FROM insumos WHERE id = ?", (insumo_id,)).fetchone() if insumo_id else None
            if insumo is None:
                erro = f"Escolha o item da linha com quantidade {texto}."
                break
            try:
                quantidade = parse_quantidade(texto)
            except ValueError:
                quantidade = None
            if not quantidade:
                erro = f"Informe quanto foi usado de {insumo['nome']}."
                break
            unidade = unidade or insumo["unidade"]
            if converter(1, unidade, insumo["unidade"], conversoes.get(insumo["id"], [])) is None:
                erro = (f"{unidade} não converte para {insumo['unidade']} ({insumo['nome']}). Use "
                        f"{insumo['unidade']} ou cadastre a medida na ficha do insumo.")
                break
            gravar.append((insumo, quantidade, unidade))
        if not erro:
            motivo = "Refeição da equipe" + (f": {refeicao_nome}" if refeicao_nome else "")
            agora = config.agora().strftime("%Y-%m-%d %H:%M:%S")
            for insumo, quantidade, unidade in gravar:
                conn.execute("""
                    INSERT INTO movimentacoes (data, insumo_id, tipo, quantidade, unidade, motivo, local_origem,
                                               local_destino, responsavel, criado_em)
                    VALUES (?, ?, 'refeicao', ?, ?, ?, ?, '', ?, ?)
                """, (data, insumo["id"], quantidade, unidade, motivo, insumo["local"] or "",
                      session.get("nome", ""), agora))
            conn.commit()
            conn.close()
            return redirect(url_for("refeicao.refeicao", mes=data[:7], salvo=len(gravar)))

    falado = request.args.get("falado", "").strip()[:500] if request.method == "GET" else ""
    entendidos, nao_entendi = [], []
    if falado:
        # Itens falados ("2 quilos de arroz e 1 de feijão"): preenchem as linhas para conferir antes de lançar
        from voz import itens_falados
        entendidos, nao_entendi = itens_falados(falado, conn.execute("SELECT * FROM insumos WHERE ativo = 1").fetchall())
        itens = [(i["insumo"]["id"], formatar_quantidade(i["quantidade"]), i["unidade"]) for i in entendidos]
    elif not itens:
        # Começa com os itens da última refeição (a equipe costuma repetir), quantidades em branco
        ultima = conn.execute("SELECT criado_em FROM movimentacoes WHERE tipo = 'refeicao' "
                              "ORDER BY criado_em DESC LIMIT 1").fetchone()
        if ultima:
            itens = [(r["insumo_id"], "", r["unidade"]) for r in conn.execute(
                "SELECT insumo_id, unidade FROM movimentacoes WHERE tipo = 'refeicao' AND criado_em = ? "
                "ORDER BY id", (ultima["criado_em"],))]
    itens = itens + [(None, "", "")] * LINHAS_EM_BRANCO

    mes = mes_selecionado()
    registros = conn.execute("""
        SELECT m.*, i.nome AS insumo_nome, i.unidade AS unidade_estoque FROM movimentacoes m JOIN insumos i ON i.id = m.insumo_id
        WHERE m.tipo = 'refeicao' AND substr(m.data, 1, 7) = ? ORDER BY m.data DESC, m.criado_em DESC, m.id
    """, (mes,)).fetchall()
    # Um lançamento = os itens gravados juntos (mesma data, hora e pessoa), com o valor em R$ de cada item
    conversoes = carregar_conversoes(conn)
    precos = precos_dos_insumos(conn, conversoes)
    lancamentos = []
    for r in registros:
        r = dict(r)
        r["valor"] = valor_em_reais(precos, conversoes, r["insumo_id"], r["quantidade"], r["unidade"], r["unidade_estoque"])
        chave = (r["data"], r["criado_em"], r["responsavel"], r["motivo"])
        if not lancamentos or lancamentos[-1]["chave"] != chave:
            lancamentos.append({"chave": chave, "data": r["data"], "responsavel": r["responsavel"],
                                "motivo": r["motivo"], "itens": [], "valor": 0.0, "sem_preco": 0})
        lancamentos[-1]["itens"].append(r)
        if r["valor"] is None:
            lancamentos[-1]["sem_preco"] += 1
        else:
            lancamentos[-1]["valor"] += r["valor"]
    total_mes = {"valor": round(sum(l["valor"] for l in lancamentos), 2),
                 "sem_preco": sum(l["sem_preco"] for l in lancamentos), "refeicoes": len(lancamentos)}
    grupos = insumos_para_formulario(conn)
    conn.close()
    return render_template(
        "refeicao.html", grupos=grupos, itens=itens, unidades=UNIDADES_COMUNS, erro=erro, form=form, mes=mes,
        lancamentos=lancamentos, total_mes=total_mes, salvo=request.args.get("salvo"), falado=falado, entendidos=entendidos,
        nao_entendi=nao_entendi,
        data_padrao=form.get("data") or config.hoje().isoformat(),
    )
