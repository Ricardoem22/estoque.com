# ===== Parte 1: Dados iniciais =====
nome = input("Qual é o seu nome? ")
idade = int(input("Quantos anos você tem? "))  # convertendo texto para número

print(f"Olá, {nome}! Bem-vindo à programação 🚀")
print(f"No ano que vem você terá {idade + 1} anos!")

# ===== Parte 2: Condição (if/else) =====
if idade >= 18:
    print("Você é maior de idade! ✅")
else:
    print("Você é menor de idade. Ainda dá tempo de aprender muito! 😄")

# ===== Parte 3: Mini quiz =====
print("\n--- Vamos fazer um mini quiz! ---")

pontos = 0

resposta1 = input("1) Qual linguagem estamos aprendendo agora? ")
if resposta1.lower() == "python":
    print("Certo! ✅")
    pontos += 1
else:
    print("Errado! A resposta era Python.")

resposta2 = input("2) Quanto é 5 + 3? ")
if resposta2 == "8":
    print("Certo! ✅")
    pontos += 1
else:
    print("Errado! A resposta era 8.")

resposta3 = input("3) O Python usa chaves { } para blocos de código? (sim/nao) ")
if resposta3.lower() == "nao":
    print("Certo! ✅ (Python usa indentação, não chaves)")
    pontos += 1
else:
    print("Errado! Python usa indentação (espaços), não chaves.")

print(f"\nFim do quiz, {nome}! Você acertou {pontos} de 3 perguntas.")
