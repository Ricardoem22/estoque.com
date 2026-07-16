# main.py
from database import (
    init_db, adicionar_produto, listar_produtos, buscar_produto,
    vender_produto, valor_total_estoque, produtos_estoque_baixo,
    historico_vendas, total_vendido, ValidationError
)
from backup import criar_backup
from datetime import datetime


def exibir_produtos():
    produtos = listar_produtos()
    print("\n📦 PRODUTOS EM ESTOQUE")
    print("-" * 50)
    if not produtos:
        print("Nenhum produto cadastrado.")
    for p in produtos:
        print(f"ID: {p['id']} | {p['nome']} | Qtd: {p['quantidade']} | R$ {p['preco']:.2f}")
    print("-" * 50)


def menu_vender():
    exibir_produtos()
    try:
        produto_id = int(input("ID do produto: "))
        quantidade = int(input("Quantidade a vender: "))
    except ValueError:
        print("❌ Entrada inválida. Digite números.")
        return

    try:
        criar_backup()  # backup antes de operação crítica
        valor = vender_produto(produto_id, quantidade)
        print(f"✅ Venda realizada! Valor: R$ {valor:.2f}")
    except ValidationError as e:
        print(f"❌ {e}")


def menu_adicionar():
    nome = input("Nome do produto: ")
    quantidade = input("Quantidade: ")
    preco = input("Preço (R$): ")

    try:
        criar_backup()
        adicionar_produto(nome, quantidade, preco)
        print(f"✅ Produto '{nome.strip()}' adicionado com sucesso!")
    except ValidationError as e:
        print(f"❌ {e}")


def exibir_estoque_baixo():
    produtos = produtos_estoque_baixo()
    print("\n⚠️ PRODUTOS COM ESTOQUE BAIXO (<= 5)")
    if not produtos:
        print("Nenhum produto com estoque baixo.")
    for p in produtos:
        print(f"{p['nome']} | Qtd: {p['quantidade']}")


def exibir_historico():
    vendas = historico_vendas()
    print("\n🧾 HISTÓRICO DE VENDAS")
    print("-" * 60)
    if not vendas:
        print("Nenhuma venda registrada.")
    for v in vendas:
        print(f"[{v['data']}] {v['nome']} | Qtd: {v['quantidade']} | R$ {v['valor_total']:.2f}")
    print("-" * 60)


def filtrar_vendas_por_data():
    data_str = input("Digite a data (AAAA-MM-DD): ")
    try:
        datetime.strptime(data_str, "%Y-%m-%d")
    except ValueError:
        print("❌ Formato de data inválido.")
        return

    vendas = [v for v in historico_vendas() if v['data'].startswith(data_str)]
    print(f"\n📅 VENDAS EM {data_str}")
    if not vendas:
        print("Nenhuma venda encontrada nesta data.")
    for v in vendas:
        print(f"[{v['data']}] {v['nome']} | Qtd: {v['quantidade']} | R$ {v['valor_total']:.2f}")


def gerar_relatorio_txt():
    produtos = listar_produtos()
    vendas = historico_vendas()
    nome_arquivo = f"relatorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    with open(nome_arquivo, "w", encoding="utf-8") as f:
        f.write("RELATÓRIO DE ESTOQUE E VENDAS\n")
        f.write("=" * 50 + "\n\n")
        f.write("PRODUTOS EM ESTOQUE:\n")
        for p in produtos:
            f.write(f"ID: {p['id']} | {p['nome']} | Qtd: {p['quantidade']} | R$ {p['preco']:.2f}\n")

        f.write(f"\nValor total do estoque: R$ {valor_total_estoque():.2f}\n")
        f.write(f"Total vendido: R$ {total_vendido():.2f}\n\n")

        f.write("HISTÓRICO DE VENDAS:\n")
        for v in vendas:
            f.write(f"[{v['data']}] {v['nome']} | Qtd: {v['quantidade']} | R$ {v['valor_total']:.2f}\n")

    print(f"✅ Relatório salvo em: {nome_arquivo}")


def menu():
    init_db()  # garante que as tabelas existam

    opcoes = {
        "1": exibir_produtos,
        "2": menu_vender,
        "3": menu_adicionar,
        "4": lambda: print(f"\n💰 Valor total do estoque: R$ {valor_total_estoque():.2f}"),
        "5": exibir_estoque_baixo,
        "6": exibir_historico,
        "7": lambda: print(f"\n💵 Total vendido: R$ {total_vendido():.2f}"),
        "8": gerar_relatorio_txt,
        "10": filtrar_vendas_por_data,
    }

    while True:
        print("\n==== MENU =====")
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

        escolha = input("\nEscolha uma opção: ").strip()

        if escolha == "12":
            print("👋 Saindo...")
            break

        acao = opcoes.get(escolha)
        if acao:
            acao()
        elif escolha in ("9", "11"):
            print("⚠️ Funcionalidade ainda não integrada (mantenha seu código original de .pdf/gráfico aqui).")
        else:
            print("❌ Opção inválida.")


if __name__ == "__main__":
    menu()
