def cadastrar_produto(nome, preco, estoque):
    return {"nome": nome, "preco": preco, "estoque": estoque}

def exibir_produto(produto):
    print(f"📦 {produto['nome']} - R$ {produto['preco']:.2f} - {produto['estoque']} unidades")

def calcular_valor_total(produtos):
    total = 0
    for produto in produtos:
        total += produto["preco"] * produto["estoque"]
    return total

def buscar_produto(produtos, nome_buscado):
    for produto in produtos:
        if produto["nome"].lower() == nome_buscado.lower():
            return produto
    return None


# Cadastrando produtos
estoque = []
estoque.append(cadastrar_produto("Notebook", 3500.00, 5))
estoque.append(cadastrar_produto("Mouse", 50.00, 20))
estoque.append(cadastrar_produto("Teclado", 120.00, 15))

print("=== Estoque Atual ===")
for produto in estoque:
    exibir_produto(produto)

valor_total = calcular_valor_total(estoque)
print(f"\n💰 Valor total em estoque: R$ {valor_total:.2f}")

# Buscando um produto
busca = buscar_produto(estoque, "mouse")
if busca:
    print(f"\n🔍 Encontrado: {busca}")
else:
    print("\n🔍 Produto não encontrado.")
