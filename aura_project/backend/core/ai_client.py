"""
Claude AI klient – komunikace s Anthropic API.

Udržuje historii konverzace pro přirozený dialog.
"""

import asyncio
from typing import Optional

import anthropic

from backend.config.settings import Settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class ClaudeClient:
    """Klient pro komunikaci s Claude API."""

    def __init__(self, api_key: str, settings: Settings):
        self.settings = settings
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._history: list = []  # Historie konverzace
        logger.info("✅ Claude API klient inicializován")

    async def chat(self, user_message: str) -> str:
        """
        Odešle zprávu do Claude a vrátí odpověď.

        Args:
            user_message: Text od uživatele

        Returns:
            Odpověď od Claude
        """
        # Přidáme zprávu do historie
        self._history.append({
            "role": "user",
            "content": user_message
        })

        # Ořežeme historii pokud je příliš dlouhá
        if len(self._history) > self.settings.conversation_history_limit * 2:
            self._history = self._history[-self.settings.conversation_history_limit * 2:]

        try:
            response = await self._client.messages.create(
                model=self.settings.claude_model,
                max_tokens=self.settings.claude_max_tokens,
                system=self.settings.claude_system_prompt,
                messages=self._history
            )

            answer = response.content[0].text

            # Uložíme odpověď do historie
            self._history.append({
                "role": "assistant",
                "content": answer
            })

            return answer

        except anthropic.APIError as e:
            logger.error(f"Claude API chyba: {e}")
            # Odstraníme poslední zprávu z historie (selhala)
            self._history.pop()
            return f"Omlouvám se, nastala chyba při komunikaci s AI: {str(e)}"

    def clear_history(self):
        """Vymaže historii konverzace."""
        self._history = []
        logger.info("Historie konverzace vymazána")
