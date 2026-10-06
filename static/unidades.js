// Liga o select de insumo ao select de unidade: mostra as medidas que o insumo aceita
// e a prévia de quanto entra no estoque (ex.: 3 saco = 15 kg).
(function () {
    var PESO = {mg: 0.001, g: 1, kg: 1000};
    var VOLUME = {ml: 1, L: 1000, lt: 1000};

    function fixo(q, de, para) {
        if (de === para) return q;
        var grupos = [PESO, VOLUME];
        for (var i = 0; i < grupos.length; i++) {
            if (de in grupos[i] && para in grupos[i]) return q * grupos[i][de] / grupos[i][para];
        }
        return null;
    }

    function converter(q, de, para, conv) {
        var direto = fixo(q, de, para);
        if (direto !== null) return direto;
        if (conv[de]) return fixo(q * conv[de][0], conv[de][1], para);
        return null;
    }

    function numero(texto) {
        var v = parseFloat(String(texto || "").replace(/\./g, "").replace(",", "."));
        if (String(texto || "").indexOf(",") === -1) v = parseFloat(String(texto || ""));
        return isNaN(v) ? null : v;
    }

    function formatar(v) {
        return (Math.round(v * 1000) / 1000).toString().replace(".", ",");
    }

    window.ligarUnidades = function (idInsumo, idUnidade, idQuantidade, idPrevia) {
        var insumo = document.getElementById(idInsumo);
        var unidade = document.getElementById(idUnidade);
        var quantidade = document.getElementById(idQuantidade);
        var previa = document.getElementById(idPrevia);
        if (!insumo || !unidade) return;

        function opcaoAtual() { return insumo.selectedOptions[0]; }

        function atualizarPrevia() {
            if (!previa) return;
            var op = opcaoAtual();
            if (!op || !op.dataset.unidade) { previa.textContent = ""; return; }
            var base = op.dataset.unidade;
            var conv = JSON.parse(op.dataset.conv || "{}");
            var q = numero(quantidade && quantidade.value);
            var u = unidade.value;
            if (u === base) { previa.textContent = ""; previa.className = "previa-unidade"; return; }
            var r = converter(q === null ? 1 : q, u, base, conv);
            if (r === null) {
                previa.textContent = "⚠️ " + u + " não converte para " + base + ". Cadastre a medida na ficha do insumo.";
                previa.className = "previa-unidade aviso";
            } else {
                previa.textContent = (q === null ? "1 " + u : formatar(q) + " " + u) + " = " + formatar(r) + " " + base + " no estoque";
                previa.className = "previa-unidade";
            }
        }

        function trocarInsumo(manterUnidade) {
            var op = opcaoAtual();
            if (!op || !op.dataset.unidades) { atualizarPrevia(); return; }
            var escolhida = manterUnidade ? unidade.value : op.dataset.unidade;
            var lista = JSON.parse(op.dataset.unidades);
            unidade.innerHTML = "";
            lista.forEach(function (u) {
                var o = document.createElement("option");
                o.value = u; o.textContent = u;
                if (u === escolhida) o.selected = true;
                unidade.appendChild(o);
            });
            atualizarPrevia();
        }

        insumo.addEventListener("change", function () { trocarInsumo(false); });
        unidade.addEventListener("change", atualizarPrevia);
        if (quantidade) quantidade.addEventListener("input", atualizarPrevia);
        trocarInsumo(true);
    };
})();
