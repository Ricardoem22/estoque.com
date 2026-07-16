import json
import os
from datetime import datetime
from fpdf import FPDF
import matplotlib.pyplot as plt

ARQUIVO_ESTOQUE = "estoque.json"
ARQUIVO_HISTORICO = "historico_vendas.json"
ARQUIVO_RELATORIO = "relatorio.txt"
ARQUIVO_RELATORIO_PDF = "relatorio.pdf"
ARQUIVO_GRAFICO = "grafico_vendas.png"


# ===================== ESTOQUE =====================

def carregar_estoque():
    if os.path.exists(ARQUIVO_ESTOQUE):
        with open(ARQUIVO_ESTOQUE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def salvar_estoque(estoque):
    with open(ARQUIVO_ESTOQUE, "w", encoding="utf-8") as f:
        json.dump(estoque, f, indent=4, ensure_ascii=False)


def buscar_produto(estoque, nome_produto):
    nome_produto = nome_produto.strip().lower()
    for produto in estoque:
        if produto["nome"].lower() == nome_produto:
            return produto
    return None


def adicionar_produto(estoque, nome, quantidade, preco):
    produto_existente = buscar_produto(estoque, nome)
    if produto_existente:
        produto_existente["quantidade"] += quantidade
        produto_existente["preco"] = preco
        print(f"🔄 {nome} já existia. Quantidade atualizada para {produto_existente['quantidade']}.")
    else:
        estoque.append({"nome": nome.strip(), "quantidade": quantidade, "preco": preco})
        print(f"➕ {nome} adicionado ao estoque")


def listar_produtos(estoque):
    if not estoque:
        print("📦 Estoque vazio.")
        return
    print("\n===== PRODUTOS EM ESTOQUE =====")
    for produto in estoque:
        print(f"- {produto['nome']} | Qtd: {produto['quantidade']} | R$ {produto['preco']:.2f}")


def valor_total_estoque(estoque):
    total = sum(p["quantidade"] * p["preco"] for p in estoque)
    print(f"💰 Valor total do estoque: R$ {total:.2f}")
    return total


def produtos_estoque_baixo(estoque, limite=5):
    baixos = [p for p in estoque if p["quantidade"] < limite]
    if not baixos:
        print(f"✅ Nenhum produto com estoque abaixo de {limite} unidades.")
        return baixos
    print(f"\n⚠️ Produtos com estoque baixo (< {limite}):")
    for p in baixos:
        print(f"- {p['nome']} | Qtd: {p['quantidade']}")
    return baixos


# ===================== HISTÓRICO DE VENDAS =====================

def carregar_historico():
    if os.path.exists(ARQUIVO_HISTORICO):
        with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def salvar_historico(historico):
    with open(ARQUIVO_HISTORICO, "w", encoding="utf-8") as f:
        json.dump(historico, f, indent=4, ensure_ascii=False)


def registrar_venda(historico, nome_produto, quantidade, preco_unitario):
    venda = {
        "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "produto": nome_produto,
        "quantidade": quantidade,
        "preco_unitario": preco_unitario,
        "total": round(quantidade * preco_unitario, 2)
    }
    historico.append(venda)


def vender_produto(estoque, historico, nome_produto, quantidade_venda):
    produto = buscar_produto(estoque, nome_produto)
    if produto is None:
        print(f"❌ Produto '{nome_produto}' não encontrado no estoque.")
        return False
    if produto["quantidade"] < quantidade_venda:
        print(f"⚠️ Estoque insuficiente. Disponível: {produto['quantidade']}")
        return False
    produto["quantidade"] -= quantidade_venda
    registrar_venda(historico, produto["nome"], quantidade_venda, produto["preco"])
    print(f"✅ Venda realizada: {quantidade_venda}x {produto['nome']}")
    return True


def listar_historico(historico):
    if not historico:
        print("📭 Nenhuma venda registrada ainda.")
        return
    print("\n===== HISTÓRICO DE VENDAS =====")
    for venda in historico:
        print(f"[{venda['data_hora']}] {venda['quantidade']}x {venda['produto']} "
              f"| Unit: R$ {venda['preco_unitario']:.2f} | Total: R$ {venda['total']:.2f}")


def total_vendido(historico):
    total = sum(v["total"] for v in historico)
    print(f"📈 Total vendido: R$ {total:.2f}")
    return total


# ===================== FILTRAR VENDAS POR DATA =====================

def filtrar_vendas_por_data(historico, data_inicio_str, data_fim_str):
    """Filtra vendas entre duas datas (formato: DD/MM/AAAA)."""
    try:
        data_inicio = datetime.strptime(data_inicio_str, "%d/%m/%Y")
        data_fim = datetime.strptime(data_fim_str, "%d/%m/%Y").replace(hour=23, minute=59, second=59)
    except ValueError:
        print("❌ Formato de data inválido. Use DD/MM/AAAA.")
        return []

    resultado = []
    for venda in historico:
        data_venda = datetime.strptime(venda["data_hora"], "%Y-%m-%d %H:%M:%S")
        if data_inicio <= data_venda <= data_fim:
            resultado.append(venda)

    if not resultado:
        print("📭 Nenhuma venda encontrada nesse período.")
        return resultado

    print(f"\n===== VENDAS DE {data_inicio_str} A {data_fim_str} =====")
    total_periodo = 0
    for v in resultado:
        print(f"[{v['data_hora']}] {v['quantidade']}x {v['produto']} "
              f"| Unit: R$ {v['preco_unitario']:.2f} | Total: R$ {v['total']:.2f}")
        total_periodo += v["total"]
    print(f"\n💰 Total no período: R$ {total_periodo:.2f}")

    return resultado


# ===================== RELATÓRIO TXT =====================

def gerar_relatorio(estoque, historico):
    with open(ARQUIVO_RELATORIO, "w", encoding="utf-8") as f:
        f.write("=" * 40 + "\n")
        f.write("RELATÓRIO DE ESTOQUE E VENDAS\n")
        f.write(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
        f.write("=" * 40 + "\n\n")

        f.write("--- ESTOQUE ATUAL ---\n")
        if estoque:
            for p in estoque:
                f.write(f"{p['nome']:<20} Qtd: {p['quantidade']:<5} Preço: R$ {p['preco']:.2f}\n")
        else:
            f.write("Estoque vazio.\n")

        valor_estoque = sum(p["quantidade"] * p["preco"] for p in estoque)
        f.write(f"\nValor total em estoque: R$ {valor_estoque:.2f}\n")

        f.write("\n--- PRODUTOS COM ESTOQUE BAIXO (< 5) ---\n")
        baixos = [p for p in estoque if p["quantidade"] < 5]
        if baixos:
            for p in baixos:
                f.write(f"{p['nome']:<20} Qtd: {p['quantidade']}\n")
        else:
            f.write("Nenhum produto com estoque baixo.\n")

        f.write("\n--- HISTÓRICO DE VENDAS ---\n")
        if historico:
            for v in historico:
                f.write(f"[{v['data_hora']}] {v['quantidade']}x {v['produto']} "
                        f"| Unit: R$ {v['preco_unitario']:.2f} | Total: R$ {v['total']:.2f}\n")
            total = sum(v["total"] for v in historico)
            f.write(f"\nTotal vendido: R$ {total:.2f}\n")
        else:
            f.write("Nenhuma venda registrada.\n")

        f.write("\n" + "=" * 40 + "\n")
        f.write("FIM DO RELATÓRIO\n")

    print(f"📄 Relatório gerado com sucesso em '{ARQUIVO_RELATORIO}'!")


# ===================== RELATÓRIO PDF =====================

def gerar_relatorio_pdf(estoque, historico):
    """Gera um relatório em PDF."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Relatório de Estoque e Vendas", ln=True, align="C")

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 8, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True, align="C")
    pdf.ln(5)

    # Estoque
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "Estoque Atual", ln=True)
    pdf.set_font("Helvetica", "", 10)
    if estoque:
        for p in estoque:
            pdf.cell(0, 7, f"{p['nome']} | Qtd: {p['quantidade']} | R$ {p['preco']:.2f}", ln=True)
    else:
        pdf.cell(0, 7, "Estoque vazio.", ln=True)

    valor_estoque = sum(p["quantidade"] * p["preco"] for p in estoque)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, f"Valor total em estoque: R$ {valor_estoque:.2f}", ln=True)
    pdf.ln(5)

    # Estoque baixo
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "Produtos com Estoque Baixo (< 5)", ln=True)
    pdf.set_font("Helvetica", "", 10)
    baixos = [p for p in estoque if p["quantidade"] < 5]
    if baixos:
        for p in baixos:
            pdf.cell(0, 7, f"{p['nome']} | Qtd: {p['quantidade']}", ln=True)
    else:
        pdf.cell(0, 7, "Nenhum produto com estoque baixo.", ln=True)
    pdf.ln(5)

    # Histórico
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "Histórico de Vendas", ln=True)
    pdf.set_font("Helvetica", "", 9)
    if historico:
        for v in historico:
            texto = f"[{v['data_hora']}] {v['quantidade']}x {v['produto']} | Unit: R$ {v['preco_unitario']:.2f} | Total: R$ {v['total']:.2f}"
            pdf.cell(0, 6, texto, ln=True)
        total = sum(v["total"] for v in historico)
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, f"Total vendido: R$ {total:.2f}", ln=True)
    else:
        pdf.cell(0, 7, "Nenhuma venda registrada.", ln=True)

    pdf.output(ARQUIVO_RELATORIO_PDF)
    print(f"📄 Relatório PDF gerado com sucesso em '{ARQUIVO_RELATORIO_PDF}'!")


# ===================== GRÁFICO DE VENDAS =====================

def gerar_grafico_vendas(historico):
    """Gera um gráfico de barras com o total vendido por produto."""
    if not historico:
        print("📭 Nenhuma venda registrada. Não é possível gerar gráfico.")
        return

    totais_por_produto = {}
    for v in historico:
        totais_por_produto[v["produto"]] = totais_por_produto.get(v["produto"], 0) + v["total"]

    produtos = list(totais_por_produto.keys())
    valores = list(totais_por_produto.values())

    plt.figure(figsize=(8, 5))
    barras = plt.bar(produtos, valores, color="#4CAF50")
    plt.title("Total Vendido por Produto")
    plt.xlabel("Produto")
    plt.ylabel("Total Vendido (R$)")
    plt.xticks(rotation=30, ha="right")

    for barra, valor in zip(barras, valores):
        plt.text(barra.get_x() + barra.get_width() / 2, barra.get_height(),
                  f"R$ {valor:.2f}", ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    plt.savefig(ARQUIVO_GRAFICO)
    plt.close()
    print(f"📊 Gráfico gerado com sucesso em '{ARQUIVO_GRAFICO}'!")


# ===================== MENU PRINCIPAL =====================

def menu():
    estoque = carregar_estoque()
    historico = carregar_historico()

    if not estoque:
        adicionar_produto(estoque, "Notebook", 10, 3500.00)
        adicionar_produto(estoque, "Mouse", 20, 45.00)
        adicionar_produto(estoque, "Teclado", 15, 90.00)
        salvar_estoque(estoque)

    while True:
        print("\n===== MENU =====")
        print("1. Listar produtos")
        print("2. Vender produto")
        print("3. Adicionar produto")
        print("4. Ver valor total do estoque")
        print("5. Produtos com estoque baixo")
        print("6. Ver histórico de vendas")
        print("7. Ver total vendido")
        print("8. Gerar relatório (.txt)")
        print("9. Gerar relatório (.pdf)")
        print("10. Filtrar vendas por data")
        print("11. Gerar gráfico de vendas")
        print("12. Sair")

        opcao = input("Escolha uma opção: ").strip()

        if opcao == "1":
            listar_produtos(estoque)

        elif opcao == "2":
            nome = input("Nome do produto a vender: ")
            try:
                qtd = int(input("Quantidade a vender: "))
                if vender_produto(estoque, historico, nome, qtd):
                    salvar_estoque(estoque)
                    salvar_historico(historico)
            except ValueError:
                print("❌ Quantidade inválida.")

        elif opcao == "3":
            nome = input("Nome do produto: ")
            try:
                qtd = int(input("Quantidade: "))
                preco = float(input("Preço unitário: "))
                adicionar_produto(estoque, nome, qtd, preco)
                salvar_estoque(estoque)
            except ValueError:
                print("❌ Quantidade ou preço inválido.")

        elif opcao == "4":
            valor_total_estoque(estoque)

        elif opcao == "5":
            produtos_estoque_baixo(estoque)

        elif opcao == "6":
            listar_historico(historico)

        elif opcao == "7":
            total_vendido(historico)

        elif opcao == "8":
            gerar_relatorio(estoque, historico)

        elif opcao == "9":
            gerar_relatorio_pdf(estoque, historico)

        elif opcao == "10":
            data_inicio = input("Data inicial (DD/MM/AAAA): ")
            data_fim = input("Data final (DD/MM/AAAA): ")
            filtrar_vendas_por_data(historico, data_inicio, data_fim)

        elif opcao == "11":
            gerar_grafico_vendas(historico)

        elif opcao == "12":
            print("👋 Saindo do sistema...")
            break

        else:
            print("❌ Opção inválida. Tente novamente.")


if __name__ == "__main__":
    menu()
