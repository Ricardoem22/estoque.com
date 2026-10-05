# database.py
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import config

DB_PATH = config.DB_PATH


def init_db():
    """Cria as tabelas se não existirem."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                quantidade INTEGER NOT NULL CHECK(quantidade >= 0),
                preco REAL NOT NULL CHECK(preco >= 0)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vendas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                produto_id INTEGER NOT NULL,
                quantidade INTEGER NOT NULL CHECK(quantidade > 0),
                valor_total REAL NOT NULL,
                data TEXT NOT NULL,
                FOREIGN KEY (produto_id) REFERENCES produtos(id)
            )
        """)
        conn.commit()


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


class ValidationError(Exception):
    """Erro de validação de dados de entrada."""
    pass


def validar_produto(nome: str, quantidade, preco):
    if not nome or not nome.strip():
        raise ValidationError("Nome do produto não pode ser vazio.")
    try:
        quantidade = int(quantidade)
        preco = float(preco)
    except (ValueError, TypeError):
        raise ValidationError("Quantidade deve ser inteiro e preço deve ser numérico.")
    if quantidade < 0:
        raise ValidationError("Quantidade não pode ser negativa.")
    if preco < 0:
        raise ValidationError("Preço não pode ser negativo.")
    return nome.strip(), quantidade, preco


def adicionar_produto(nome, quantidade, preco):
    nome, quantidade, preco = validar_produto(nome, quantidade, preco)
    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO produtos (nome, quantidade, preco) VALUES (?, ?, ?)",
                (nome, quantidade, preco)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise ValidationError(f"Produto '{nome}' já existe.")


def listar_produtos():
    with get_connection() as conn:
        return conn.execute("SELECT * FROM produtos ORDER BY id").fetchall()


def buscar_produto(produto_id):
    with get_connection() as conn:
        produto = conn.execute(
            "SELECT * FROM produtos WHERE id = ?", (produto_id,)
        ).fetchone()
        if not produto:
            raise ValidationError(f"Produto ID {produto_id} não encontrado.")
        return produto


def vender_produto(produto_id, quantidade):
    if not isinstance(quantidade, int) or quantidade <= 0:
        raise ValidationError("Quantidade vendida deve ser um inteiro positivo.")

    with get_connection() as conn:
        produto = conn.execute(
            "SELECT * FROM produtos WHERE id = ?", (produto_id,)
        ).fetchone()

        if not produto:
            raise ValidationError(f"Produto ID {produto_id} não encontrado.")

        if produto["quantidade"] < quantidade:
            raise ValidationError(
                f"Estoque insuficiente. Disponível: {produto['quantidade']}"
            )

        valor_total = quantidade * produto["preco"]
        data = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn.execute(
            "UPDATE produtos SET quantidade = quantidade - ? WHERE id = ?",
            (quantidade, produto_id)
        )
        conn.execute(
            "INSERT INTO vendas (produto_id, quantidade, valor_total, data) VALUES (?, ?, ?, ?)",
            (produto_id, quantidade, valor_total, data)
        )
        conn.commit()
        return valor_total


def valor_total_estoque():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT SUM(quantidade * preco) AS total FROM produtos"
        ).fetchone()
        return row["total"] or 0.0


def produtos_estoque_baixo(limite=5):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM produtos WHERE quantidade <= ?", (limite,)
        ).fetchall()


def historico_vendas():
    with get_connection() as conn:
        return conn.execute("""
            SELECT v.id, p.nome, v.quantidade, v.valor_total, v.data
            FROM vendas v
            JOIN produtos p ON v.produto_id = p.id
            ORDER BY v.data DESC
        """).fetchall()


def total_vendido():
    with get_connection() as conn:
        row = conn.execute("SELECT SUM(valor_total) AS total FROM vendas").fetchone()
        return row["total"] or 0.0
