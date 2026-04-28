"""
Konfigurace aplikace AURA.
Všechna nastavení jsou zde centralizována a typována.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json
import os


# Kořenový adresář projektu
ROOT_DIR = Path(__file__).parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
NOTES_DIR = DATA_DIR / "notes"
WAKE_WORDS_DIR = DATA_DIR / "wake_words"


@dataclass
class Settings:
    """
    Hlavní konfigurace aplikace.
    Hodnoty lze přepsat přes config.json nebo env proměnné.
    """

    # ── WebSocket server ──────────────────────────────────────────────────────
    ws_port: int = 8765
    ws_host: str = "localhost"

    # ── Audio ─────────────────────────────────────────────────────────────────
    sample_rate: int = 16000          # Hz – Whisper vyžaduje 16kHz
    channels: int = 1                 # Mono
    chunk_size: int = 1024            # Vzorků na chunk
    silence_threshold: float = 0.01  # Práh pro detekci ticha (RMS)
    silence_duration: float = 1.5    # Sekund ticha pro ukončení nahrávání
    max_record_duration: float = 30.0 # Max délka jedné promluvy v sekundách

    # ── Wake Word ─────────────────────────────────────────────────────────────
    wake_word_phrase: str = "hey aura"
    wake_word_sensitivity: float = 0.5  # 0.0 – 1.0
    wake_word_engine: str = "vosk"       # "vosk" | "picovoice" | "custom"

    # ── Whisper STT ───────────────────────────────────────────────────────────
    whisper_model: str = "base"          # tiny | base | small | medium | large
    whisper_language: str = "cs"         # Jazyk (cs = čeština, en = angličtina)
    whisper_device: str = "cpu"          # "cpu" | "cuda"
    whisper_compute_type: str = "int8"   # Typ výpočtu pro faster-whisper

    # ── Claude AI ─────────────────────────────────────────────────────────────
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 1024
    claude_temperature: float = 0.7
    claude_system_prompt: str = (
        "Jsi AURA, inteligentní hlasový asistent. Odpovídej stručně a přirozeně, "
        "jako při hlasovém rozhovoru. Maximálně 3 věty, pokud není vyžadováno více. "
        "Mluvíš česky, jsi přátelský a věcný."
    )
    conversation_history_limit: int = 10  # Max zpráv v historii konverzace

    # ── TTS (Text-to-Speech) ──────────────────────────────────────────────────
    tts_engine: str = "edge-tts"          # "edge-tts" | "pyttsx3" | "elevenlabs"
    tts_voice: str = "cs-CZ-VlastaNeural" # Hlas pro edge-tts (čeština)
    tts_rate: str = "+0%"                 # Rychlost řeči (+10% = rychlejší)
    tts_volume: str = "+0%"
    tts_pitch: str = "+0Hz"

    # ── Cesty ─────────────────────────────────────────────────────────────────
    data_dir: Path = field(default_factory=lambda: DATA_DIR)
    notes_dir: Path = field(default_factory=lambda: NOTES_DIR)
    wake_words_dir: Path = field(default_factory=lambda: WAKE_WORDS_DIR)

    # ── Focus režim ───────────────────────────────────────────────────────────
    focus_mode_block_sites: list = field(default_factory=lambda: [
        "youtube.com", "facebook.com", "twitter.com",
        "instagram.com", "reddit.com", "tiktok.com"
    ])
    focus_mode_duration_minutes: int = 25  # Pomodoro default

    def __post_init__(self):
        """Vytvoří potřebné adresáře a načte config soubor."""
        self._ensure_directories()
        self._load_from_file()
        self._load_from_env()

    def _ensure_directories(self):
        """Vytvoří adresáře pro data."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.wake_words_dir.mkdir(parents=True, exist_ok=True)

    def _load_from_file(self):
        """Načte nastavení z config.json pokud existuje."""
        config_path = ROOT_DIR / "config.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, value in data.items():
                if hasattr(self, key):
                    setattr(self, key, value)

    def _load_from_env(self):
        """Přepíše nastavení z environment proměnných (AURA_ prefix)."""
        env_mapping = {
            "AURA_WS_PORT": ("ws_port", int),
            "AURA_WHISPER_MODEL": ("whisper_model", str),
            "AURA_WHISPER_LANGUAGE": ("whisper_language", str),
            "AURA_WAKE_WORD": ("wake_word_phrase", str),
            "AURA_TTS_VOICE": ("tts_voice", str),
            "AURA_CLAUDE_MODEL": ("claude_model", str),
        }
        for env_key, (attr, cast) in env_mapping.items():
            if env_key in os.environ:
                setattr(self, attr, cast(os.environ[env_key]))

    def save(self):
        """Uloží aktuální nastavení do config.json."""
        config_path = ROOT_DIR / "config.json"
        data = {
            k: v for k, v in self.__dict__.items()
            if not isinstance(v, Path)  # Path objekty neserializujeme
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
