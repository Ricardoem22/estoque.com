"""Voz falada usando as vozes do Windows (funciona sem internet)."""


class Voz:
    def __init__(self, preferida: str = "Daniel", ativa: bool = True):
        self.motor = None
        self.ativa = ativa
        if not ativa:
            return
        try:
            import pyttsx3
            self.motor = pyttsx3.init()
        except Exception:  # sem pyttsx3 ou sem saída de áudio
            self.ativa = False
            return
        self._escolher(preferida)

    def _escolher(self, preferida: str) -> None:
        vozes = self.motor.getProperty("voices")

        def idioma(v):
            return (str(getattr(v, "languages", "")) + v.id + v.name).lower()

        candidatas = (
            [v for v in vozes if preferida.lower() in v.name.lower()]
            or [v for v in vozes if "pt" in idioma(v) and "male" in str(getattr(v, "gender", "")).lower()]
            or [v for v in vozes if "pt-br" in idioma(v) or "portuguese" in idioma(v)]
        )
        if candidatas:
            self.motor.setProperty("voice", candidatas[0].id)

    def falar(self, texto: str) -> None:
        if self.ativa and self.motor:
            self.motor.say(texto)
            self.motor.runAndWait()
