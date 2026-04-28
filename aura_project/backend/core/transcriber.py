"""
Transcriber – převod řeči na text pomocí OpenAI Whisper.

Používá faster-whisper (optimalizovaná verze) pro rychlejší přepis.
Funguje 100% offline, bez internetu.
"""

import asyncio
import io
import tempfile
from pathlib import Path
from typing import Optional

from backend.config.settings import Settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class Transcriber:
    """
    Převádí audio na text pomocí Whisper modelu.
    Automaticky volí mezi faster-whisper a openai-whisper.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._model = None
        self._engine = None
        self._load_model()

    def _load_model(self):
        """Načte Whisper model – preferuje faster-whisper."""
        logger.info(f"⏳ Načítám Whisper model '{self.settings.whisper_model}'...")

        # Zkusíme faster-whisper (rychlejší, méně RAM)
        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.settings.whisper_model,
                device=self.settings.whisper_device,
                compute_type=self.settings.whisper_compute_type
            )
            self._engine = "faster-whisper"
            logger.info(f"✅ faster-whisper model načten ({self.settings.whisper_model})")
            return

        except ImportError:
            logger.warning("faster-whisper není nainstalován, zkouším openai-whisper...")

        # Fallback na openai-whisper
        try:
            import whisper

            self._model = whisper.load_model(
                self.settings.whisper_model,
                device=self.settings.whisper_device
            )
            self._engine = "openai-whisper"
            logger.info(f"✅ openai-whisper model načten ({self.settings.whisper_model})")

        except ImportError:
            raise RuntimeError(
                "❌ Whisper není nainstalován!\n"
                "   Nainstaluj: pip install faster-whisper\n"
                "   Nebo:       pip install openai-whisper"
            )

    async def transcribe(self, audio_data: bytes) -> Optional[str]:
        """
        Přepíše audio data na text.

        Args:
            audio_data: WAV audio data jako bytes

        Returns:
            Přepsaný text nebo None při chybě
        """
        if not audio_data:
            return None

        loop = asyncio.get_event_loop()

        # Spustíme přepis v thread poolu (CPU náročná operace)
        result = await loop.run_in_executor(
            None,
            self._transcribe_sync,
            audio_data
        )

        return result

    def _transcribe_sync(self, audio_data: bytes) -> Optional[str]:
        """Synchronní přepis volaný z thread poolu."""
        try:
            # Uložíme do dočasného souboru (Whisper preferuje soubory)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_data)
                tmp_path = tmp.name

            if self._engine == "faster-whisper":
                return self._transcribe_faster_whisper(tmp_path)
            else:
                return self._transcribe_openai_whisper(tmp_path)

        except Exception as e:
            logger.error(f"Chyba při přepisu: {e}", exc_info=True)
            return None
        finally:
            # Smažeme dočasný soubor
            try:
                Path(tmp_path).unlink()
            except Exception:
                pass

    def _transcribe_faster_whisper(self, audio_path: str) -> str:
        """Přepis pomocí faster-whisper."""
        segments, info = self._model.transcribe(
            audio_path,
            language=self.settings.whisper_language if self.settings.whisper_language != "auto" else None,
            beam_size=5,
            vad_filter=True,       # Filtruje ticho
            vad_parameters=dict(
                min_silence_duration_ms=500
            )
        )

        # Spojíme všechny segmenty
        text = " ".join(segment.text.strip() for segment in segments)
        return text.strip()

    def _transcribe_openai_whisper(self, audio_path: str) -> str:
        """Přepis pomocí openai-whisper."""
        result = self._model.transcribe(
            audio_path,
            language=self.settings.whisper_language if self.settings.whisper_language != "auto" else None,
            fp16=False  # Bezpečnější pro CPU
        )
        return result["text"].strip()
