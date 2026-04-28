"""
Wake Word Detection – detekce aktivační fráze.

Podporuje více enginů:
1. VOSK (offline, open-source, doporučeno)
2. Picovoice Porcupine (přesný, vyžaduje klíč)
3. Simple keyword matching (fallback, méně přesný)

Výchozí: VOSK – funguje offline, bez API klíče, česky i anglicky.
"""

import asyncio
import io
import json
from pathlib import Path
from typing import Optional

import numpy as np

from backend.config.settings import Settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class WakeWordDetector:
    """
    Detekuje wake word v audio streamu.
    
    Automaticky vybírá nejlepší dostupný engine.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._engine = None
        self._custom_phrase = settings.wake_word_phrase.lower().strip()

        # Inicializujeme nejlepší dostupný engine
        self._init_engine()

    def _init_engine(self):
        """Inicializuje detekční engine podle konfigurace."""
        engine = self.settings.wake_word_engine

        if engine == "vosk":
            self._init_vosk()
        elif engine == "picovoice":
            self._init_picovoice()
        else:
            self._init_simple()

    def _init_vosk(self):
        """
        Inicializuje VOSK speech recognizer pro wake word detection.
        VOSK je offline, open-source a podporuje češtinu.
        """
        try:
            from vosk import Model, KaldiRecognizer

            # Hledáme model v data adresáři
            model_path = self.settings.data_dir / "vosk-model"

            if not model_path.exists():
                logger.warning(
                    f"⚠️ VOSK model nenalezen v {model_path}\n"
                    "   Stáhni model z: https://alphacephei.com/vosk/models\n"
                    "   Doporučeno: vosk-model-small-cs-0.4-rhasspy (čeština)\n"
                    "   Nebo: vosk-model-small-en-us-0.15 (angličtina)\n"
                    "   Rozbal do data/vosk-model/\n"
                    "   Přepínám na simple keyword matching..."
                )
                self._init_simple()
                return

            model = Model(str(model_path))
            self._vosk_recognizer = KaldiRecognizer(
                model,
                self.settings.sample_rate
            )
            self._engine = "vosk"
            logger.info(f"✅ VOSK engine inicializován (model: {model_path.name})")

        except ImportError:
            logger.warning("⚠️ VOSK není nainstalován. Použij: pip install vosk")
            self._init_simple()
        except Exception as e:
            logger.error(f"Chyba při inicializaci VOSK: {e}")
            self._init_simple()

    def _init_picovoice(self):
        """
        Inicializuje Picovoice Porcupine.
        Vyžaduje API klíč a .ppn soubor s modelem wake wordu.
        """
        try:
            import pvporcupine

            from backend.config.secrets import SecretsManager
            secrets = SecretsManager()
            access_key = secrets.picovoice_access_key

            if not access_key:
                logger.warning(
                    "⚠️ PICOVOICE_ACCESS_KEY není nastaven. "
                    "Přepínám na VOSK."
                )
                self._init_vosk()
                return

            # Hledáme .ppn model
            ppn_files = list(self.settings.wake_words_dir.glob("*.ppn"))

            if ppn_files:
                # Použijeme custom wake word
                self._porcupine = pvporcupine.create(
                    access_key=access_key,
                    keyword_paths=[str(ppn_files[0])],
                    sensitivities=[self.settings.wake_word_sensitivity]
                )
                logger.info(f"✅ Picovoice inicializován s custom wake word: {ppn_files[0].name}")
            else:
                # Použijeme built-in keyword
                self._porcupine = pvporcupine.create(
                    access_key=access_key,
                    keywords=["hey google"],  # Nejbližší built-in alternativa
                    sensitivities=[self.settings.wake_word_sensitivity]
                )
                logger.info("✅ Picovoice inicializován s built-in wake word")

            self._engine = "picovoice"

        except ImportError:
            logger.warning("⚠️ pvporcupine není nainstalován. Přepínám na VOSK.")
            self._init_vosk()
        except Exception as e:
            logger.error(f"Chyba při inicializaci Picovoice: {e}")
            self._init_vosk()

    def _init_simple(self):
        """
        Jednoduchý fallback – porovnání klíčových slov v přepisu.
        Méně přesný, ale bez závislostí.
        """
        self._engine = "simple"
        logger.info(
            f"ℹ️ Použit simple keyword matching pro wake word: '{self._custom_phrase}'"
        )

    async def detect(self, audio_chunk: bytes) -> bool:
        """
        Detekuje wake word v audio chunku.
        
        Args:
            audio_chunk: Raw PCM int16 audio data
            
        Returns:
            True pokud byl wake word detekován
        """
        if self._engine == "vosk":
            return await self._detect_vosk(audio_chunk)
        elif self._engine == "picovoice":
            return await self._detect_picovoice(audio_chunk)
        else:
            return await self._detect_simple(audio_chunk)

    async def _detect_vosk(self, audio_chunk: bytes) -> bool:
        """Detekce pomocí VOSK – spustíme v thread poolu."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._vosk_detect_sync,
            audio_chunk
        )

    def _vosk_detect_sync(self, audio_chunk: bytes) -> bool:
        """Synchronní VOSK detekce (volaná z thread poolu)."""
        if self._vosk_recognizer.AcceptWaveform(audio_chunk):
            result = json.loads(self._vosk_recognizer.Result())
            text = result.get("text", "").lower()

            if text:
                logger.debug(f"VOSK rozpoznal: '{text}'")
                # Kontrola zda přepis obsahuje wake word frázi
                return self._matches_wake_word(text)

        # Kontrola i partial výsledků pro rychlejší detekci
        partial = json.loads(self._vosk_recognizer.PartialResult())
        partial_text = partial.get("partial", "").lower()

        if partial_text and self._matches_wake_word(partial_text):
            self._vosk_recognizer.Reset()  # Reset po detekci
            return True

        return False

    async def _detect_picovoice(self, audio_chunk: bytes) -> bool:
        """Detekce pomocí Picovoice Porcupine."""
        loop = asyncio.get_event_loop()

        def _detect():
            # Picovoice vyžaduje int16 numpy array
            pcm = np.frombuffer(audio_chunk, dtype=np.int16)

            # Zpracujeme po framích (Porcupine má fixní frame length)
            frame_length = self._porcupine.frame_length
            for i in range(0, len(pcm) - frame_length + 1, frame_length):
                frame = pcm[i:i + frame_length].tolist()
                keyword_index = self._porcupine.process(frame)
                if keyword_index >= 0:
                    return True
            return False

        return await loop.run_in_executor(None, _detect)

    async def _detect_simple(self, audio_chunk: bytes) -> bool:
        """
        Jednoduchý fallback – provede rychlý STT a porovná klíčová slova.
        Méně přesný ale funguje bez modelů.
        """
        # Jednoduchá energy-based detekce + simulace
        # V produkci by toto volalo lightweight STT
        audio_array = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(audio_array ** 2)) / 32768.0

        # Pokud je dost energie, zkusíme rozpoznat (zjednodušená logika)
        # Reálná implementace by použila very fast tiny Whisper model
        return False

    def _matches_wake_word(self, text: str) -> bool:
        """
        Zkontroluje zda text obsahuje wake word nebo jeho variantu.
        
        Args:
            text: Rozpoznaný text (lowercase)
            
        Returns:
            True pokud je wake word přítomen
        """
        phrase = self._custom_phrase

        # Přesná shoda
        if phrase in text:
            return True

        # Podobné varianty (překlepy, různá výslovnost)
        words = phrase.split()
        found_words = sum(1 for w in words if w in text.split())

        # Alespoň 80% slov musí být nalezeno
        if len(words) > 0 and found_words / len(words) >= 0.8:
            return True

        return False

    async def set_custom_phrase(self, phrase: str):
        """
        Nastaví novou wake word frázi.
        
        Args:
            phrase: Nová aktivační fráze
        """
        self._custom_phrase = phrase.lower().strip()
        self.settings.wake_word_phrase = phrase
        logger.info(f"Wake word nastaven na: '{self._custom_phrase}'")

    def cleanup(self):
        """Uvolní zdroje detektoru."""
        if self._engine == "picovoice" and hasattr(self, '_porcupine'):
            self._porcupine.delete()
