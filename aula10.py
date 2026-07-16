numeros = [10, 25, 3, 47, 8, 19]

# 1. Ordenando a lista
numeros.sort()
print("Lista ordenada:", numeros)

# 2. Encontrando o maior e o menor
print("Maior número:", max(numeros))
print("Menor número:", min(numeros))

# 3. Somando todos os itens
print("Soma total:", sum(numeros))

# 4. Removendo um item
numeros.remove(25)
print("\nApós remover o 25:", numeros)

# 5. Verificando se um número está na lista
if 47 in numeros:
    print("O número 47 está na lista!")
else:
    print("O número 47 não está na lista.")
