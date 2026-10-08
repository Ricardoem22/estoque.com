// Busca que ignora acentos e aceita várias palavras ("frango desf" acha "Frango desfiado").
// ligarBusca(id do campo, seletor de cada linha, seletor do grupo que some quando fica vazio, id do aviso)
(function () {
    function limpar(t) { return (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
    window.ligarBusca = function (idCampo, seletorLinha, seletorGrupo, idVazio) {
        var campo = document.getElementById(idCampo);
        if (!campo) return;
        function filtrar() {
            var palavras = limpar(campo.value.trim()).split(/\s+/).filter(Boolean);
            var total = 0;
            document.querySelectorAll(seletorGrupo).forEach(function (grupo) {
                var visiveis = 0;
                grupo.querySelectorAll(seletorLinha).forEach(function (linha) {
                    var texto = limpar(linha.dataset.busca || linha.textContent);
                    var mostra = palavras.every(function (p) { return texto.indexOf(p) !== -1; });
                    linha.style.display = mostra ? "" : "none";
                    if (mostra) visiveis++;
                });
                grupo.style.display = visiveis ? "" : "none";
                total += visiveis;
            });
            var vazio = idVazio && document.getElementById(idVazio);
            if (vazio) vazio.hidden = total > 0;
        }
        campo.addEventListener("input", filtrar);
        campo.addEventListener("search", filtrar);
        if (campo.value) filtrar();
    };
})();
