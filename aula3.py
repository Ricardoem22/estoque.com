idade = input("Quantos anos você tem? ")
idade = int(idade)

if idade < 12:
    print("Você é uma criança. 🧒")
elif idade < 18:
    print("Você é um adolescente. 🧑")
elif idade < 60:
    print("Você é um adulto. 👨")
else:
    print("Você é um idoso. 👴")
