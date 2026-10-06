# insumos_iniciais.py
# Lista de insumos da planilha de contagem do Restaurante La Barca.
# Usada para popular o banco na primeira execução.

CATEGORIAS = [
    ("🥩 Carnes, Embutidos e Pescados", "kg", [
        "Bacon", "Calabresa", "Camarão", "Carne moída", "Carne seca",
        "Entrecot", "Filé mignon", "Frango", "Lombo", "Lula", "Pepperoni",
        "Picanha", "Presunto", "Salame", "Salmão", "Tilápia",
    ]),
    ("🧀 Laticínios e Derivados", "un", [
        "Catupiry", "Cheddar", "Creme de leite", "Gorgonzola", "Leite",
        "Leite condensado", "Mussarela", "Parmesão", "Provolone", "Sorvete",
    ]),
    ("🥬 Hortifrúti (Verduras, Legumes e Frutas)", "kg", [
        "Abacaxi", "Alface", "Alho", "Alho poró", "Banana", "Batata",
        "Brócolis", "Cebola", "Cebolinha", "Figo", "Hortelã", "Laranja",
        "Mamão", "Manjericão", "Maracujá", "Milho", "Morango", "Ovos",
        "Palmito", "Pêssego", "Pimenta", "Rúcula", "Salsa", "Tomate", "Uva",
    ]),
    ("🌾 Grãos, Massas, Pães e Farináceos", "kg", [
        "Aipim", "Arroz", "Ervilha", "Farinha", "Farofa", "Feijão",
        "Fermento", "Fubá", "Massa", "Pão", "Panko",
    ]),
    ("🏺 Condimentos, Óleos e Enlatados", "un", [
        "Alcaparras", "Azeite de oliva", "Azeitona", "Canela", "Leite de coco",
        "Maionese", "Molho barbecue", "Molho madeira", "Óleo", "Orégano",
        "Sal", "Vinagre",
    ]),
    ("🍫 Doces e Chocolates", "un", [
        "Chocolate", "Geleia", "Kit Kat", "Ouro Branco", "Sonho de Valsa",
    ]),
    ("🍷 Bebidas e Bar", "un", [
        "Açúcar", "Água", "Cachaça", "Café", "Campari", "Cerveja", "Chopp",
        "Cointreau", "Gelo", "Gin", "Jägermeister", "Licor", "Negroni",
        "Refrigerante", "Rum", "Steinhaeger", "Tequila", "Vermute", "Vinho",
        "Vodka", "Whisky", "Xarope",
    ]),
]

# Uma lista só de medidas para o app inteiro
from unidades import UNIDADES_COMUNS  # noqa: E402
UNIDADES = UNIDADES_COMUNS
