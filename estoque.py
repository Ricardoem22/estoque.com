import sqlite3
from datetime import datetime

BANCO = "loja.db"
ESTOQUE_MINIMO = 5  # limite para considerar "estoque baixo"


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


# ---------- 1. LISTAR PRODUTOS ----------
def listar_produtos():
    conn = conectar()
    produtos = conn.execute("SELECT * FROM produtos ORDER BY nome").fetchall()
    conn.close()

    if not produtos:
        print("📭 Nenhum produto cadastrado.")
        return

    print("\n📦 PRODUTOS EM ESTOQUE")
    print("-" * 50)
    for p in produtos:
        print(f"ID: {p['id']} | {p['nome']} | Qtd: {p['quantidade']} | R$ {p['preco']:.2f}")
    print("-" * 50)


# ---------- 2. VENDER PRODUTO ----------
def vender_produto():
    conn = conectar()
    nome = input("Nome do produto a vender: ").strip()
    produto = conn.execute("SELECT * FROM produtos WHERE nome = ?", (nome,)).fetchone()

    if not produto:
        print("❌ Produto não encontrado.")
        conn.close()
        return

    try:
        quantidade = int(input(f"Quantidade a vender (disponível: {produto['quantidade']}): "))
    except ValueError:
        print("❌ Quantidade inválida.")
        conn.close()
        return

    if quantidade <= 0:
        print("❌ Quantidade deve ser maior que zero.")
        conn.close()
        return

    if quantidade > produto["quantidade"]:
        print("❌ Estoque insuficiente.")
        conn.close()
        return

    total = round(quantidade * produto["preco"], 2)
    nova_qtd = produto["quantidade"] - quantidade
    data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor = conn.cursor()
    cursor.execute("UPDATE produtos SET quantidade = ? WHERE id = ?", (nova_qtd, produto["id"]))
    cursor.execute(
        "INSERT INTO vendas (produto, quantidade, preco_unitario, total, data_hora) VALUES (?, ?, ?, ?, ?)",
        (produto["nome"], quantidade, produto["preco"], total, data_hora)
    )
    conn.commit()
    conn.close()
    print(f"✅ Venda registrada: {quantidade}x {nome} = R$ {total:.2f}")


# ---------- 3. ADICIONAR PRODUTO ----------
def adicionar_produto():
    nome = input("Nome do produto: ").strip()
    if not nome:
        print("❌ Nome inválido.")
        return

    try:
        quantidade = int(input("Quantidade: "))
        preco = float(input("Preço unitário (ex: 19.90): "))
    except ValueError:
        print("❌ Valores inválidos.")
        return

    conn = conectar()
    existente = conn.execute("SELECT * FROM produtos WHERE nome = ?", (nome,)).fetchone()

    if existente:
        nova_qtd = existente["quantidade"] + quantidade
        conn.execute(
            "UPDATE produtos SET quantidade = ?, preco = ? WHERE id = ?",
            (nova_qtd, preco, existente["id"])
        )
        print(f"✅ Estoque atualizado: {nome} agora tem {nova_qtd} unidades.")
    else:
        conn.execute(
            "INSERT INTO produtos (nome, quantidade, preco) VALUES (?, ?, ?)",
            (nome, quantidade, preco)
        )
        print(f"✅ Produto '{nome}' cadastrado com sucesso.")

    conn.commit()
    conn.close()


# ---------- 4. VALOR TOTAL DO ESTOQUE ----------
def valor_total_estoque():
    conn = conectar()
    produtos = conn.execute("SELECT * FROM produtos").fetchall()
    conn.close()

    total = sum(p["quantidade"] * p["preco"] for p in produtos)
    print(f"\n💰 Valor total do estoque: R$ {total:.2f}")


# ---------- 5. PRODUTOS COM ESTOQUE BAIXO ----------
def produtos_estoque_baixo():
    conn = conectar()
    produtos = conn.execute(
        "SELECT * FROM produtos WHERE quantidade <= ? ORDER BY quantidade", (ESTOQUE_MINIMO,)
    ).fetchall()
    conn.close()

    if not produtos:
        print(f"✅ Nenhum produto com estoque <= {ESTOQUE_MINIMO}.")
        return

    print(f"\n⚠️ PRODUTOS COM ESTOQUE BAIXO (<= {ESTOQUE_MINIMO})")
    for p in produtos:
        print(f"{p['nome']} | Qtd: {p['quantidade']}")


# ---------- 6. HISTÓRICO DE VENDAS ----------
def historico_vendas():
    conn = conectar()
    vendas = conn.execute("SELECT * FROM vendas ORDER BY data_hora DESC").fetchall()
    conn.close()

    if not vendas:
        print("📭 Nenhuma venda registrada.")
        return

    print("\n🧾 HISTÓRICO DE VENDAS")
    print("-" * 60)
    for v in vendas:
        print(f"{v['data_hora']} | {v['produto']} | Qtd: {v['quantidade']} | Total: R$ {v['total']:.2f}")
    print("-" * 60)


# ---------- 7. TOTAL VENDIDO ----------
def total_vendido():
    conn = conectar()
    resultado = conn.execute("SELECT SUM(total) as soma FROM vendas").fetchone()
    conn.close()
    soma = resultado["soma"] or 0
    print(f"\n💵 Total vendido: R$ {soma:.2f}")


