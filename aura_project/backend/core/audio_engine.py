"""
Audio Engine – jádro pro práci se zvukem.

Zodpovídá za:
- Streaming audio ze mikrofonu
- Voice Activity Detection (VAD)
- Nahrávání promluvy s automatickým detekováním konce řeči
- Cross-platform kompatibilitu (Windows / Linux / Android přes Termux)
"""

import asyncio
import io
import struct
import wave
from collections import deque
from typing import AsyncGenerator, Optional

import numpy as np
import sounddevice as sd

from config.settings import Settings
from utils.logger import get_logger

logger = get_logger(__name__)


class AudioEngine:
    """
    Spravuje audio vstup z mikrofonu.
    
    Klíčové vlastnosti:
    - Použití sounddevice pro cross-platform kompatibilitu
    - Webrtcvad pro efektivní detekci hlasové aktivity
    - Async-first design pomocí asyncio.Queue
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._audio_queue: asyncio.Queue = asyncio.Queue()
        self._stream: Optional[sd.InputStream] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Inicializujeme VAD
        try:
            import webrtcvad
            self._vad = webrtcvad.Vad(2)  # Agresivita 0-3 (2 = vyvážené)
            self._vad_available = True
            logger.info("✅ WebRTC VAD inicializován")
        except ImportError:
            self._vad = None
            self._vad_available = False
            logger.warning("⚠️ webrtcvad nedostupný, používám RMS energii pro VAD")

        # Ověříme dostupné audio zařízení
        self._check_audio_device()

    def _check_audio_device(self):
        """Ověří dostupnost vstupního zvukového zařízení."""
        try:
            devices = sd.query_devices()
            input_devices = [d for d in devices if d['max_input_channels'] > 0]

            if not input_devices:
                raise RuntimeError("Nebyl nalezen žádný mikrofon!")

            logger.info(f"🎤 Dostupné mikrofony: {len(input_devices)}")

            # Výchozí vstupní zařízení
            default_input = sd.query_devices(kind='input')
            logger.info(f"   Výchozí: {default_input['name']}")

        except Exception as e:
            logger.error(f"Chyba při kontrole audio zařízení: {e}")
            raise

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status: sd.CallbackFlags
    ):
        """
        Callback volaný sounddevice při příjmu audio dat.
        Vkládá data do asyncio fronty.
        """
        if status:
            logger.debug(f"Audio callback status: {status}")

        # Konvertujeme na mono int16 bytes (formát pro VAD a Whisper)
        audio_bytes = (indata[:, 0] * 32767).astype(np.int16).tobytes()

        # Thread-safe vložení do asyncio queue
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(
                self._audio_queue.put_nowait,
                audio_bytes
            )

    async def stream_audio(self) -> AsyncGenerator[bytes, None]:
        """
        Async generátor pro kontinuální stream audio dat ze mikrofonu.
        
        Yields:
            bytes: Chunk audio dat ve formátu int16 PCM
        """
        self._loop = asyncio.get_event_loop()

        with sd.InputStream(
            samplerate=self.settings.sample_rate,
            channels=self.settings.channels,
            dtype='float32',
            blocksize=self.settings.chunk_size,
            callback=self._audio_callback
        ) as stream:
            self._stream = stream
            logger.debug("Audio stream spuštěn")

            while True:
                # Čekáme na nový chunk (s timeoutem pro kontrolu ukončení)
                try:
                    chunk = await asyncio.wait_for(
                        self._audio_queue.get(),
                        timeout=0.1
                    )
                    yield chunk
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break

    async def record_utterance(self) -> Optional[bytes]:
        """
        Nahraje jednu promluvu uživatele.
        
        Algoritmus:
        1. Čeká na začátek řeči (detekce hlasové aktivity)
        2. Nahrává dokud je detekována řeč
        3. Ukončí nahrávání po definované době ticha
        4. Vrátí WAV data
        
        Returns:
            WAV audio data jako bytes, nebo None při chybě
        """
        logger.info("⏳ Čekám na řeč...")

        self._loop = asyncio.get_event_loop()
        recorded_chunks = []
        silent_chunks = 0
        speaking_started = False
        total_chunks = 0

        # Parametry pro detekci ticha
        chunk_duration_ms = (self.settings.chunk_size / self.settings.sample_rate) * 1000
        silence_chunks_needed = int(
            self.settings.silence_duration * 1000 / chunk_duration_ms
        )
        max_chunks = int(
            self.settings.max_record_duration * 1000 / chunk_duration_ms
        )

        with sd.InputStream(
            samplerate=self.settings.sample_rate,
            channels=self.settings.channels,
            dtype='float32',
            blocksize=self.settings.chunk_size,
            callback=self._audio_callback
        ):
            while total_chunks < max_chunks:
                try:
                    chunk = await asyncio.wait_for(
                        self._audio_queue.get(),
                        timeout=0.5
                    )
                except asyncio.TimeoutError:
                    continue

                total_chunks += 1

                # Detekujeme hlasovou aktivitu
                is_speech = self._detect_speech(chunk)

                if is_speech:
                    speaking_started = True
                    silent_chunks = 0
                    recorded_chunks.append(chunk)
                elif speaking_started:
                    recorded_chunks.append(chunk)
                    silent_chunks += 1

                    # Konec promluvy po dostatečném tichu
                    if silent_chunks >= silence_chunks_needed:
                        logger.info(f"🔇 Detekován konec promluvy ({len(recorded_chunks)} chunks)")
                        break

        if not recorded_chunks:
            logger.warning("Nebyla nahrána žádná data")
            return None

        return self._chunks_to_wav(recorded_chunks)

    def _detect_speech(self, audio_bytes: bytes) -> bool:
        """
        Detekuje přítomnost řeči v audio chunku.
        
        Preferuje WebRTC VAD, fallback na RMS energii.
        
        Args:
            audio_bytes: Raw int16 PCM data
            
        Returns:
            True pokud je detekována řeč
        """
        if self._vad_available and self._vad:
            try:
                # WebRTC VAD vyžaduje přesně 10, 20 nebo 30ms frameů
                # při 16kHz: 10ms = 160 vzorků = 320 bytes
                frame_size = int(self.settings.sample_rate * 0.02) * 2  # 20ms frame
                if len(audio_bytes) >= frame_size:
                    return self._vad.is_speech(
                        audio_bytes[:frame_size],
                        self.settings.sample_rate
                    )
            except Exception:
                pass

        # Fallback: RMS energie
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(audio_array ** 2)) / 32768.0
        return rms > self.settings.silence_threshold

    def _chunks_to_wav(self, chunks: list) -> bytes:
        """
        Převede seznam audio chunků na WAV bytes.
        
        Args:
            chunks: Seznam raw PCM int16 bytes
            
        Returns:
            WAV soubor jako bytes
        """
        raw_audio = b"".join(chunks)

        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(self.settings.channels)
            wav_file.setsampwidth(2)  # 16-bit = 2 bytes
            wav_file.setframerate(self.settings.sample_rate)
            wav_file.writeframes(raw_audio)

        return buffer.getvalue()

    def get_audio_level(self) -> float:
        """
        Vrátí aktuální hlasitost mikrofonu (0.0 - 1.0).
        Použitelné pro vizualizaci v UI.
        """
        try:
            # Krátké nahrání pro měření
            recording = sd.rec(
                frames=self.settings.chunk_size,
                samplerate=self.settings.sample_rate,
                channels=1,
                dtype='float32',
                blocking=True
            )
            rms = np.sqrt(np.mean(recording ** 2))
            return min(1.0, rms * 10)  # Normalizace
        except Exception:
            return 0.0

    def cleanup(self):
        """Uvolní audio zdroje."""
        if self._stream and not self._stream.closed:
            self._stream.close()
        logger.info("Audio engine ukončen")
