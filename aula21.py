def ler_int(mensagem):
    while True:
        try:
            return int(input(mensagem))
        except ValueError:
            print("❌ Digite um número válido.")


def buscar_itens_por_nome(estoque, nome):
    return [item for item in estoque if item["nome"].lower() == nome]


def vender_produto(estoque):
    nome = input("Nome do produto a vender: ").strip().lower()
    itens = buscar_itens_por_nome(estoque, nome)

    if not itens:
        print(f"❌ Produto '{nome}' não encontrado no estoque.")
        return

    if len(itens) > 1:
        print(f"\n⚠️ Existem múltiplos itens com o nome '{nome}':")
        for i, item in enumerate(itens, start=1):
            print(f"{i}. R$ {item['preco']:.2f} - {item['quantidade']} unidades")
        escolha = ler_int("Escolha o número do item para vender: ")
        if escolha < 1 or escolha > len(itens):
            print("❌ Opção inválida.")
            return
        item_selecionado = itens[escolha - 1]
    else:
        item_selecionado = itens[0]

    quantidade = ler_int("Quantidade a vender: ")

    if quantidade > item_selecionado["quantidade"]:
        print(f"❌ Estoque insuficiente! Disponível: {item_selecionado['quantidade']} unidades.")
        return

    item_selecionado["quantidade"] -= quantidade
    total = quantidade * item_selecionado["preco"]
    print(f"✅ Venda realizada: {quantidade}x {nome} - Total: R$ {total:.2f}")

    if item_selecionado["quantidade"] == 0:
        estoque.remove(item_selecionado)
        print(f"🗑️ '{nome}' (R$ {item_selecionado['preco']:.2f}) removido do estoque (quantidade zerada).")


# --- Bloco de teste ---
if __name__ == "__main__":
    estoque_teste = [
        {"nome": "arroz", "preco": 25.0, "quantidade": 10},
        {"nome": "feijao", "preco": 8.5, "quantidade": 5},
    ]
    vender_produto(estoque_teste)
