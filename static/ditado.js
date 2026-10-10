// Ditado em qualquer campo: ao tocar num campo de texto aparece um 🎙️ no canto dele. Tocou, falou, o texto
// entra no campo. Campos de quantidade recebem o número ("dois e meio" → 2,5).
// Sem reconhecimento de voz no navegador (iPhone fora do Safari), o 🎤 do próprio teclado faz o ditado.
(function () {
    var Reconhecer = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Reconhecer) return;
    var NUMEROS = {zero: 0, um: 1, uma: 1, dois: 2, duas: 2, tres: 3, quatro: 4, cinco: 5, seis: 6, sete: 7, oito: 8,
        nove: 9, dez: 10, onze: 11, doze: 12, treze: 13, quatorze: 14, catorze: 14, quinze: 15, dezesseis: 16,
        dezessete: 17, dezoito: 18, dezenove: 19, vinte: 20, trinta: 30, quarenta: 40, cinquenta: 50, sessenta: 60,
        setenta: 70, oitenta: 80, noventa: 90, cem: 100, cento: 100, duzentos: 200, trezentos: 300, quinhentos: 500,
        mil: 1000};
    var TIPOS = {text: 1, search: 1, email: 0, "": 1};

    function semAcento(t) { return t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }
    function paraNumero(fala) {
        var t = semAcento(fala).replace(/(\d)\s*[.,]\s*(\d)/g, "$1,$2");
        var digitos = t.match(/\d+(,\d+)?/);
        if (digitos) {
            var n = digitos[0];
            if (/\be meio\b|\be meia\b/.test(t)) n = String(parseFloat(n.replace(",", ".")) + 0.5).replace(".", ",");
            return n;
        }
        var inteiro = 0, decimais = "", depois = false, achou = false;
        t.split(/\s+/).forEach(function (p) {
            if (p === "virgula" || p === "ponto") { depois = true; return; }
            if (p === "meio" || p === "meia") { inteiro += 0.5; achou = true; return; }
            if (p in NUMEROS) {
                achou = true;
                if (depois) decimais += String(NUMEROS[p]);
                else if (p === "mil") inteiro = (inteiro || 1) * 1000;
                else inteiro += NUMEROS[p];
            }
        });
        if (!achou) return fala.trim();
        return (String(inteiro) + (decimais ? "." + decimais : "")).replace(".", ",");
    }
    function serve(el) {
        if (!el || el.disabled || el.readOnly || el.id === "voz-texto" || el.closest("[data-sem-ditado]")) return false;
        if (el.tagName === "TEXTAREA") return true;
        return el.tagName === "INPUT" && (TIPOS[(el.getAttribute("type") || "").toLowerCase()] === 1);
    }

    var botao = document.createElement("button");
    botao.type = "button"; botao.className = "ditar-botao nao-imprimir"; botao.textContent = "🎙️";
    botao.setAttribute("aria-label", "Ditar neste campo"); botao.title = "Ditar neste campo"; botao.hidden = true;
    document.body.appendChild(botao);
    var campo = null, rec = null;

    function posicionar() {
        if (!campo) return;
        var r = campo.getBoundingClientRect(), tam = Math.min(34, Math.max(26, r.height - 6));
        botao.style.width = botao.style.height = tam + "px";
        botao.style.top = (r.top + (r.height - tam) / 2) + "px";
        botao.style.left = (r.right - tam - 4) + "px";
        botao.hidden = r.bottom < 0 || r.top > window.innerHeight;
    }
    function esconder() {
        if (rec) return;
        if (campo) campo.classList.remove("com-ditado");
        campo = null; botao.hidden = true;
    }
    document.addEventListener("focusin", function (e) {
        if (e.target === botao) return;
        if (!serve(e.target)) { esconder(); return; }
        if (rec) { try { rec.stop(); } catch (x) {} }
        if (campo) campo.classList.remove("com-ditado");
        campo = e.target; campo.classList.add("com-ditado"); posicionar();
    });
    document.addEventListener("focusout", function () {
        setTimeout(function () { if (document.activeElement !== campo && document.activeElement !== botao) esconder(); }, 150);
    });
    window.addEventListener("scroll", posicionar, true);
    window.addEventListener("resize", posicionar);
    // Tocar no 🎙️ não tira o foco do campo
    botao.addEventListener("pointerdown", function (e) { e.preventDefault(); });
    botao.addEventListener("mousedown", function (e) { e.preventDefault(); });

    botao.addEventListener("click", function () {
        if (!campo) return;
        if (rec) { try { rec.stop(); } catch (x) {} return; }
        var alvo = campo, numerico = /decimal|numeric/.test(alvo.getAttribute("inputmode") || "");
        var antes = alvo.value, atual = new Reconhecer();
        // Campo de lista (ex.: itens da refeição): continua ouvindo nas pausas entre um item e outro,
        // até tocar no 🎙️ de novo ou ficar um tempo em silêncio
        var continuo = alvo.hasAttribute("data-ditado-continuo");
        rec = atual;
        atual.lang = "pt-BR"; atual.interimResults = true; atual.maxAlternatives = 1;
        atual.continuous = continuo;
        function escrever(fala) {
            if (numerico) alvo.value = paraNumero(fala);
            else alvo.value = (antes && !/\s$/.test(antes) ? antes + " " : antes) + fala.trim();
            alvo.dispatchEvent(new Event("input", {bubbles: true}));
        }
        atual.onstart = function () { botao.classList.add("ouvindo"); };
        atual.onresult = function (ev) {
            var ultimo = ev.results[ev.results.length - 1];
            if (continuo) {
                // Junta todos os trechos; o Chrome do Android às vezes repete o mesmo trecho final
                var partes = [];
                for (var i = 0; i < ev.results.length; i++) {
                    var t = ev.results[i][0].transcript.trim();
                    if (t && partes[partes.length - 1] !== t) partes.push(t);
                }
                escrever(partes.join(", "));
                return;
            }
            escrever(ultimo[0].transcript);
            if (ultimo.isFinal) { try { atual.stop(); } catch (x) {} }
        };
        atual.onerror = function (ev) {
            if (ev.error === "not-allowed" || ev.error === "service-not-allowed")
                alert("O microfone está bloqueado para este site. Toque no cadeado ao lado do endereço, em Microfone escolha Permitir e recarregue a página.");
        };
        atual.onend = function () {
            botao.classList.remove("ouvindo"); rec = null;
            alvo.dispatchEvent(new Event("change", {bubbles: true}));
            if (document.activeElement !== alvo) esconder(); else posicionar();
        };
        try { atual.start(); } catch (x) { rec = null; botao.classList.remove("ouvindo"); }
    });
})();
