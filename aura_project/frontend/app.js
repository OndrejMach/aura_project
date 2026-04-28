/**
 * AURA Voice Assistant – Frontend
 * Komunikuje s Python backendem přes WebSocket.
 */

// ── State ──────────────────────────────────────────────────────────────────

const state = {
  ws: null,
  connected: false,
  listening: false,
  currentState: "idle",   // idle | recording | transcribing | thinking | speaking
  focusActive: false,
};

// ── WebSocket připojení ────────────────────────────────────────────────────

function connect() {
  const port = document.getElementById("wsPort")?.value || 8765;
  const url = `ws://localhost:${port}`;

  state.ws = new WebSocket(url);

  state.ws.onopen = () => {
    state.connected = true;
    updateStatus("connected", "Připojeno");
    // Požádáme o aktuální stav
    send({ type: "get_status" });
  };

  state.ws.onclose = () => {
    state.connected = false;
    updateStatus("disconnected", "Odpojeno");
    // Automatické znovupřipojení za 3 sekundy
    setTimeout(connect, 3000);
  };

  state.ws.onerror = () => {
    updateStatus("disconnected", "Chyba připojení");
  };

  state.ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleMessage(msg);
    } catch (e) {
      console.error("Neplatný JSON:", event.data);
    }
  };
}

function send(data) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(data));
  }
}

function reconnect() {
  if (state.ws) state.ws.close();
  setTimeout(connect, 500);
}

// ── Zpracování zpráv z backendu ────────────────────────────────────────────

function handleMessage(msg) {
  switch (msg.type) {
    case "status":
      state.listening = msg.listening;
      updateListenBtn();
      if (msg.wake_word) {
        document.getElementById("wakeWordInput").value = msg.wake_word;
      }
      break;

    case "state":
      setAssistantState(msg.state);
      break;

    case "wake_word_detected":
      flashOrb();
      addSystemMessage("Wake word detekován...");
      break;

    case "transcript":
      addMessage("user", msg.text);
      break;

    case "response":
      if (msg.action) {
        addMessage("action", `⚡ ${msg.text}`);
      } else {
        addMessage("assistant", msg.text);
      }
      break;

    case "wake_word_set":
      addSystemMessage(`Aktivační fráze nastavena: "${msg.phrase}"`);
      break;

    case "error":
      addSystemMessage(`❌ Chyba: ${msg.message}`);
      setAssistantState("idle");
      break;
  }
}

// ── Stavový automat UI ─────────────────────────────────────────────────────

const STATE_CONFIG = {
  idle: {
    orbClass: "",
    icon: "◉",
    hint: 'Klikni nebo řekni "Hey Aura"',
    statusLabel: "Připojeno",
  },
  recording: {
    orbClass: "active",
    icon: "●",
    hint: "Nahrávám... mluv teď",
    statusLabel: "Nahrávám",
  },
  transcribing: {
    orbClass: "active",
    icon: "◌",
    hint: "Přepisuji řeč...",
    statusLabel: "Přepisuji",
  },
  thinking: {
    orbClass: "thinking",
    icon: "◎",
    hint: "Přemýšlím...",
    statusLabel: "Myslím",
  },
  speaking: {
    orbClass: "speaking",
    icon: "◈",
    hint: "Mluvím...",
    statusLabel: "Mluvím",
  },
};

function setAssistantState(newState) {
  state.currentState = newState;
  const cfg = STATE_CONFIG[newState] || STATE_CONFIG.idle;

  const orb = document.getElementById("voiceOrb");
  const icon = document.getElementById("orbIcon");
  const hint = document.getElementById("orbHint");

  // Reset tříd
  orb.className = "voice-orb";
  if (cfg.orbClass) orb.classList.add(cfg.orbClass);

  icon.textContent = cfg.icon;
  hint.textContent = cfg.hint;

  // Aktualizace status baru
  if (state.connected) {
    const statusClass = newState === "idle" ? "connected" : "active";
    updateStatus(statusClass, cfg.statusLabel);
  }
}

// ── UI Helpers ─────────────────────────────────────────────────────────────

function updateStatus(className, text) {
  const dot = document.getElementById("statusDot");
  const label = document.getElementById("statusText");

  dot.className = "status-dot";
  if (className !== "disconnected") dot.classList.add(className);

  label.textContent = text;
}

function addMessage(role, text) {
  const conv = document.getElementById("conversation");

  const div = document.createElement("div");
  div.className = `message ${role}`;

  const label = document.createElement("span");
  label.className = "msg-label";
  label.textContent = role === "user" ? "TY" : role === "action" ? "AKCE" : "AURA";

  const p = document.createElement("p");
  p.textContent = text;

  div.appendChild(label);
  div.appendChild(p);
  conv.appendChild(div);

  // Scroll na konec
  conv.scrollTop = conv.scrollHeight;
}

function addSystemMessage(text) {
  const conv = document.getElementById("conversation");

  const div = document.createElement("div");
  div.style.cssText = "text-align:center; font-size:11px; color:#5a6070; font-family:'DM Mono',monospace; padding:4px 0;";
  div.textContent = text;
  conv.appendChild(div);
  conv.scrollTop = conv.scrollHeight;
}

function flashOrb() {
  const orb = document.getElementById("voiceOrb");
  orb.style.transform = "scale(1.1)";
  setTimeout(() => orb.style.transform = "", 200);
}

// ── Akce tlačítek ─────────────────────────────────────────────────────────

function toggleListening() {
  send({ type: "toggle_listening" });
  state.listening = !state.listening;
  updateListenBtn();

  if (state.listening) {
    const orb = document.getElementById("voiceOrb");
    orb.classList.add("listening");
    updateStatus("listening", "Poslouchám");
  } else {
    const orb = document.getElementById("voiceOrb");
    orb.classList.remove("listening");
    updateStatus("connected", "Připojeno");
  }
}

function updateListenBtn() {
  const btn = document.getElementById("listenBtn");
  if (state.listening) {
    btn.classList.add("active");
  } else {
    btn.classList.remove("active");
  }
}

function manualActivate() {
  if (!state.connected) {
    addSystemMessage("Nejprve spusť Python backend");
    return;
  }
  send({ type: "manual_activate" });
}

function clearConversation() {
  const conv = document.getElementById("conversation");
  conv.innerHTML = "";
  addMessage("assistant", "Historie smazána. Jak ti mohu pomoci?");
}

function toggleFocus() {
  state.focusActive = !state.focusActive;
  const btn = document.getElementById("focusBtn");
  btn.classList.toggle("active", state.focusActive);
  send({ type: "manual_activate" }); // Aktivujeme asistenta s focus příkazem
  addSystemMessage(state.focusActive ? "Focus režim: zapnut" : "Focus režim: vypnut");
}

function toggleSettings() {
  document.getElementById("settingsPanel").classList.toggle("open");
}

function setWakeWord() {
  const phrase = document.getElementById("wakeWordInput").value.trim();
  if (!phrase) return;
  send({ type: "set_wake_word", phrase });
}

// ── Start ──────────────────────────────────────────────────────────────────

// Připojíme se při načtení stránky
connect();

// Klávesová zkratka: mezerník = manuální aktivace
document.addEventListener("keydown", (e) => {
  if (e.code === "Space" && e.target.tagName !== "INPUT") {
    e.preventDefault();
    manualActivate();
  }
});
