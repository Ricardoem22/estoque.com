# Programa que soma números digitados pelo usuário

quantidade = int(input("Quantos números você quer somar? "))
soma = 0

for i in range(1, quantidade + 1):
    numero = float(input(f"Digite o número {i}: "))
    soma += numero

print(f"\nA soma total é: {soma}")

if soma > 0:
    print("O resultado é positivo! 😀")
elif soma < 0:
    print("O resultado é negativo! 😞")
else:
    print("O resultado é zero! 😐")
