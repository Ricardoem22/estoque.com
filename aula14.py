def saudacao(nome):
    print(f"Olá, {nome}! Bem-vindo(a)! 👋")

def somar(a, b):
    resultado = a + b
    return resultado

def calcular_media(notas):
    if len(notas) == 0:
        return 0
    return sum(notas) / len(notas)

def apresentar_cliente(nome, idade=18):  # valor padrão
    print(f"{nome} tem {idade} anos.")


# Usando as funções
saudacao("Ricardo")

resultado_soma = somar(5, 3)
print("Soma:", resultado_soma)

notas = [8, 7, 9.5, 6]
media = calcular_media(notas)
print("Média:", media)

apresentar_cliente("Ana", 30)
apresentar_cliente("Bruno")  # usa o valor padrão (18)
