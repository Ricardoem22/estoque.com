import json
import os
import sqlite3
from datetime import datetime

BANCO = "loja.db"

# Ajuste os nomes se os seus arquivos JSON tiverem nomes diferentes
ARQUIVO_ESTOQUE_JSON = "estoque.json"
ARQUIVO_HISTORICO_JSON = "historico_vendas.json"


def conectar():
    conn = sqlite3.connect(BANCO)
    conn.row_factory = sqlite3.Row
    return conn


def criar_tabelas():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            quantidade INTEGER NOT NULL,
            preco REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto TEXT NOT NULL,
            quantidade INTEGER NOT NULL,
            preco_unitario REAL NOT NULL,
            total REAL NOT NULL,
            data_hora TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def migrar_estoque():
    if not os.path.exists(ARQUIVO_ESTOQUE_JSON):
        print(f"⚠️ Arquivo '{ARQUIVO_ESTOQUE_JSON}' não encontrado. Pulando estoque.")
        return

    with open(ARQUIVO_ESTOQUE_JSON, "r", encoding="utf-8") as f:
        estoque = json.load(f)

    if not estoque:
        print("📭 Estoque JSON estava vazio.")
        return

    conn = conectar()
    cursor = conn.cursor()
    contador = 0

    # Suporta tanto lista de dicts [{"nome":..,"quantidade":..,"preco":..}, ...]
    # quanto dicionário {"nome_produto": {"quantidade":.., "preco":..}, ...}
    if isinstance(estoque, dict):
        itens = [{"nome": nome, **dados} for nome, dados in estoque.items()]
    else:
        itens = estoque

    for item in itens:
        nome = item.get("nome")
        quantidade = item.get("quantidade", 0)
        preco = item.get("preco", 0.0)

        if not nome:
            continue

        cursor.execute(
            "INSERT OR REPLACE INTO produtos (nome, quantidade, preco) VALUES (?, ?, ?)",
            (nome.strip(), quantidade, preco)
        )
        contador += 1

    conn.commit()
    conn.close()
    print(f"✅ {contador} produto(s) migrado(s) para o banco.")


def migrar_historico():
    if not os.path.exists(ARQUIVO_HISTORICO_JSON):
        print(f"⚠️ Arquivo '{ARQUIVO_HISTORICO_JSON}' não encontrado. Pulando histórico.")
        return

    with open(ARQUIVO_HISTORICO_JSON, "r", encoding="utf-8") as f:
        historico = json.load(f)

    if not historico:
        print("📭 Histórico JSON estava vazio.")
        return

    conn = conectar()
    cursor = conn.cursor()
    contador = 0

    for venda in historico:
        produto = venda.get("produto")
        quantidade = venda.get("quantidade", 0)
        preco_unitario = venda.get("preco_unitario", venda.get("preco", 0.0))
        total = venda.get("total", round(quantidade * preco_unitario, 2))
        data_hora = venda.get("data_hora", venda.get("data", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        if not produto:
            continue

        cursor.execute(
            "INSERT INTO vendas (produto, quantidade, preco_unitario, total, data_hora) VALUES (?, ?, ?, ?, ?)",
            (produto, quantidade, preco_unitario, total, data_hora)
        )
        contador += 1

    conn.commit()
    conn.close()
    print(f"✅ {contador} venda(s) migrada(s) para o banco.")


if __name__ == "__main__":
    print("🚀 Iniciando migração JSON → SQLite...\n")
    criar_tabelas()
    migrar_estoque()
    migrar_historico()
    print("\n🎉 Migração concluída! Agora você pode usar o sistema com 'loja.db'.")
