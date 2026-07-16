produto = {
    "nome": "Notebook",
    "preco": 3500.00,
    "estoque": 10
}

# 1. Verificando se uma chave existe
if "preco" in produto:
    print("O produto tem preço definido:", produto["preco"])

# 2. Usando .get() (mais seguro que [ ])
print("Marca:", produto.get("marca", "Não informada"))

# 3. Removendo uma chave
produto.pop("estoque")
print("\nApós remover 'estoque':", produto)

# 4. Lista de dicionários (muito comum!)
clientes = [
    {"nome": "Ana", "idade": 30},
    {"nome": "Bruno", "idade": 22},
    {"nome": "Carla", "idade": 45}
]

print("\n=== Lista de Clientes ===")
for cliente in clientes:
    print(f"{cliente['nome']} tem {cliente['idade']} anos")

