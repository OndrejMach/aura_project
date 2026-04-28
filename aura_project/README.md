# 🌟 AURA – AI Voice Assistant

Hlasový asistent napájený Claude AI, Whisper STT a Edge TTS.

---

## ⚡ Instalace krok za krokem

### 1. Požadavky
- Python 3.10 nebo novější
- Windows 10/11 (nebo Linux)
- Mikrofon

### 2. Stáhni projekt
Rozbal složku `aura_project` kamkoliv, např. `C:\Users\Tvoje\aura_project`

### 3. Otevři VS Code
- **File → Open Folder** → vyber složku `aura_project`

### 4. Otevři terminál ve VS Code
```
Terminal → New Terminal   (nebo Ctrl+`)
```

### 5. Vytvoř virtuální prostředí
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
```

### 6. Nainstaluj závislosti
```bash
pip install -r requirements.txt
```

### 7. Nastav API klíč
```bash
# Zkopíruj .env.example na .env
copy .env.example .env       # Windows
# cp .env.example .env       # Linux

# Otevři .env a vlož svůj Anthropic API klíč:
# ANTHROPIC_API_KEY=sk-ant-xxxxx
```

API klíč získáš zdarma na: https://console.anthropic.com
(nové účty mají $5 kredit)

### 8. (Volitelné) Stáhni VOSK model pro wake word
Pro detekci wake wordu offline stáhni český model:
https://alphacephei.com/vosk/models → vosk-model-small-cs-0.4-rhasspy

Rozbal do složky: `data/vosk-model/`

### 9. Spusť backend
```bash
python backend/main.py
```

### 10. Otevři frontend
Otevři soubor `frontend/index.html` v prohlížeči (dvojklik)

---

## 🎙 Použití

| Způsob aktivace | Popis |
|---|---|
| Řekni "Hey Aura" | Automatická detekce wake wordu |
| Klikni na kruh | Manuální aktivace |
| Mezerník | Klávesová zkratka |

## ⚡ Hlasové příkazy

| Příkaz | Akce |
|---|---|
| "Nastav timer na 5 minut" | Spustí odpočítávání |
| "Otevři kalkulačku" | Spustí aplikaci |
| "Jdi na youtube.com" | Otevře web |
| "Zapiš poznámku: koupit mléko" | Uloží poznámku do data/notes/ |
| "Zapni focus režim" | Aktivuje soustředění |

---

## 📁 Struktura projektu

```
aura_project/
├── backend/
│   ├── core/           ← Jádro aplikace
│   ├── config/         ← Nastavení a API klíče
│   ├── actions/        ← Akce asistenta
│   └── main.py         ← Vstupní bod
├── frontend/           ← Web UI
├── data/               ← Modely, poznámky
├── .env                ← Tvoje API klíče (neverzovat!)
└── requirements.txt    ← Python závislosti
```

---

## 🔧 Konfigurace

Edituj `config.json` (vytvoří se automaticky) nebo nastav env proměnné:

| Proměnná | Výchozí | Popis |
|---|---|---|
| `AURA_WHISPER_MODEL` | `base` | Velikost Whisper modelu |
| `AURA_WHISPER_LANGUAGE` | `cs` | Jazyk přepisu |
| `AURA_WAKE_WORD` | `hey aura` | Aktivační fráze |
| `AURA_TTS_VOICE` | `cs-CZ-VlastaNeural` | Hlas asistenta |

---

## ❓ Řešení problémů

**"Chybí ANTHROPIC_API_KEY"**
→ Zkontroluj soubor `.env`, musí obsahovat tvůj klíč

**"Nebyl nalezen žádný mikrofon"**
→ Zkontroluj že máš povolený přístup mikrofonu v systému

**Wake word nefunguje**
→ Stáhni VOSK model (krok 8) nebo nastav jinou aktivační frázi

**Whisper je pomalý**
→ Změň model na `tiny`: `AURA_WHISPER_MODEL=tiny` v `.env`
