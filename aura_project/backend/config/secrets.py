"""
Bezpečná správa API klíčů a tajných dat.

Klíče se načítají v tomto pořadí (od nejvyšší priority):
1. Environment proměnné
2. .env soubor (přes python-dotenv)
3. OS keychain (přes keyring)

NIKDY neukládejte klíče přímo do kódu nebo do verzovaných souborů!
"""

import os
import sys
from pathlib import Path
from typing import Optional

# Načteme .env soubor pokud existuje
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass  # dotenv není nainstalováno, spoléháme na OS env

try:
    import keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False


class SecretsManager:
    """
    Spravuje přístup k API klíčům a citlivým datům.
    
    Použití:
        secrets = SecretsManager()
        api_key = secrets.anthropic_api_key
    """

    SERVICE_NAME = "aura-assistant"

    def __init__(self):
        self._validate_required_secrets()

    @property
    def anthropic_api_key(self) -> str:
        """Vrátí Anthropic API klíč."""
        return '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'
        return self._get_secret(
            env_key="ANTHROPIC_API_KEY",
            keyring_key="anthropic_api_key",
            required=True
        )

    @property
    def picovoice_access_key(self) -> Optional[str]:
        """Vrátí Picovoice Access Key (volitelný)."""
        return self._get_secret(
            env_key="PICOVOICE_ACCESS_KEY",
            keyring_key="picovoice_access_key",
            required=False
        )

    @property
    def elevenlabs_api_key(self) -> Optional[str]:
        """Vrátí ElevenLabs API klíč (volitelný, pro TTS)."""
        return self._get_secret(
            env_key="ELEVENLABS_API_KEY",
            keyring_key="elevenlabs_api_key",
            required=False
        )

    def _get_secret(
        self,
        env_key: str,
        keyring_key: str,
        required: bool = False
    ) -> Optional[str]:
        """
        Načte tajný klíč z dostupných zdrojů.
        
        Args:
            env_key: Název environment proměnné
            keyring_key: Klíč pro OS keychain
            required: Pokud True a klíč nenalezen, vyhodí výjimku
            
        Returns:
            Hodnota klíče nebo None
        """
        # 1. Environment proměnná (nejvyšší priorita)
        value = os.environ.get(env_key)
        if value:
            return value

        # 2. OS Keychain (bezpečné úložiště)
        if _KEYRING_AVAILABLE:
            value = keyring.get_password(self.SERVICE_NAME, keyring_key)
            if value:
                return value

        # 3. Klíč nenalezen
        if required:
            raise EnvironmentError(
                f"\n❌ Chybí povinný klíč: {env_key}\n"
                f"   Přidej ho do souboru .env:\n"
                f"   {env_key}=tvůj-api-klíč-zde\n"
                f"\n   Nebo ulož přes OS keychain:\n"
                f"   python -c \"import keyring; keyring.set_password("
                f"'aura-assistant', '{keyring_key}', 'tvůj-klíč')\""
            )
        return None

    def store_in_keychain(self, key_name: str, value: str):
        """
        Bezpečně uloží klíč do OS keychainu.
        
        Args:
            key_name: Název klíče (např. 'anthropic_api_key')
            value: Hodnota klíče
        """
        if not _KEYRING_AVAILABLE:
            raise RuntimeError(
                "Keyring není dostupný. Nainstaluj: pip install keyring"
            )
        keyring.set_password(self.SERVICE_NAME, key_name, value)
        print(f"✅ Klíč '{key_name}' bezpečně uložen do OS keychainu")

    def _validate_required_secrets(self):
        """Ověří dostupnost povinných klíčů při startu."""
        # Anthropic API klíč je povinný
        try:
            _ = self.anthropic_api_key
        except EnvironmentError as e:
            print(str(e))
            sys.exit(1)
