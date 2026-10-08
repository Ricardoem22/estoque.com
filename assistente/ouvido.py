"""Ouvir pelo microfone e transformar a fala em texto, sem internet (faster-whisper)."""
import math
import os
import threading

# Aviso inofensivo do Windows sobre atalhos de arquivo no cache do modelo de voz
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

TAXA = 16000          # amostras por segundo
BLOCO = 0.1           # segundos por bloco lido do microfone


class DetectorDeFala:
    """Decide quando a pessoa começou e terminou de falar, pelo volume de cada bloco."""

    def __init__(self, ruido: float, espera_max=8.0, silencio_fim=1.2, fala_max=20.0):
        self.limiar = max(0.004, ruido * 2.5)
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
    def __init__(self, tamanho: str = "small", idioma: str = "pt", dispositivo: str = ""):
        self.tamanho = tamanho
        self.dispositivo = int(dispositivo) if dispositivo.strip().isdigit() else (dispositivo.strip() or None)
        self.motivo = ""  # por que a última tentativa não deu certo
        self.idioma = None if idioma == "auto" else idioma
        self._modelo = None
        self._trava = threading.Lock()
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
        with self._trava:
            return self._carregar_sem_trava()

    def aquecer(self) -> None:
        """Carrega o reconhecimento de voz em segundo plano, para a primeira fala ser rápida."""
        if self.disponivel:
            threading.Thread(target=self._carregar, daemon=True).start()

    def _carregar_sem_trava(self):
        if self._modelo is None:
            from faster_whisper import WhisperModel

            self._modelo = WhisperModel(self.tamanho, device="cpu", compute_type="int8")
        return self._modelo

    def microfones(self) -> str:
        import sounddevice as sd

        padrao = sd.default.device[0]
        linhas = [f"{'*' if i == padrao else ' '} {i}: {d['name']}"
                  for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
        return "\n".join(linhas) or "Nenhum microfone encontrado."

    def medir(self, segundos: float = 4.0) -> None:
        """Mostra uma barra com o volume do microfone, para testar."""
        import sounddevice as sd

        n = int(TAXA * BLOCO)
        with sd.InputStream(samplerate=TAXA, channels=1, dtype="float32", blocksize=n,
                            device=self.dispositivo) as mic:
            for _ in range(int(segundos / BLOCO)):
                v = volume(mic.read(n)[0][:, 0])
                print(f"\r  volume {v:6.3f} |{'#' * min(50, int(v * 500)):<50}|", end="", flush=True)
        print()

    def gravar(self):
        import numpy as np
        import sounddevice as sd

        n = int(TAXA * BLOCO)
        partes = []
        with sd.InputStream(samplerate=TAXA, channels=1, dtype="float32", blocksize=n,
                            device=self.dispositivo) as mic:
            ruido = sum(volume(mic.read(n)[0][:, 0]) for _ in range(3)) / 3  # 0,3 s de silêncio
            detector = DetectorDeFala(ruido)
            pico = 0.0
            print("🎤 Pode falar...")
            while True:
                bloco = mic.read(n)[0][:, 0].copy()
                v = volume(bloco)
                pico = max(pico, v)
                estado = detector.bloco(v)
                if estado == "nada":
                    self.motivo = (f"Não ouvi voz: o volume máximo foi {pico:.3f} e preciso de {detector.limiar:.3f}. "
                                   "Fale mais perto do microfone ou digite /microfone para testar.")
                    return None
                if estado != "esperando":
                    partes.append(bloco)
                if estado == "fim":
                    return np.concatenate(partes)

    def ouvir(self) -> str | None:
        """Grava uma frase e devolve o texto (ou None, com o motivo em self.motivo)."""
        self.motivo = ""
        modelo = self._carregar()
        try:
            audio = self.gravar()
        except Exception as e:  # microfone ausente, bloqueado pelo Windows etc.
            self.motivo = (f"Não consegui usar o microfone ({e}). Veja em Configurações › Privacidade › "
                           "Microfone se aplicativos da área de trabalho têm permissão.")
            return None
        if audio is None:
            return None
        trechos, _ = modelo.transcribe(audio, language=self.idioma, vad_filter=True,
                                     beam_size=1)  # bem mais rápido, quase sem perder precisão
        texto = " ".join(t.text.strip() for t in trechos).strip()
        if not texto:
            self.motivo = "Ouvi um som, mas não reconheci palavras. Tente falar de novo, um pouco mais devagar."
        return texto or None
