lista_compras = []

print("=== Lista de Compras ===\n")

while True:
    item = input("Digite um item (ou 'sair' para terminar): ")
    
    if item.lower() == "sair":
        break
    
    lista_compras.append(item)
    print(f"'{item}' adicionado! ✅\n")

print("\n=== Sua lista final ===")
if len(lista_compras) == 0:
    print("Nenhum item adicionado.")
else:
    for i, item in enumerate(lista_compras, start=1):
        print(f"{i}. {item}")
