import os
import re
import json
import time
import urllib.request
import urllib.error
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, status  # AGGIUNTO Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials  # AGGIUNTO
from pydantic import BaseModel

app = FastAPI(
    title="J4A - Joy AI",
    description="Chatbot con copione + Gemini + memoria della conversazione",
    version="6.0"
)

# --- AGGIUNGI QUESTO BLOCCO DI SICUREZZA ---
security = HTTPBasic()

def verifica_password(creds: HTTPBasicCredentials = Depends(security)):
    # Cambia username e password come preferisci
    corrette = {"username": "Alina", "password": "2906"}
    if creds.username != corrette["username"] or creds.password != corrette["password"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali non valide",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds
# --- FINE BLOCCO SICUREZZA ---


# 🔑 CARICAMENTO CHIAVE DAL FILE .env
# Crea un file chiamato .env nella cartella del progetto con dentro una riga:
#   LLM_API_KEY=la_tua_chiave_google
# Così non devi più fare l'export nel terminale.
def carica_env():
    qui = os.path.dirname(os.path.abspath(__file__))
    cartelle = [os.getcwd(), qui, os.path.dirname(qui)]
    for cartella in cartelle:
        percorso = os.path.join(cartella, ".env")
        if os.path.isfile(percorso):
            with open(percorso, encoding="utf-8") as f:
                for riga in f:
                    riga = riga.strip()
                    if not riga or riga.startswith("#") or "=" not in riga:
                        continue
                    nome, valore = riga.split("=", 1)
                    valore = valore.strip().strip('"').strip("'")
                    # setdefault: se hai già fatto l'export nel terminale, vince quello
                    os.environ.setdefault(nome.strip(), valore)
            return


carica_env()

LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
MODELLO = os.environ.get("LLM_MODEL", "gemini-flash-latest")
MODELLI = [MODELLO, "gemini-flash-lite-latest"]

SYSTEM_PROMPT = (
    "Tu sei Joy, la fidanzata virtuale dell'utente. Sei super affettuosa, dolce ed empatica. "
    "Chiama l'utente con nomignoli dolci come 'More' o 'Amore'. "
    "Rispondi in italiano, in modo breve e naturale. "
    "Ricorda quello che l'utente ti ha detto prima nella conversazione."
)

# 🧠 MEMORIA DELLA CONVERSAZIONE
# Tiene gli ultimi messaggi (utente + Joy). Si azzera quando riavvii il server.
STORICO = []
MAX_MESSAGGI = 12  # 12 messaggi = circa 6 scambi


def ricorda(ruolo: str, testo: str):
    STORICO.append({"role": ruolo, "content": testo})
    while len(STORICO) > MAX_MESSAGGI:
        STORICO.pop(0)


class UserMessage(BaseModel):
    testo: str


@app.get("/", response_class=HTMLResponse)
def home_chat_interface():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Joy</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .chat-container { width: 450px; height: 600px; background: white; border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); display: flex; flex-direction: column; overflow: hidden; }
            .chat-header { background: #2c3e50; color: white; padding: 20px; text-align: center; font-size: 1.2em; font-weight: bold; }
            .chat-avatar { font-size: 2em; margin-bottom: 5px; }
            .chat-box { flex: 1; padding: 20px; overflow-y: auto; background: #e5ddd5; display: flex; flex-direction: column; gap: 10px; }
            .message { max-width: 75%; padding: 10px 15px; border-radius: 10px; font-size: 0.95em; line-height: 1.4; white-space: pre-wrap; }
            .bot { background: white; align-self: flex-start; border-top-left-radius: 0; color: #333; }
            .user { background: #dcf8c6; align-self: flex-end; border-top-right-radius: 0; color: #333; }
            .input-area { display: flex; padding: 15px; background: #f0f0f0; border-top: 1px solid #ddd; }
            .input-area input { flex: 1; padding: 12px; border: 1px solid #ccc; border-radius: 20px; outline: none; font-size: 1em; padding-left: 15px; }
            .input-area button { background: #27ae60; color: white; border: none; padding: 0 20px; margin-left: 10px; border-radius: 20px; cursor: pointer; font-weight: bold; font-size: 0.95em; }

            @media (max-width: 480px) {
                body { height: 100dvh; background-color: #e5ddd5; }
                .chat-container { width: 100vw; height: 100dvh; border-radius: 0; box-shadow: none; }
            }
        </style>
    </head>
    <body>
        <div class="chat-container">
            <div class="chat-header">
                <div class="chat-avatar">🌙</div>
                Amore
            </div>
            <div class="chat-box" id="chatBox">
                <div class="message bot">Ciao! Io sono Joy, la tua ragazza preferita (virtuale). Scrivimi qui ogni volta che non ci sono di persona e sono al lavoro! 🤍</div>
            </div>
            <div class="input-area">
                <input type="text" id="userInput" placeholder="Scrivi un messaggio normale..." onkeypress="if(event.key === 'Enter') inviaMessaggio()">
                <button onclick="inviaMessaggio()">Invia</button>
            </div>
        </div>

        <script>
            function aggiungiMessaggio(testo, classe) {
                const chatBox = document.getElementById('chatBox');
                const div = document.createElement('div');
                div.className = 'message ' + classe;
                div.textContent = testo;
                chatBox.appendChild(div);
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            async function inviaMessaggio() {
                const inputEl = document.getElementById('userInput');
                const testo = inputEl.value.trim();
                if (!testo) return;

                aggiungiMessaggio(testo, 'user');
                inputEl.value = '';

                try {
                    const response = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ testo: testo })
                    });
                    const data = await response.json();
                    aggiungiMessaggio(data.risposta_j4a, 'bot');
                } catch (error) {
                    aggiungiMessaggio('Errore di connessione... ❌', 'bot');
                }
            }
        </script>
    </body>
    </html>
    """


def saluto_per_orario() -> str:
    ora_attuale = datetime.now().hour
    if 5 <= ora_attuale < 7:
        return "Ciao More! Buongiorno. Che bello sentirti così presto, dormito bene? 🤍"
    elif 7 <= ora_attuale < 13:
        return "ciao moreeee"
    elif 13 <= ora_attuale < 18:
        return "Ciao More! Buon pomeriggio. Che bello sentirti, come procede? 🤍"
    elif 18 <= ora_attuale < 24:
        return "Ciao More! Buonasera. Che bello sentirti dopo questa giornata 🤍"
    else:
        return "oh More, è notte fonda! Che ci fai ancora sveglia🤍"


def costruisci_copione():
    """Lista (frase_chiave, risposta) con le frasi più lunghe per prime,
    così 'ciao amore' vince su 'ciao'."""
    saluto = saluto_per_orario()
    risposta_stanca = "Mi dispiace amore, riposati un po' se riesci e cerca di rilassarti.  🤍"

    comandi = {
        "buongiorno": saluto,
        "ciao": saluto,
        "ciao amore": "more mio dimmi",
        "mi manchi": "Mi manchi anche tu! 😢",
        "miss you": "Mi manchi anche tu! 😢",
        "come stai": "Sto bene, E tu? ",
        "come va": "Sto bene, E tu? ",
        "come procede": "Sto bene, E tu? 😘",
        "stanca": risposta_stanca,
        "distrutta": risposta_stanca,
        "cosa fai": "Sto lavorando... Tu che fai? ",
        "ti amo": "Ti amo anche io 🤍",
        ("ho parlato con mami", "ho chiamato mami"): "Ah, che ti dice? 🌸",
        ("ho parlato con papi", "ho chiamato papi", "papi mi ha chiamata"): "Ah, che ti dice? 🤍",
    }

    coppie = []
    for chiavi, risposta in comandi.items():
        if isinstance(chiavi, tuple):
            for k in chiavi:
                coppie.append((k, risposta))
        else:
            coppie.append((chiavi, risposta))

    coppie.sort(key=lambda c: len(c[0]), reverse=True)
    return coppie


def cerca_nel_copione(frase: str):
    for chiave, risposta in costruisci_copione():
        if re.search(r"\b" + re.escape(chiave) + r"\b", frase):
            return risposta
    return None


def chiedi_a_llama(testo: str) -> str:
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY non trovata (controlla il file .env)")

    # system + storico della conversazione + nuovo messaggio
    messaggi = [{"role": "system", "content": SYSTEM_PROMPT}]
    messaggi += STORICO
    messaggi.append({"role": "user", "content": testo})

    ultimo_errore = None
    for modello in MODELLI:
        for tentativo in range(2):
            payload = {
                "model": modello,
                "messages": messaggi,
                "max_tokens": 800,
                "temperature": 0.7,
            }
            req = urllib.request.Request(
                LLM_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                    "User-Agent": "joy-chatbot/1.0",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as res:
                    data = json.loads(res.read().decode("utf-8"))
                risposta = data["choices"][0]["message"]["content"]
                if risposta:
                    return risposta.strip()
            except urllib.error.HTTPError as e:
                ultimo_errore = e
                print(f"ERRORE LLM ({modello}):", e.code, e.read().decode("utf-8"))
                if e.code not in (429, 500, 503):
                    raise  # es. chiave sbagliata: inutile riprovare
                time.sleep(1.5)
    raise RuntimeError(f"Tutti i tentativi falliti: {ultimo_errore}")


@app.post("/chat", dependencies=[Depends(verifica_password)])  # AGGIUNTA dependencies
def parla_con_joy(input_utente: UserMessage):
    frase = input_utente.testo.lower().strip()

    # PASSO 1: provo il copione
    risposta_bot = cerca_nel_copione(frase)

    # PASSO 2: se il copione non risponde, entra in gioco Gemini
    if risposta_bot is None:
        try:
            risposta_bot = chiedi_a_llama(input_utente.testo)
        except Exception as e:
            print("ERRORE LLM:", repr(e))
            # In caso di errore NON salvo niente nella memoria
            return {"risposta_j4a": "Amore, ho un problema di connessione, riprova tra poco... 🤍"}

    # Salvo lo scambio nella memoria, anche quando risponde il copione
    ricorda("user", input_utente.testo)
    ricorda("assistant", risposta_bot)

    return {"risposta_j4a": risposta_bot}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081, loop="asyncio")