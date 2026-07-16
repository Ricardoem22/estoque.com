import json
import sqlite3

# 1. Conecta (ou cria) o banco de dados
conexao = sqlite3.connect("estoque.db")
cursor = conexao.cursor()

# 2. Garante que a tabela existe (ajuste os campos se seu banco já tiver outra estrutura)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        quantidade INTEGER NOT NULL,
        preco REAL NOT NULL
    )
""")

# 3. Lê o arquivo JSON antigo
with open("estoque.json", "r", encoding="utf-8") as arquivo:
    produtos = json.load(arquivo)

# 4. Insere cada produto no banco
for produto in produtos:
    cursor.execute(
        "INSERT INTO produtos (nome, quantidade, preco) VALUES (?, ?, ?)",
        (produto["nome"], produto["quantidade"], produto["preco"])
    )

# 5. Salva as alterações e fecha a conexão
conexao.commit()
conexao.close()

print(f"✅ Migração concluída! {len(produtos)} produtos importados com sucesso.")
