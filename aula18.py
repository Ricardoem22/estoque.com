class Produto:
    def __init__(self, nome, preco, estoque):
        self.nome = nome
        self.preco = preco
        self.estoque = estoque

    def exibir(self):
        print(f"📦 {self.nome} - R$ {self.preco:.2f} - {self.estoque} unidades")

    def valor_total(self):
        return self.preco * self.estoque


class ProdutoEletronico(Produto):
    def __init__(self, nome, preco, estoque, garantia_meses):
        super().__init__(nome, preco, estoque)  # chama o __init__ da classe mãe
        self.garantia_meses = garantia_meses

    def exibir(self):  # sobrescrevendo o método da classe mãe
        super().exibir()
        print(f"   🛡️ Garantia: {self.garantia_meses} meses")


class ProdutoAlimenticio(Produto):
    def __init__(self, nome, preco, estoque, validade):
        super().__init__(nome, preco, estoque)
        self.validade = validade

    def exibir(self):
        super().exibir()
        print(f"   📅 Validade: {self.validade}")


# Criando objetos das classes filhas
notebook = ProdutoEletronico("Notebook", 3500.00, 5, garantia_meses=12)
arroz = ProdutoAlimenticio("Arroz 5kg", 25.00, 50, validade="12/2026")

notebook.exibir()
arroz.exibir()

print(f"\n💰 Valor total notebook: R$ {notebook.valor_total():.2f}")
print(f"💰 Valor total arroz: R$ {arroz.valor_total():.2f}")
