class Produto:
    def __init__(self, nome, preco, estoque):
        self.nome = nome
        self.preco = preco
        self.estoque = estoque

    def exibir(self):
        print(f"📦 {self.nome} - R$ {self.preco:.2f} - {self.estoque} unidades")

    def valor_total(self):
        return self.preco * self.estoque

    def vender(self, quantidade):
        if quantidade > self.estoque:
            print(f"❌ Estoque insuficiente de {self.nome}!")
        else:
            self.estoque -= quantidade
            print(f"✅ Vendido {quantidade}x {self.nome}. Estoque restante: {self.estoque}")


# Criando objetos (instâncias) da classe
notebook = Produto("Notebook", 3500.00, 5)
mouse = Produto("Mouse", 50.00, 20)

notebook.exibir()
mouse.exibir()

print(f"\n💰 Valor total do notebook em estoque: R$ {notebook.valor_total():.2f}")

notebook.vender(2)
notebook.exibir()

notebook.vender(10)  # vai dar erro de estoque insuficiente