# ---------- 8. RELATÓRIO .TXT ----------
def gerar_relatorio_txt():
    conn = conectar()
    produtos = conn.execute("SELECT * FROM produtos ORDER BY nome").fetchall()
    vendas = conn.execute("SELECT * FROM vendas ORDER BY data_hora").fetchall()
    conn.close()

    with open("relatorio.txt", "w", encoding="utf-8") as f:
        f.write("RELATÓRIO DE ESTOQUE E VENDAS\n")
        f.write(f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("=== PRODUTOS ===\n")
        for p in produtos:
            f.write(f"{p['nome']} | Qtd: {p['quantidade']} | R$ {p['preco']:.2f}\n")

        f.write("\n=== VENDAS ===\n")
        total_geral = 0
        for v in vendas:
            f.write(f"{v['data_hora']} | {v['produto']} | Qtd: {v['quantidade']} | R$ {v['total']:.2f}\n")
            total_geral += v["total"]

        f.write(f"\nTotal vendido: R$ {total_geral:.2f}\n")

    print("✅ Relatório 'relatorio.txt' gerado com sucesso.")


# ---------- 9. RELATÓRIO .PDF ----------
def gerar_relatorio_pdf():
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        print("❌ Instale a biblioteca: pip install reportlab")
        return

    conn = conectar()
    produtos = conn.execute("SELECT * FROM produtos ORDER BY nome").fetchall()
    vendas = conn.execute("SELECT * FROM vendas ORDER BY data_hora").fetchall()
    conn.close()

    c = canvas.Canvas("relatorio.pdf", pagesize=A4)
    largura, altura = A4
    y = altura - 50

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Relatório de Estoque e Vendas")
    y -= 20
    c.setFont("Helvetica", 9)
    c.drawString(50, y, f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    y -= 30

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Produtos")
    y -= 20
    c.setFont("Helvetica", 10)
    for p in produtos:
        c.drawString(50, y, f"{p['nome']} | Qtd: {p['quantidade']} | R$ {p['preco']:.2f}")
        y -= 15
        if y < 60:
            c.showPage()
            y = altura - 50

    y -= 15
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Vendas")
    y -= 20
    c.setFont("Helvetica", 10)
    total_geral = 0
    for v in vendas:
        c.drawString(50, y, f"{v['data_hora']} | {v['produto']} | Qtd: {v['quantidade']} | R$ {v['total']:.2f}")
        total_geral += v["total"]
        y -= 15
        if y < 60:
            c.showPage()
            y = altura - 50

    y -= 15
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, f"Total vendido: R$ {total_geral:.2f}")

    c.save()
    print("✅ Relatório 'relatorio.pdf' gerado com sucesso.")


# ---------- 10. FILTRAR VENDAS POR DATA ----------
def filtrar_vendas_por_data():
    data = input("Digite a data (formato AAAA-MM-DD): ").strip()

    conn = conectar()
    vendas = conn.execute(
        "SELECT * FROM vendas WHERE data_hora LIKE ? ORDER BY data_hora", (f"{data}%",)
    ).fetchall()
    conn.close()

    if not vendas:
        print(f"📭 Nenhuma venda encontrada em {data}.")
        return

    print(f"\n🔎 VENDAS EM {data}")
    total = 0
    for v in vendas:
        print(f"{v['data_hora']} | {v['produto']} | Qtd: {v['quantidade']} | R$ {v['total']:.2f}")
        total += v["total"]
    print(f"\nTotal do dia: R$ {total:.2f}")


# ---------- 11. GRÁFICO DE VENDAS ----------
def gerar_grafico_vendas():
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("❌ Instale a biblioteca: pip install matplotlib")
        return

    conn = conectar()
    dados = conn.execute("""
        SELECT produto, SUM(quantidade) as total_qtd
        FROM vendas
        GROUP BY produto
        ORDER BY total_qtd DESC
    """).fetchall()
    conn.close()

    if not dados:
        print("📭 Nenhuma venda para gerar gráfico.")
        return

    produtos = [d["produto"] for d in dados]
    quantidades = [d["total_qtd"] for d in dados]

    plt.figure(figsize=(8, 5))
    plt.bar(produtos, quantidades, color="steelblue")
    plt.title("Quantidade Vendida por Produto")
    plt.xlabel("Produto")
    plt.ylabel("Quantidade Vendida")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig("grafico_vendas.png")
    plt.close()

    print("✅ Gráfico 'grafico_vendas.png' gerado com sucesso.")


# ---------- MENU PRINCIPAL ----------
def menu():
    criar_tabelas()

    opcoes = {
        "1": listar_produtos,
        "2": vender_produto,
        "3": adicionar_produto,
        "4": valor_total_estoque,
        "5": produtos_estoque_baixo,
        "6": historico_vendas,
        "7": total_vendido,
        "8": gerar_relatorio_txt,
        "9": gerar_relatorio_pdf,
        "10": filtrar_vendas_por_data,
        "11": gerar_grafico_vendas,
    }

    while True:
        print("""
==== MENU =====
1. Listar produtos
2. Vender produto
3. Adicionar produto
4. Ver valor total do estoque
5. Produtos com estoque baixo
6. Ver histórico de vendas
7. Ver total vendido
8. Gerar relatório (.txt)
9. Gerar relatório (.pdf)
10. Filtrar vendas por data
11. Gerar gráfico de vendas
12. Sair
""")
        escolha = input("Escolha uma opção: ").strip()

        if escolha == "12":
            print("👋 Saindo... Até logo!")
            break

        acao = opcoes.get(escolha)
        if acao:
            acao()
        else:
            print("❌ Opção inválida.")


if __name__ == "__main__":
    menu()
