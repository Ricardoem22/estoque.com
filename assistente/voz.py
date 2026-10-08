"""Voz falada usando as vozes do Windows (funciona sem internet).

No Windows fala direto pelo SAPI (o mesmo motor do Narrador). Se não der,
usa o PowerShell, que existe em todo Windows. Fora do Windows usa o pyttsx3.
"""
import platform
import re
import subprocess


def limpar(texto: str) -> str:
    """Tira marcações (negrito, títulos, links) que soariam estranhas faladas."""
    texto = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texto)
    texto = re.sub(r"[*_#`>|]", "", texto)
    return re.sub(r"\s+", " ", texto).strip()


class Voz:
    def __init__(self, preferida: str = "Daniel", ativa: bool = True):
        self.preferida = preferida
        self.ativa = ativa
        self.erro = ""
        self.nome_voz = ""
        self._sapi = None
        self._pyttsx3 = None
        self._powershell = False
        if not ativa:
            return
        if platform.system() == "Windows":
            self._iniciar_sapi() or self._iniciar_powershell()
        else:
            self._iniciar_pyttsx3()
        if not (self._sapi or self._pyttsx3 or self._powershell):
            self.ativa = False

    # ---------- motores ----------

    def _iniciar_sapi(self) -> bool:
        try:
            import win32com.client

            self._sapi = win32com.client.Dispatch("SAPI.SpVoice")
            vozes = [self._sapi.GetVoices().Item(i) for i in range(self._sapi.GetVoices().Count)]
            nomes = [v.GetDescription() for v in vozes]
            escolhida = self._escolher(nomes)
            if escolhida is not None:
                self._sapi.Voice = vozes[escolhida]
            self.nome_voz = self._sapi.Voice.GetDescription()
            return True
        except Exception as e:
            self._sapi = None
            self.erro = f"SAPI: {e}"
            return False

    def _iniciar_powershell(self) -> bool:
        self._powershell = True
        self.nome_voz = "voz do Windows (via PowerShell)"
        return True

    def _iniciar_pyttsx3(self) -> bool:
        try:
            import pyttsx3

            self._pyttsx3 = pyttsx3.init()
            vozes = self._pyttsx3.getProperty("voices")
            escolhida = self._escolher([f"{v.name} {v.id} {getattr(v, 'languages', '')}" for v in vozes])
            if escolhida is not None:
                self._pyttsx3.setProperty("voice", vozes[escolhida].id)
            return True
        except Exception as e:
            self.erro = f"pyttsx3: {e}"
            return False

    def _escolher(self, nomes: list[str]) -> int | None:
        """Prefere a voz pedida; senão, qualquer voz em português."""
        baixo = [n.lower() for n in nomes]
        for i, n in enumerate(baixo):
            if self.preferida.lower() in n:
                return i
        for i, n in enumerate(baixo):
            if "portug" in n or "pt-br" in n or "brazil" in n or "brasil" in n:
                return i
        return None

    def vozes(self) -> list[str]:
        if self._sapi:
            v = self._sapi.GetVoices()
            return [v.Item(i).GetDescription() for i in range(v.Count)]
        return []

    # ---------- falar ----------

    def falar(self, texto: str) -> None:
        if not self.ativa:
            return
        texto = limpar(texto)
        if not texto:
            return
        try:
            if self._sapi:
                self._sapi.Speak(texto)
            elif self._powershell:
                self._falar_powershell(texto)
            elif self._pyttsx3:
                self._pyttsx3.say(texto)
                self._pyttsx3.runAndWait()
        except Exception as e:
            print(f"[aviso] Não consegui falar: {e}")
            if self._sapi:  # tenta pelo PowerShell daqui em diante
                self._sapi = None
                self._powershell = True

    def _falar_powershell(self, texto: str) -> None:
        texto = texto.replace("'", "''")
        voz = self.preferida.replace("'", "''")
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$v = $s.GetInstalledVoices() | Where-Object {{ $_.VoiceInfo.Name -like '*{voz}*' }} | Select-Object -First 1; "
            "if (-not $v) { $v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'pt-BR' } "
            "| Select-Object -First 1 }; "
            "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }; "
            f"$s.Speak('{texto}')"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
