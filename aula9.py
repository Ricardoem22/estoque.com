# Introdução a listas

frutas = ["maçã", "banana", "uva", "laranja"]

print("Lista de frutas:", frutas)
print("Primeira fruta:", frutas[0])
print("Última fruta:", frutas[-1])
print("Quantidade de frutas:", len(frutas))

# Adicionando um item
frutas.append("morango")
print("\nApós adicionar morango:", frutas)

# Percorrendo a lista
print("\nTodas as frutas:")
for fruta in frutas:
    print(f"- {fruta}")
