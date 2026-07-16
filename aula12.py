pessoa = {
    "nome": "Ricardo",
    "idade": 25,
    "cidade": "Joinville"
}

print("Nome:", pessoa["nome"])
print("Idade:", pessoa["idade"])
print("Cidade:", pessoa["cidade"])

# Adicionando/alterando uma chave
pessoa["profissao"] = "Estudante"
print("\nDicionário atualizado:", pessoa)

# Percorrendo o dicionário
print("\nTodos os dados:")
for chave, valor in pessoa.items():
    print(f"{chave}: {valor}")

