"""
Bot Telegram Skincare — Sequenza personalizzata per ogni iscritto
- /start → salva l'utente nel Google Sheet e invia subito il Giorno 1
- GitHub Actions ogni mattina invia il messaggio del giorno giusto
"""

import os
import re
import requests
from datetime import date, datetime, timedelta

TELEGRAM_BOT_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
GOOGLE_DOC_FILE_ID   = os.environ["GOOGLE_DOC_FILE_ID"]
APPS_SCRIPT_URL      = os.environ["APPS_SCRIPT_URL"]


def scarica_messaggi() -> dict:
    url = f"https://docs.google.com/document/d/{GOOGLE_DOC_FILE_ID}/export?format=txt"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    testo = r.text
    messaggi = {}
    pattern = re.compile(r'[Gg]iorno\s+(\d+)\s*[:.\-]\s*(.+?)(?=\n[Gg]iorno\s+\d+|\Z)', re.DOTALL)
    for match in pattern.finditer(testo):
        numero    = int(match.group(1))
        contenuto = match.group(2).strip()
        if contenuto:
            messaggi[numero] = contenuto
    return messaggi


def leggi_iscritti() -> list:
    r = requests.get(APPS_SCRIPT_URL, params={"action": "leggi"}, timeout=15)
    r.raise_for_status()
    return r.json()


def salva_iscritto(chat_id: str, nome: str, data_iscrizione: str) -> None:
    payload = {
        "action": "scrivi",
        "chat_id": chat_id,
        "nome": nome,
        "data_iscrizione": data_iscrizione
    }
    r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=15)
    r.raise_for_status()


def invia_messaggio(chat_id: str, testo: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": testo}
    r = requests.post(url, json=payload, timeout=15)
    return r.ok


def calcola_giorno(data_iscrizione_str: str, totale: int):
    try:
        data_iscrizione = datetime.fromisoformat(str(data_iscrizione_str).strip()).date()
    except (ValueError, TypeError):
        return None
    delta = (date.today() - data_iscrizione).days + 1
    if delta < 1 or delta > totale:
        return None
    return delta


def processa_aggiornamenti() -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    offset_file = "/tmp/telegram_offset.txt"
    offset = 0
    try:
        with open(offset_file) as f:
            offset = int(f.read().strip())
    except:
        pass

    r = requests.get(url, params={"offset": offset, "timeout": 5}, timeout=10)
    if not r.ok:
        return

    updates = r.json().get("result", [])

    for update in updates:
        offset = update["update_id"] + 1
        msg = update.get("message", {})
        text = msg.get("text", "")

        if text.startswith("/start"):
            chat_id = str(msg["chat"]["id"])
            nome = msg["from"].get("first_name", "Amico")

            iscritti = leggi_iscritti()
            ids_esistenti = [str(i.get("chat_id", "")) for i in iscritti]

            if chat_id not in ids_esistenti:
                # Salva con data di IERI → così oggi è già Giorno 1
                data_ieri = (date.today() - timedelta(days=1)).isoformat()
                salva_iscritto(chat_id, nome, data_ieri)

                # Invia subito il Giorno 1
                messaggi = scarica_messaggi()
                if messaggi:
                    chiavi = sorted(messaggi.keys())
                    msg_g1 = messaggi[chiavi[0]]
                    invia_messaggio(chat_id,
                        f"Ciao {nome}! 🌿 Benvenuta nel programma skincare. ✨\n\n{msg_g1}"
                    )
                print(f"Nuovo iscritto: {nome} ({chat_id})")
            else:
                invia_messaggio(chat_id, f"Ciao {nome}! Sei già iscritta. 😊")

    with open(offset_file, "w") as f:
        f.write(str(offset))


def invia_messaggi_giornalieri() -> None:
    messaggi = scarica_messaggi()
    if not messaggi:
        print("Nessun messaggio trovato nel Doc.")
        return

    totale = len(messaggi)
    chiavi = sorted(messaggi.keys())
    iscritti = leggi_iscritti()

    print(f"Messaggi disponibili: {totale} | Iscritti: {len(iscritti)}")

    for iscritto in iscritti:
        chat_id = str(iscritto.get("chat_id", ""))
        nome    = iscritto.get("nome", "")
        data_is = iscritto.get("data_iscrizione", "")

        if not chat_id or not data_is:
            continue

        giorno = calcola_giorno(data_is, totale)

        if giorno is None:
            print(f"{nome}: sequenza completata o non ancora iniziata.")
            continue

        numero_msg = chiavi[giorno - 1]
        testo = messaggi[numero_msg]

        ok = invia_messaggio(chat_id, testo)
        stato = "✅" if ok else "❌"
        print(f"{stato} {nome} → Giorno {giorno}: {testo[:50]}...")


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "invia"

    if mode == "start":
        print("Controllo nuovi iscritti...")
        processa_aggiornamenti()
    else:
        print("Invio messaggi giornalieri...")
        invia_messaggi_giornalieri()
