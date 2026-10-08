"""Ouvir pelo microfone e transformar a fala em texto, sem internet (faster-whisper)."""
import math

TAXA = 16000          # amostras por segundo
BLOCO = 0.1           # segundos por bloco lido do microfone


class DetectorDeFala:
    """Decide quando a pessoa começou e terminou de falar, pelo volume de cada bloco."""

    def __init__(self, ruido: float, espera_max=8.0, silencio_fim=1.2, fala_max=20.0):
        self.limiar = max(0.01, ruido * 3)
        self.blocos_espera = int(espera_max / BLOCO)
        self.blocos_silencio = int(silencio_fim / BLOCO)
        self.blocos_max = int(fala_max / BLOCO)
        self.falando = False
        self.esperou = 0
        self.silencio = 0
        self.gravados = 0

    def bloco(self, volume: float) -> str:
        """Devolve 'esperando', 'gravando', 'fim' ou 'nada' (ninguém falou)."""
        if not self.falando:
            if volume >= self.limiar:
                self.falando = True
            else:
                self.esperou += 1
                return "nada" if self.esperou >= self.blocos_espera else "esperando"
        self.gravados += 1
        self.silencio = 0 if volume >= self.limiar else self.silencio + 1
        if self.silencio >= self.blocos_silencio or self.gravados >= self.blocos_max:
            return "fim"
        return "gravando"


def volume(bloco) -> float:
    return math.sqrt(float((bloco ** 2).mean()))


class Ouvido:
    def __init__(self, tamanho: str = "small", idioma: str = "pt"):
        self.tamanho = tamanho
        self.idioma = None if idioma == "auto" else idioma
        self._modelo = None
        self.erro = None
        try:
            import faster_whisper  # noqa: F401
            import numpy  # noqa: F401
            import sounddevice  # noqa: F401
        except Exception:  # pacote faltando ou sem driver de áudio
            self.erro = "Para falar comigo, instale: pip install faster-whisper sounddevice"

    @property
    def disponivel(self) -> bool:
        return self.erro is None

    def _carregar(self):
        if self._modelo is None:
            from faster_whisper import WhisperModel

            print(f"(carregando o reconhecimento de voz '{self.tamanho}'; "
                  "na primeira vez ele baixa o modelo, aguarde...)")
            self._modelo = WhisperModel(self.tamanho, device="cpu", compute_type="int8")
        return self._modelo

    def gravar(self):
        import numpy as np
        import sounddevice as sd

        n = int(TAXA * BLOCO)
        partes = []
        with sd.InputStream(samplerate=TAXA, channels=1, dtype="float32", blocksize=n) as mic:
            ruido = sum(volume(mic.read(n)[0][:, 0]) for _ in range(3)) / 3  # 0,3 s de silêncio
            detector = DetectorDeFala(ruido)
            print("🎤 Pode falar...")
            while True:
                bloco = mic.read(n)[0][:, 0].copy()
                estado = detector.bloco(volume(bloco))
                if estado == "nada":
                    return None
                if estado != "esperando":
                    partes.append(bloco)
                if estado == "fim":
                    return np.concatenate(partes)

    def ouvir(self) -> str | None:
        """Grava uma frase e devolve o texto (ou None se não entendeu nada)."""
        modelo = self._carregar()
        try:
            audio = self.gravar()
        except Exception as e:  # microfone ausente, bloqueado pelo Windows etc.
            print(f"[aviso] Não consegui usar o microfone: {e}")
            return None
        if audio is None:
            return None
        trechos, _ = modelo.transcribe(audio, language=self.idioma, vad_filter=True)
        texto = " ".join(t.text.strip() for t in trechos).strip()
        return texto or None
