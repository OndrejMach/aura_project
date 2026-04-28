"""
TTS Engine – převod textu na hlas.

Výchozí engine: edge-tts (Microsoft, zdarma, vysoká kvalita, česky)
Fallback: pyttsx3 (offline, nižší kvalita)
"""

import asyncio
import io
import tempfile
from pathlib import Path
from typing import Optional

from backend.config.settings import Settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class TTSEngine:
    """Převádí text na řeč a přehraje ho."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._engine = None
        self._init_engine()

    def _init_engine(self):
        """Inicializuje TTS engine."""
        engine = self.settings.tts_engine

        if engine == "edge-tts":
            self._init_edge_tts()
        elif engine == "pyttsx3":
            self._init_pyttsx3()
        else:
            self._init_edge_tts()

    def _init_edge_tts(self):
        """Inicializuje Microsoft Edge TTS (online, vysoká kvalita)."""
        try:
            import edge_tts
            self._engine = "edge-tts"
            logger.info(f"✅ Edge TTS inicializován (hlas: {self.settings.tts_voice})")
        except ImportError:
            logger.warning("edge-tts není nainstalován, zkouším pyttsx3...")
            self._init_pyttsx3()

    def _init_pyttsx3(self):
        """Inicializuje pyttsx3 (offline fallback)."""
        try:
            import pyttsx3
            self._pyttsx3_engine = pyttsx3.init()
            self._pyttsx3_engine.setProperty('rate', 175)
            self._engine = "pyttsx3"
            logger.info("✅ pyttsx3 TTS inicializován (offline)")
        except ImportError:
            logger.error("❌ Žádný TTS engine není dostupný!")
            logger.error("   Nainstaluj: pip install edge-tts")
            self._engine = "none"

    async def synthesize(self, text: str) -> Optional[bytes]:
        """
        Převede text na audio.

        Args:
            text: Text k převedení

        Returns:
            MP3/WAV audio data jako bytes
        """
        if not text or self._engine == "none":
            return None

        if self._engine == "edge-tts":
            return await self._synthesize_edge_tts(text)
        elif self._engine == "pyttsx3":
            return await self._synthesize_pyttsx3(text)

        return None

    async def _synthesize_edge_tts(self, text: str) -> Optional[bytes]:
        """Syntéza pomocí Edge TTS."""
        import edge_tts

        communicate = edge_tts.Communicate(
            text=text,
            voice=self.settings.tts_voice,
            rate=self.settings.tts_rate,
            volume=self.settings.tts_volume,
            pitch=self.settings.tts_pitch
        )

        # Shromáždíme audio chunks
        audio_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])

        if audio_chunks:
            return b"".join(audio_chunks)

        return None

    async def _synthesize_pyttsx3(self, text: str) -> Optional[bytes]:
        """Syntéza pomocí pyttsx3 (offline)."""
        loop = asyncio.get_event_loop()

        def _synth():
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            self._pyttsx3_engine.save_to_file(text, tmp_path)
            self._pyttsx3_engine.runAndWait()

            with open(tmp_path, "rb") as f:
                data = f.read()

            Path(tmp_path).unlink()
            return data

        return await loop.run_in_executor(None, _synth)

    async def play(self, audio_data: Optional[bytes]):
        """
        Přehraje audio data.

        Args:
            audio_data: MP3 nebo WAV data
        """
        if not audio_data:
            return

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._play_sync, audio_data)

    def _play_sync(self, audio_data: bytes):
        """Synchronní přehrávání (voláno z thread poolu)."""
        try:
            # Zkusíme pygame (cross-platform)
            import pygame
            import io

            pygame.mixer.init()
            sound = pygame.mixer.Sound(io.BytesIO(audio_data))
            sound.play()

            # Čekáme na dokončení přehrávání
            while pygame.mixer.get_busy():
                pygame.time.wait(100)

        except ImportError:
            # Fallback na playsound
            try:
                import playsound
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp.write(audio_data)
                    tmp_path = tmp.name

                playsound.playsound(tmp_path)
                Path(tmp_path).unlink()

            except ImportError:
                logger.error("Nelze přehrát audio – nainstaluj: pip install pygame")
        except Exception as e:
            logger.error(f"Chyba při přehrávání: {e}")
