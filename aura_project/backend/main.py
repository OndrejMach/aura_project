"""
AURA - AI Voice Assistant
Hlavní vstupní bod aplikace.

Spouští backend WebSocket server a audio pipeline.
"""

import asyncio
import sys
import signal
import threading
from pathlib import Path

# Přidáme root do Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config.settings import Settings
from backend.config.secrets import SecretsManager
from backend.core.audio_engine import AudioEngine
from backend.core.wake_word import WakeWordDetector
from backend.core.transcriber import Transcriber
from backend.core.ai_client import ClaudeClient
from backend.core.tts_engine import TTSEngine
from backend.core.action_dispatcher import ActionDispatcher
from backend.api.websocket_server import WebSocketServer
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class AuraAssistant:
    """
    Hlavní orchestrátor celé aplikace.
    Propojuje všechny komponenty do funkčního pipeline.
    """

    def __init__(self):
        logger.info("🌟 Inicializuji AURA Voice Assistant...")

        # Načteme konfiguraci a tajné klíče
        self.settings = Settings()
        self.secrets = SecretsManager()

        # Inicializujeme všechny komponenty
        self.audio_engine = AudioEngine(self.settings)
        self.wake_word_detector = WakeWordDetector(self.settings)
        self.transcriber = Transcriber(self.settings)
        self.ai_client = ClaudeClient('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', self.settings)
        self.tts_engine = TTSEngine(self.settings)
        self.action_dispatcher = ActionDispatcher(self.settings)

        # WebSocket server pro komunikaci s frontendem
        self.ws_server = WebSocketServer(self.settings)

        # Stav asistenta
        self._running = False
        self._listening_active = False

        # Propojíme WebSocket server s callbacky
        self._setup_ws_callbacks()

    def _setup_ws_callbacks(self):
        """Nastaví callback funkce pro WebSocket server."""
        self.ws_server.on_client_command = self._handle_client_command

    async def _handle_client_command(self, command: dict):
        """
        Zpracovává příkazy přicházející z frontend klienta.
        
        Args:
            command: Slovník s klíčem 'type' a dalšími parametry
        """
        cmd_type = command.get("type")
        logger.debug(f"Přijat příkaz z frontendu: {cmd_type}")

        if cmd_type == "toggle_listening":
            if self._listening_active:
                await self._stop_listening()
            else:
                await self._start_listening()

        elif cmd_type == "set_wake_word":
            phrase = command.get("phrase", "")
            await self.wake_word_detector.set_custom_phrase(phrase)
            await self.ws_server.broadcast({"type": "wake_word_set", "phrase": phrase})

        elif cmd_type == "manual_activate":
            # Uživatel aktivoval asistenta ručně (kliknutím)
            await self._process_voice_input()

        elif cmd_type == "get_status":
            await self.ws_server.broadcast(self._get_status())

    async def _start_listening(self):
        """Spustí kontinuální poslouchání na pozadí."""
        self._listening_active = True
        logger.info("🎙️ Začínám poslouchat...")
        await self.ws_server.broadcast({"type": "status", "listening": True})
        asyncio.create_task(self._background_listen_loop())

    async def _stop_listening(self):
        """Zastaví poslouchání na pozadí."""
        self._listening_active = False
        logger.info("🔇 Zastavuji poslouchání")
        await self.ws_server.broadcast({"type": "status", "listening": False})

    async def _background_listen_loop(self):
        """
        Hlavní smyčka pro detekci wake wordu.
        Běží na pozadí a čeká na aktivační frázi.
        """
        logger.info("▶️ Background listen loop spuštěn")

        async for audio_chunk in self.audio_engine.stream_audio():
            if not self._listening_active:
                break

            # Detekujeme wake word v audio chunku
            detected = await self.wake_word_detector.detect(audio_chunk)

            if detected:
                logger.info("✅ Wake word detekován!")
                await self.ws_server.broadcast({"type": "wake_word_detected"})
                # Spustíme plný pipeline zpracování
                await self._process_voice_input()

                # Po zpracování počkáme chvíli před dalším posloucháním
                await asyncio.sleep(1.0)

    async def _process_voice_input(self):
        """
        Hlavní pipeline: nahrání → STT → AI → TTS → akce.
        """
        try:
            # 1. NAHRÁVÁNÍ ŘEČI
            await self.ws_server.broadcast({"type": "state", "state": "recording"})
            logger.info("🎤 Nahrávám řeč uživatele...")

            audio_data = await self.audio_engine.record_utterance()

            if not audio_data:
                logger.warning("Nepodařilo se nahrát žádný zvuk")
                await self.ws_server.broadcast({"type": "state", "state": "idle"})
                return

            # 2. SPEECH TO TEXT (Whisper)
            await self.ws_server.broadcast({"type": "state", "state": "transcribing"})
            logger.info("📝 Přepisuji řeč na text...")

            transcript = await self.transcriber.transcribe(audio_data)

            if not transcript or len(transcript.strip()) < 2:
                logger.warning("Přepis vrátil prázdný text")
                await self.ws_server.broadcast({"type": "state", "state": "idle"})
                return

            logger.info(f"📄 Přepis: '{transcript}'")
            await self.ws_server.broadcast({
                "type": "transcript",
                "text": transcript
            })

            # 3. DETEKCE AKCE (před voláním AI)
            action = self.action_dispatcher.detect_action(transcript)

            if action:
                logger.info(f"⚡ Detekována akce: {action['type']}")
                result = await self.action_dispatcher.execute(action)
                response_text = result.get("message", "Akce provedena.")
            else:
                # 4. CLAUDE AI
                await self.ws_server.broadcast({"type": "state", "state": "thinking"})
                logger.info("🤖 Odesílám dotaz do Claude API...")

                response_text = await self.ai_client.chat(transcript)

            logger.info(f"💬 Odpověď: '{response_text[:100]}...'")
            await self.ws_server.broadcast({
                "type": "response",
                "text": response_text,
                "action": action
            })

            # 5. TEXT TO SPEECH
            await self.ws_server.broadcast({"type": "state", "state": "speaking"})
            logger.info("🔊 Převádím odpověď na hlas...")

            audio_response = await self.tts_engine.synthesize(response_text)
            await self.tts_engine.play(audio_response)

            # Hotovo
            await self.ws_server.broadcast({"type": "state", "state": "idle"})

        except Exception as e:
            logger.error(f"Chyba v pipeline: {e}", exc_info=True)
            await self.ws_server.broadcast({
                "type": "error",
                "message": str(e)
            })
            await self.ws_server.broadcast({"type": "state", "state": "idle"})

    def _get_status(self) -> dict:
        """Vrátí aktuální stav asistenta."""
        return {
            "type": "status",
            "listening": self._listening_active,
            "whisper_model": self.settings.whisper_model,
            "wake_word": self.settings.wake_word_phrase,
        }

    async def run(self):
        """Spustí celou aplikaci."""
        self._running = True
        logger.info("🚀 AURA spuštěna")

        # Spustíme WebSocket server
        await self.ws_server.start()

        logger.info(f"🌐 WebSocket server běží na ws://localhost:{self.settings.ws_port}")
        logger.info("✨ Otevři frontend/index.html ve svém prohlížeči")

        # Čekáme na vypnutí
        try:
            await asyncio.Future()  # Čeká donekonečna
        except asyncio.CancelledError:
            pass

    async def shutdown(self):
        """Bezpečně vypne všechny komponenty."""
        logger.info("👋 Vypínám AURA...")
        self._running = False
        await self._stop_listening()
        await self.ws_server.stop()
        self.audio_engine.cleanup()
        logger.info("✅ AURA vypnuta")


def main():
    """Vstupní bod pro spuštění z příkazové řádky."""
    assistant = AuraAssistant()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def handle_signal(sig, frame):
        logger.info(f"Přijat signál {sig}, vypínám...")
        loop.create_task(assistant.shutdown())
        loop.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        loop.run_until_complete(assistant.run())
    except KeyboardInterrupt:
        loop.run_until_complete(assistant.shutdown())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
