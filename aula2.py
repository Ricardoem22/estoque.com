nome = input("Qual é o seu nome? ")
idade = input("Quantos anos você tem? ")

# Convertendo idade de texto (str) para número inteiro (int)
idade = float(idade)

# Calculando em quantos anos a pessoa fará 100 anos
anos_para_100 = 100 - idade

print(f"Olá, {nome}!")
print(f"Você tem {idade} anos.")
print(f"Em {anos_para_100} anos, você completará 100 anos! 🎂")
