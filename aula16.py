def dividir(a, b):
    try:
        resultado = a / b
        return resultado
    except ZeroDivisionError:
        print("❌ Erro: não é possível dividir por zero!")
        return None

def converter_para_numero(valor):
    try:
        numero = float(valor)
        return numero
    except ValueError:
        print(f"❌ Erro: '{valor}' não é um número válido!")
        return None


# Testando divisão
print(dividir(10, 2))
print(dividir(10, 0))  # vai cair no except

# Testando conversão
print(converter_para_numero("42"))
print(converter_para_numero("abc"))  # vai cair no except

# Exemplo com input do usuário (protegido)
entrada = input("Digite um número: ")
numero = converter_para_numero(entrada)
if numero is not None:
    print(f"Você digitou: {numero}")

