"""
Action Dispatcher – rozpoznává a spouští akce z hlasových příkazů.

Podporované akce:
- Otevřít aplikaci
- Spustit timer
- Otevřít web
- Zapsat poznámku
- Zapnout focus režim
"""

import asyncio
import re
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config.settings import Settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)


# Slovník klíčových slov pro detekci akcí (česky + anglicky)
ACTION_PATTERNS = {
    "timer": [
        r"nastav timer na (\d+) (minut|sekund|hodin)",
        r"set timer for (\d+) (minutes|seconds|hours)",
        r"timer (\d+) (minut|sekund)",
        r"připomeň mi za (\d+) (minut|sekund|hodin)",
    ],
    "open_app": [
        r"otevři (.+)",
        r"spusť (.+)",
        r"open (.+)",
        r"launch (.+)",
        r"start (.+)",
    ],
    "open_web": [
        r"otevři web (.+)",
        r"jdi na (.+\.cz|.+\.com|.+\.org|.+\.net)",
        r"otevři stránku (.+)",
        r"open website (.+)",
        r"go to (.+)",
        r"navigate to (.+)",
    ],
    "note": [
        r"zapiš poznámku[:\s]+(.+)",
        r"ulož poznámku[:\s]+(.+)",
        r"poznámka[:\s]+(.+)",
        r"take note[:\s]+(.+)",
        r"save note[:\s]+(.+)",
        r"note[:\s]+(.+)",
    ],
    "focus": [
        r"zapni focus režim",
        r"focus mode",
        r"nerušit režim",
        r"soustředění",
        r"pomodoro",
        r"turn on focus",
        r"enable focus",
    ],
}

# Mapování názvů aplikací na spustitelné soubory (Windows)
APP_MAP_WINDOWS = {
    "notepad": "notepad.exe",
    "poznámkový blok": "notepad.exe",
    "kalkulačka": "calc.exe",
    "calculator": "calc.exe",
    "průzkumník": "explorer.exe",
    "explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "terminál": "cmd.exe",
    "spotify": "spotify.exe",
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
}


class ActionDispatcher:
    """
    Detekuje akce v textu a spouští je.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._active_timers = []
        self._focus_active = False

    def detect_action(self, text: str) -> Optional[dict]:
        """
        Zjistí zda text obsahuje příkaz pro akci.

        Args:
            text: Přepsaný text od uživatele

        Returns:
            Slovník s typem akce a parametry, nebo None
        """
        text_lower = text.lower().strip()

        for action_type, patterns in ACTION_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text_lower)
                if match:
                    return self._build_action(action_type, match, text)

        return None

    def _build_action(self, action_type: str, match: re.Match, original: str) -> dict:
        """Sestaví slovník akce z regex match."""
        action = {"type": action_type, "original": original}

        if action_type == "timer":
            amount = int(match.group(1))
            unit = match.group(2)
            seconds = self._to_seconds(amount, unit)
            action["seconds"] = seconds
            action["display"] = f"{amount} {unit}"

        elif action_type == "open_app":
            action["app_name"] = match.group(1).strip()

        elif action_type == "open_web":
            url = match.group(1).strip()
            if not url.startswith("http"):
                url = f"https://{url}"
            action["url"] = url

        elif action_type == "note":
            action["content"] = match.group(1).strip()

        elif action_type == "focus":
            action["duration"] = self.settings.focus_mode_duration_minutes

        return action

    async def execute(self, action: dict) -> dict:
        """
        Spustí akci a vrátí výsledek.

        Args:
            action: Slovník akce z detect_action()

        Returns:
            Slovník s 'message' (odpověď pro TTS) a 'success'
        """
        action_type = action["type"]

        try:
            if action_type == "timer":
                return await self._run_timer(action)

            elif action_type == "open_app":
                return await self._open_app(action)

            elif action_type == "open_web":
                return await self._open_web(action)

            elif action_type == "note":
                return await self._save_note(action)

            elif action_type == "focus":
                return await self._toggle_focus(action)

        except Exception as e:
            logger.error(f"Chyba při provádění akce {action_type}: {e}")
            return {"success": False, "message": f"Akci se nepodařilo provést: {e}"}

        return {"success": False, "message": "Neznámá akce"}

    async def _run_timer(self, action: dict) -> dict:
        """Spustí odpočítávání."""
        seconds = action["seconds"]
        display = action["display"]

        async def _timer_task():
            logger.info(f"⏲️ Timer spuštěn: {display}")
            await asyncio.sleep(seconds)
            logger.info(f"⏰ Timer dokončen: {display}")
            # V reálné implementaci by zde bylo notifikace / zvuk

        task = asyncio.create_task(_timer_task())
        self._active_timers.append(task)

        return {
            "success": True,
            "message": f"Timer nastaven na {display}. Upozorním tě až vyprší."
        }

    async def _open_app(self, action: dict) -> dict:
        """Otevře aplikaci."""
        app_name = action["app_name"].lower()
        import platform

        if platform.system() == "Windows":
            exe = APP_MAP_WINDOWS.get(app_name)
            if exe:
                subprocess.Popen([exe])
                return {"success": True, "message": f"Otevírám {action['app_name']}"}
            else:
                # Zkusíme spustit přímo
                try:
                    subprocess.Popen([app_name])
                    return {"success": True, "message": f"Spouštím {action['app_name']}"}
                except FileNotFoundError:
                    return {"success": False, "message": f"Aplikaci '{action['app_name']}' jsem nenašel"}
        else:
            # Linux / Mac
            try:
                subprocess.Popen(["xdg-open", app_name])
                return {"success": True, "message": f"Otevírám {action['app_name']}"}
            except Exception:
                return {"success": False, "message": f"Nepodařilo se otevřít {action['app_name']}"}

    async def _open_web(self, action: dict) -> dict:
        """Otevře webovou stránku v prohlížeči."""
        url = action["url"]
        webbrowser.open(url)
        return {"success": True, "message": f"Otevírám {url}"}

    async def _save_note(self, action: dict) -> dict:
        """Uloží poznámku do souboru."""
        content = action["content"]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        notes_file = self.settings.notes_dir / "notes.txt"
        notes_file.parent.mkdir(parents=True, exist_ok=True)

        with open(notes_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {content}\n")

        logger.info(f"📝 Poznámka uložena: {content}")
        return {"success": True, "message": f"Poznámka uložena: {content}"}

    async def _toggle_focus(self, action: dict) -> dict:
        """Zapne nebo vypne focus režim."""
        if self._focus_active:
            self._focus_active = False
            return {"success": True, "message": "Focus režim vypnut. Vítej zpět!"}
        else:
            self._focus_active = True
            duration = action.get("duration", 25)
            return {
                "success": True,
                "message": f"Focus režim zapnut na {duration} minut. Hodně soustředění!"
            }

    @staticmethod
    def _to_seconds(amount: int, unit: str) -> int:
        """Převede čas na sekundy."""
        unit = unit.lower()
        if unit in ("sekunda", "sekund", "second", "seconds"):
            return amount
        elif unit in ("minuta", "minut", "minute", "minutes"):
            return amount * 60
        elif unit in ("hodina", "hodin", "hour", "hours"):
            return amount * 3600
        return amount * 60
