"""
Bot Telegram Skincare — Sequenza personalizzata per ogni iscritto
- mode start → registra nuovi /start (cronjob ogni 5 min)
- mode invia → invia messaggio del giorno (cronjob alle 11:30)
"""

import os
import re
import requests
from datetime import date, datetime, timedelta

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GOOGLE_DOC_FILE_ID = os.environ["GOOGLE_DOC_FILE_ID"]
APPS_SCRIPT_URL    = os.environ["APPS_SCRIPT_URL"]


def scarica_messaggi() -> dict:
    url = f"https://docs.google.com/document/d/{GOOGLE_DOC_FILE_ID}/export?format=txt"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    messaggi = {}
    pattern = re.compile(r'[Gg]iorno\s+(\d+)\s*[:.\-]\s*(.+?)(?=\n[Gg]iorno\s+\d+|\Z)', re.DOTALL)
    for match in pattern.finditer(r.text):
        numero    = int(match.group(1))
        contenuto = match.group(2).strip()
        if contenuto:
            messaggi[numero] = contenuto
    return messaggi


def leggi_iscritti() -> list:
    r = requests.get(APPS_SCRIPT_URL, params={"action": "leggi"}, timeout=15)
    r.raise_for_status()
    data = r.json()
    # Filtra la riga intestazione se presente
    return [i for i in data if str(i.get("chat_id", "")) != "chat_id"]


def salva_iscritto(chat_id: str, nome: str, data_iscrizione: str) -> None:
    payload = {
        "action": "scrivi",
        "chat_id": chat_id,
        "nome": nome,
        "data_iscrizione": data_iscrizione
    }
    requests.post(APPS_SCRIPT_URL, json=payload, timeout=15).raise_for_status()


def invia_messaggio(chat_id: str, testo: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": testo}, timeout=15)
    return r.ok


def leggi_offset() -> int:
    """Legge l'offset salvato nel Google Sheet (colonna D, riga 1)."""
    try:
        r = requests.get(APPS_SCRIPT_URL, params={"action": "leggi_offset"}, timeout=15)
        if r.ok:
            data = r.json()
            return int(data.get("offset", 0))
    except:
        pass
    return 0


def salva_offset(offset: int) -> None:
    """Salva l'offset nel Google Sheet."""
    try:
        requests.post(APPS_SCRIPT_URL,
            json={"action": "salva_offset", "offset": offset}, timeout=15)
    except:
        pass


def processa_aggiornamenti() -> None:
    """Controlla i nuovi /start e registra gli iscritti."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    offset = leggi_offset()

    r = requests.get(url, params={"offset": offset, "timeout": 5}, timeout=10)
    if not r.ok:
        print(f"Errore getUpdates: {r.text}")
        return

    updates = r.json().get("result", [])
    if not updates:
        print("Nessun nuovo aggiornamento.")
        return

    iscritti = leggi_iscritti()
    ids_esistenti = set(str(i.get("chat_id", "")) for i in iscritti)

    for update in updates:
        offset = update["update_id"] + 1
        msg  = update.get("message", {})
        text = msg.get("text", "")

        if text.startswith("/start"):
            chat_id = str(msg["chat"]["id"])
            nome    = msg["from"].get("first_name", "Amico")

            if chat_id not in ids_esistenti:
                # Salva con data di ieri → oggi è già Giorno 1
                data_ieri = (date.today() - timedelta(days=1)).isoformat()
                salva_iscritto(chat_id, nome, data_ieri)
                ids_esistenti.add(chat_id)

                # Invia subito il Giorno 1
                messaggi = scarica_messaggi()
                if messaggi:
                    chiavi  = sorted(messaggi.keys())
                    msg_g1  = messaggi[chiavi[0]]
                    invia_messaggio(chat_id,
                        f"Ciao {nome}! 🌿 Benvenuta nel programma skincare. ✨\n\n{msg_g1}"
                    )
                print(f"✅ Nuovo iscritto: {nome} ({chat_id})")
            else:
                invia_messaggio(chat_id, f"Ciao {nome}! Sei già iscritta. 😊")
                print(f"ℹ️ Già iscritto: {nome}")

    salva_offset(offset)


def calcola_giorno(data_iscrizione_str: str, totale: int):
    try:
        data_iscr = datetime.fromisoformat(str(data_iscrizione_str).strip()).date()
    except (ValueError, TypeError):
        return None
    delta = (date.today() - data_iscr).days + 1
    if delta < 1 or delta > totale:
        return None
    return delta


def invia_messaggi_giornalieri() -> None:
    messaggi = scarica_messaggi()
    if not messaggi:
        print("Nessun messaggio nel Doc.")
        return

    totale = len(messaggi)
    chiavi = sorted(messaggi.keys())
    iscritti = leggi_iscritti()
    print(f"Messaggi: {totale} | Iscritti: {len(iscritti)}")

    for iscritto in iscritti:
        chat_id = str(iscritto.get("chat_id", ""))
        nome    = iscritto.get("nome", "")
        data_is = iscritto.get("data_iscrizione", "")

        if not chat_id or not data_is:
            continue

        giorno = calcola_giorno(data_is, totale)
        if giorno is None:
            print(f"{nome}: sequenza completata.")
            continue

        testo = messaggi[chiavi[giorno - 1]]
        ok    = invia_messaggio(chat_id, testo)
        print(f"{'✅' if ok else '❌'} {nome} → Giorno {giorno}: {testo[:50]}...")


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "invia"

    if mode == "start":
        print("Controllo nuovi iscritti...")
        processa_aggiornamenti()
    else:
        print("Invio messaggi giornalieri...")
        invia_messaggi_giornalieri()
