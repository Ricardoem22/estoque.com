import json
import os

class Produto:
    def __init__(self, nome, preco, estoque):
        self.nome = nome
        self.preco = preco
        self.estoque = estoque

    def exibir(self):
        print(f"📦 {self.nome} - R$ {self.preco:.2f} - {self.estoque} unidades")

    def valor_total(self):
        return self.preco * self.estoque

    def to_dict(self):
        """Converte o objeto em dicionário (para salvar em JSON)"""
        return {"nome": self.nome, "preco": self.preco, "estoque": self.estoque}

    @classmethod
    def from_dict(cls, dados):
        """Cria um objeto Produto a partir de um dicionário"""
        return cls(dados["nome"], dados["preco"], dados["estoque"])


class Estoque:
    def __init__(self, arquivo="estoque.json"):
        self.produtos = []
        self.arquivo = arquivo
        self.carregar()

    def adicionar_produto(self, produto):
        self.produtos.append(produto)
        print(f"➕ {produto.nome} adicionado ao estoque")
        self.salvar()

    def listar_produtos(self):
        print("\n📋 --- ESTOQUE ATUAL ---")
        for produto in self.produtos:
            produto.exibir()

    def salvar(self):
        """Salva a lista de produtos no arquivo JSON"""
        dados = [produto.to_dict() for produto in self.produtos]
        with open(self.arquivo, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)
        print(f"💾 Estoque salvo em {self.arquivo}")

    def carregar(self):
        """Carrega os produtos do arquivo JSON, se existir"""
        if os.path.exists(self.arquivo):
            with open(self.arquivo, "r", encoding="utf-8") as f:
                dados = json.load(f)
                self.produtos = [Produto.from_dict(d) for d in dados]
            print(f"📂 Estoque carregado de {self.arquivo} ({len(self.produtos)} produtos)")
        else:
            print("📂 Nenhum arquivo de estoque encontrado. Começando vazio.")


# Simulando o uso
loja = Estoque()

loja.listar_produtos()

# Só adiciona se o estoque estiver vazio (evita duplicar a cada execução)
if not loja.produtos:
    loja.adicionar_produto(Produto("Notebook", 3500.00, 5))
    loja.adicionar_produto(Produto("Mouse", 50.00, 20))

loja.listar_produtos()
