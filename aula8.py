soma = 0
contador = 0

numero = float(input("Digite um número (0 para parar): "))

while numero != 0:
    soma += numero
    contador += 1
    numero = float(input("Digite outro número (0 para parar): "))

print(f"\nVocê digitou {contador} número(s).")
print(f"A soma total foi: {soma}")
